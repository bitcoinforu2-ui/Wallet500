from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import resilient_http
except ImportError:
    from scripts import resilient_http

try:
    import spot_market_discovery_collector as spot_identity
except ImportError:
    from scripts import spot_market_discovery_collector as spot_identity

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/futures-market-discovery.json"
STATE = ROOT / "data/futures-market-discovery-state.json"
SPOT_DISCOVERY = ROOT / "data/spot-market-discovery.json"
GATE = "https://api.gateio.ws/api/v4"
UA = "Wallet500-FuturesEarlyRadar/1.0"

MIN_EARLY_CHANGE_PCT = 5.0
BROAD_CHANGE_PCT = 8.0
STRONG_CHANGE_PCT = 15.0
HOT_CHANGE_PCT = 20.0
CUMULATIVE_HOT_PCT = 15.0
QUARTER_WAVE_PCT = 25.0
VOLUME_ACCELERATION_MULTIPLE = 2.5
VOLUME_SHOCK_MULTIPLE = 4.0
TOP_RANK_EARLY = 20
MAX_SELECTED = 120
# Identity is a bounded enrichment step. The raw futures leaderboard must never
# wait for dozens of duplicate network lookups; same-run Spot exact identities
# are reused first and only the hottest unresolved symbols hit network recovery.
IDENTITY_RESOLUTION_BUDGET = 24
EXPENSIVE_RECOVERY_BUDGET = 0
IDENTITY_WORKERS = 12
HOT_RETENTION_HOURS = 36


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def num(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError, OverflowError):
        return default


def get_json(url: str, timeout: int = 15):
    return resilient_http.request_json(
        url,
        timeout=timeout,
        attempts=4,
        cache_ttl=30,
        user_agent=UA,
    )


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pct(current, previous):
    c = num(current)
    p = num(previous)
    if c is None or p is None or p <= 0:
        return None
    return (c / p - 1.0) * 100.0


def symbol_from_contract(contract: str) -> str:
    raw = str(contract or "").upper().strip()
    return raw[:-5] if raw.endswith("_USDT") else ""


def select_reason(row: dict) -> list[str]:
    reasons = []
    change = float(row.get("change_24h_pct") or 0)
    rank = int(row.get("positive_gainer_rank") or 999999)
    baseline_multiple = float(row.get("futures_volume_baseline_multiple") or 0)
    scan_multiple = float(row.get("futures_volume_scan_multiple") or 0)
    gain = float(row.get("gain_from_first_seen_pct") or 0)
    oi_delta = row.get("futures_total_size_change_pct")
    oi_delta = float(oi_delta) if oi_delta is not None else 0.0

    if change >= BROAD_CHANGE_PCT:
        reasons.append("FUTURES_CHANGE_GE_8PCT")
    if change >= STRONG_CHANGE_PCT:
        reasons.append("FUTURES_CHANGE_GE_15PCT")
    if rank <= TOP_RANK_EARLY and change >= MIN_EARLY_CHANGE_PCT:
        reasons.append("FUTURES_TOP20_EARLY_MOVER")
    if baseline_multiple >= VOLUME_ACCELERATION_MULTIPLE and change >= MIN_EARLY_CHANGE_PCT:
        reasons.append("FUTURES_VOLUME_ACCELERATION")
    if scan_multiple >= VOLUME_ACCELERATION_MULTIPLE and change >= MIN_EARLY_CHANGE_PCT:
        reasons.append("FUTURES_SCAN_VOLUME_ACCELERATION")
    if gain >= CUMULATIVE_HOT_PCT:
        reasons.append("FUTURES_CUMULATIVE_GAIN_GE_15PCT")
    if oi_delta >= 10.0 and change >= MIN_EARLY_CHANGE_PCT:
        reasons.append("FUTURES_OPEN_INTEREST_PROXY_ACCELERATION")
    return reasons


def priority_key(row: dict):
    forced = 0 if row.get("forced_hot_watch") else 1
    rank = int(row.get("positive_gainer_rank") or 999999)
    change = float(row.get("change_24h_pct") or 0)
    gain = float(row.get("gain_from_first_seen_pct") or 0)
    vol_mult = float(row.get("futures_volume_baseline_multiple") or 0)
    volume = float(row.get("quote_volume_24h_usd") or 0)
    return (forced, rank, -max(change, gain), -vol_mult, -volume)


def load_same_run_spot_identities(path: Path = SPOT_DISCOVERY) -> dict[str, dict]:
    """Reuse exact Spot identities instead of resolving the same symbol twice.

    Only a symbol with one unambiguous exact chain+contract+pair is reused. If the
    Spot snapshot contains multiple distinct exact identities for a ticker, fail
    closed and leave it for bounded network resolution.
    """
    doc = load(path, {"candidates": []})
    grouped: dict[str, list[dict]] = {}
    for row in doc.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        if row.get("identity_status") != "RESOLVED_EXACT":
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        network = str(row.get("network") or "").strip()
        contract = str(row.get("contract") or "").strip()
        pair = str(row.get("pair") or "").strip()
        if not symbol or not network or not contract or not pair:
            continue
        grouped.setdefault(symbol, []).append(row)

    out = {}
    for symbol, rows in grouped.items():
        uniq = {
            (
                str(x.get("network") or "").lower(),
                str(x.get("contract") or ""),
                str(x.get("pair") or ""),
            )
            for x in rows
        }
        if len(uniq) != 1:
            continue
        best = max(rows, key=lambda x: float(x.get("dex_liquidity_usd") or 0))
        out[symbol] = {
            "identity_status": "RESOLVED_EXACT",
            "identity_reason": "REUSED_SAME_RUN_GATE_SPOT_EXACT_IDENTITY",
            "network": best.get("network"),
            "contract": best.get("contract"),
            "pair": best.get("pair"),
            "dex_url": best.get("dex_url") or "",
            "dex_liquidity_usd": best.get("dex_liquidity_usd"),
            "identity_source": "same-run Gate Spot exact identity",
            "identity_reused_from_spot": True,
            "research_only_identity": bool(best.get("research_only_identity")),
        }
    return out


def _identity_task(index: int, row: dict, native_registry: dict, expensive: bool):
    result = spot_identity.resolve_identity(
        row.get("symbol") or "",
        native_registry=native_registry,
        cex_price=row.get("discovery_price"),
        allow_expensive_recovery=expensive,
    )
    return index, result


def resolve_identities(selected: list[dict]) -> dict[int, dict]:
    native_registry = spot_identity.load_native_discovery_registry()
    reused = load_same_run_spot_identities()
    results: dict[int, dict] = {}

    # First consume zero-cost exact identities from the Spot discovery that ran
    # immediately before this sensor in the same Unified Watch job.
    unresolved = []
    for i, row in enumerate(selected):
        exact = reused.get(str(row.get("symbol") or "").upper().strip())
        if exact:
            results[i] = exact
        else:
            unresolved.append(i)

    # Never let identity enrichment hold the futures leaderboard hostage. Resolve
    # only the hottest unresolved slice; the remainder persists as PENDING and is
    # retried on later cycles.
    unresolved.sort(key=lambda i: priority_key(selected[i]))
    target_indexes = unresolved[:IDENTITY_RESOLUTION_BUDGET]
    expensive_set: set[int] = set()

    if not target_indexes:
        return results

    with ThreadPoolExecutor(max_workers=min(IDENTITY_WORKERS, len(target_indexes))) as pool:
        pending = {
            pool.submit(
                _identity_task,
                i,
                selected[i],
                native_registry,
                i in expensive_set,
            ): i
            for i in target_indexes
        }
        for fut in as_completed(pending):
            i = pending[fut]
            try:
                _, result = fut.result()
            except Exception as exc:
                result = {
                    "identity_status": "UNRESOLVED",
                    "identity_reason": f"FUTURES_IDENTITY_EXCEPTION:{type(exc).__name__}",
                }
            results[i] = result
    return results


def run() -> dict:
    tickers = get_json(f"{GATE}/futures/usdt/tickers")
    contracts = get_json(f"{GATE}/futures/usdt/contracts")
    if not isinstance(tickers, list) or not isinstance(contracts, list):
        raise RuntimeError("GATE_FUTURES_MARKET_DATA_UNAVAILABLE")

    active_contracts = {}
    for row in contracts:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").upper().strip()
        if not name.endswith("_USDT") or row.get("in_delisting") is True:
            continue
        active_contracts[name] = row

    rows = []
    for t in tickers:
        if not isinstance(t, dict):
            continue
        contract = str(t.get("contract") or "").upper().strip()
        symbol = symbol_from_contract(contract)
        if not symbol or contract not in active_contracts:
            continue
        last = num(t.get("last") or t.get("mark_price"))
        change = num(t.get("change_percentage"))
        volume = num(t.get("volume_24h_quote") or t.get("volume_24h_usd"), 0.0) or 0.0
        total_size = num(t.get("total_size"), 0.0) or 0.0
        funding = num(t.get("funding_rate"), 0.0) or 0.0
        if last is None or last <= 0 or change is None:
            continue
        rows.append({
            "symbol": symbol,
            "futures_contract": contract,
            "source": "Gate Futures Early Radar",
            "source_url": f"https://www.gate.com/futures/USDT/{contract}",
            "discovery_price": last,
            "change_24h_pct": change,
            "discovery_momentum_change_pct": change,
            "quote_volume_24h_usd": round(volume, 2),
            "futures_total_size": total_size,
            "futures_funding_rate": funding,
            "futures_funding_rate_pct": funding * 100.0,
            "high_24h": num(t.get("high_24h")),
            "low_24h": num(t.get("low_24h")),
            "mark_price": num(t.get("mark_price")),
            "index_price": num(t.get("index_price")),
        })

    positive = sorted(
        [x for x in rows if float(x.get("change_24h_pct") or 0) > 0],
        key=lambda x: (float(x.get("change_24h_pct") or 0), float(x.get("quote_volume_24h_usd") or 0)),
        reverse=True,
    )
    rank_map = {x["futures_contract"]: i for i, x in enumerate(positive, 1)}

    state = load(STATE, {"version": 1, "markets": {}})
    old_markets = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    old_markets = dict(old_markets)
    current = now_dt()
    selected = []

    for row in rows:
        contract = row["futures_contract"]
        old = old_markets.get(contract) if isinstance(old_markets.get(contract), dict) else {}
        first_price = num(old.get("first_seen_price")) or row["discovery_price"]
        first_volume = num(old.get("first_seen_quote_volume_24h_usd")) or float(row.get("quote_volume_24h_usd") or 0)
        prev_volume = num(old.get("last_quote_volume_24h_usd"), 0.0) or 0.0
        prev_size = num(old.get("last_total_size"), 0.0) or 0.0
        gain = pct(row["discovery_price"], first_price) or 0.0
        baseline_mult = float(row.get("quote_volume_24h_usd") or 0) / first_volume if first_volume > 0 else 0.0
        scan_mult = float(row.get("quote_volume_24h_usd") or 0) / prev_volume if prev_volume > 0 else 0.0
        size_delta = pct(row.get("futures_total_size"), prev_size)
        row.update({
            "positive_gainer_rank": rank_map.get(contract),
            "first_seen_at": old.get("first_seen_at") or current.isoformat(),
            "first_seen_price": first_price,
            "first_seen_change_24h_pct": old.get("first_seen_change_24h_pct", row.get("change_24h_pct")),
            "first_seen_quote_volume_24h_usd": first_volume,
            "gain_from_first_seen_pct": round(gain, 4),
            "futures_volume_baseline_multiple": round(baseline_mult, 4),
            "futures_volume_scan_multiple": round(scan_mult, 4),
            "futures_total_size_change_pct": round(size_delta, 4) if size_delta is not None else None,
        })
        reasons = select_reason(row)
        previous_hot_until = str(old.get("hot_until") or "")
        retain_hot = False
        if previous_hot_until:
            try:
                retain_hot = current <= datetime.fromisoformat(previous_hot_until.replace("Z", "+00:00"))
            except Exception:
                retain_hot = False

        forced = bool(
            float(row.get("change_24h_pct") or 0) >= HOT_CHANGE_PCT
            or float(row.get("gain_from_first_seen_pct") or 0) >= QUARTER_WAVE_PCT
            or float(row.get("futures_volume_baseline_multiple") or 0) >= VOLUME_SHOCK_MULTIPLE
            or (int(row.get("positive_gainer_rank") or 999999) <= 10 and float(row.get("change_24h_pct") or 0) >= 10)
        )
        row["forced_hot_watch"] = forced
        row["futures_discovery_reasons"] = reasons

        selected_now = bool(reasons)
        prior_selected = bool(old.get("selected_last_scan"))
        episode_seq = int(old.get("episode_seq") or 0)
        episode_started_at = old.get("episode_started_at")
        if selected_now and not prior_selected:
            episode_seq += 1
            episode_started_at = current.isoformat()
        if (selected_now or retain_hot) and not episode_started_at:
            # Migration/recovery path for a previously hot state that predates
            # episode tracking. This creates one deterministic ongoing episode.
            episode_seq = max(1, episode_seq)
            episode_started_at = old.get("first_seen_at") or current.isoformat()

        if selected_now or retain_hot:
            row["hot_until"] = (current + timedelta(hours=HOT_RETENTION_HOURS)).isoformat() if selected_now else previous_hot_until
            row["retained_hot"] = bool(retain_hot and not selected_now)
            row["futures_episode_seq"] = episode_seq
            row["futures_episode_started_at"] = episode_started_at
            row["futures_episode_id"] = f"{contract}:{episode_seq}"
            selected.append(row)

        old_markets[contract] = {
            "symbol": row["symbol"],
            "first_seen_at": row["first_seen_at"],
            "first_seen_price": row["first_seen_price"],
            "first_seen_change_24h_pct": row["first_seen_change_24h_pct"],
            "first_seen_quote_volume_24h_usd": row["first_seen_quote_volume_24h_usd"],
            "last_seen_at": current.isoformat(),
            "last_price": row["discovery_price"],
            "last_change_24h_pct": row["change_24h_pct"],
            "last_quote_volume_24h_usd": row["quote_volume_24h_usd"],
            "last_total_size": row["futures_total_size"],
            "peak_change_24h_pct": max(float(old.get("peak_change_24h_pct") or -999999), float(row.get("change_24h_pct") or 0)),
            "peak_gain_from_first_seen_pct": max(float(old.get("peak_gain_from_first_seen_pct") or -999999), float(row.get("gain_from_first_seen_pct") or 0)),
            "hot_until": row.get("hot_until") or previous_hot_until or None,
            "selected_last_scan": selected_now,
            "episode_seq": episode_seq,
            "episode_started_at": episode_started_at,
        }

    selected.sort(key=priority_key)
    selected = selected[:MAX_SELECTED]

    # Publish the raw leaderboard checkpoint BEFORE any external identity calls.
    # Even if an identity provider stalls, Unified Watch still receives fresh
    # futures movers and immutable first-seen anchors instead of a null snapshot.
    checkpoint_rows = []
    for row in selected:
        pending_row = dict(row)
        pending_row.update({
            "status": "FUTURES_SIGNAL_IDENTITY_PENDING",
            "identity_status": "PENDING",
            "identity_reason": "IDENTITY_ENRICHMENT_IN_PROGRESS",
            "futures_signal_verified": True,
            "research_only_identity": True,
        })
        checkpoint_rows.append(pending_row)

    checkpoint = {
        "version": 1,
        "generated_at": current.isoformat(),
        "mode": "UNIFIED_WATCH_GATE_FUTURES_EARLY_RADAR_V1",
        "checkpoint": "RAW_FUTURES_LEADERBOARD_BEFORE_IDENTITY",
        "truth_contract": {
            "sensor_only_never_direct_buy": True,
            "exact_identity_required_before_actionable_watch": True,
            "futures_signal_never_bypasses_final_buy_gates": True,
            "automatic_trade": False,
        },
        "counts": {
            "active_usdt_contracts": len(active_contracts),
            "ticker_rows": len(rows),
            "positive_movers": len(positive),
            "selected": len(selected),
            "identity_resolved": 0,
            "identity_pending": len(selected),
            "forced_hot_watch": sum(bool(x.get("forced_hot_watch")) for x in selected),
            "top10_selected": sum(int(x.get("positive_gainer_rank") or 999999) <= 10 for x in selected),
        },
        "candidates": checkpoint_rows,
    }
    write(OUTPUT, checkpoint)
    write(STATE, {"version": 1, "updated_at": current.isoformat(), "markets": old_markets})

    identity_results = resolve_identities(selected)

    resolved = 0
    for i, row in enumerate(selected):
        identity = identity_results.get(i)
        if identity:
            row.update(identity)
        elif row.get("forced_hot_watch"):
            row.update({"identity_status": "PENDING", "identity_reason": "RESOLUTION_BUDGET_OR_TRANSIENT_FAILURE"})
        else:
            row.update({"identity_status": "PENDING", "identity_reason": "RESOLUTION_BUDGET"})

        if row.get("identity_status") == "RESOLVED_EXACT":
            resolved += 1
            row["status"] = "IDENTITY_RESOLVED"
            row["execution_identity_scope"] = "EXACT_CHAIN_CONTRACT_PAIR_WITH_FUTURES_TRIGGER"
            row["futures_signal_verified"] = True
            row["research_only_identity"] = bool(row.get("research_only_identity"))
        else:
            row["status"] = "FUTURES_SIGNAL_IDENTITY_PENDING"
            row["futures_signal_verified"] = True
            row["research_only_identity"] = True

        contract = row["futures_contract"]
        state_row = old_markets.get(contract) or {}
        for field in ("identity_status", "identity_reason", "network", "contract", "pair", "dex_url", "dex_liquidity_usd", "identity_source"):
            if row.get(field) is not None:
                state_row[field] = row.get(field)
        old_markets[contract] = state_row

    out = {
        "version": 1,
        "generated_at": current.isoformat(),
        "mode": "UNIFIED_WATCH_GATE_FUTURES_EARLY_RADAR_V1",
        "truth_contract": {
            "sensor_only_never_direct_buy": True,
            "exact_identity_required_before_actionable_watch": True,
            "futures_signal_never_bypasses_final_buy_gates": True,
            "automatic_trade": False,
        },
        "counts": {
            "active_usdt_contracts": len(active_contracts),
            "ticker_rows": len(rows),
            "positive_movers": len(positive),
            "selected": len(selected),
            "identity_resolved": resolved,
            "identity_pending": len(selected) - resolved,
            "identity_reused_from_spot": sum(bool(x.get("identity_reused_from_spot")) for x in selected),
            "forced_hot_watch": sum(bool(x.get("forced_hot_watch")) for x in selected),
            "top10_selected": sum(int(x.get("positive_gainer_rank") or 999999) <= 10 for x in selected),
        },
        "candidates": selected,
    }
    write(OUTPUT, out)
    write(STATE, {"version": 1, "updated_at": current.isoformat(), "markets": old_markets})
    return out


def main() -> int:
    doc = run()
    print(json.dumps({
        "status": "OK",
        "generated_at": doc.get("generated_at"),
        "counts": doc.get("counts"),
        "top": [
            {
                "symbol": x.get("symbol"),
                "change_24h_pct": x.get("change_24h_pct"),
                "rank": x.get("positive_gainer_rank"),
                "volume_multiple": x.get("futures_volume_baseline_multiple"),
                "identity_status": x.get("identity_status"),
            }
            for x in (doc.get("candidates") or [])[:12]
        ],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
