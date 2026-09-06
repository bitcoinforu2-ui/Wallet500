from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .genesis_radar import PAPER_ENTRY_USD, THRESHOLDS, genesis_score
from .holder_truth_provider import fetch_rpc_holder_truth
from .market_data import snapshot
from .market_discovery import discover_tokens, discovery_diagnostics
from .solana_mintability_gate import resolve as resolve_mintability

CHAINS = ("solana", "ethereum", "bsc")
LEGACY_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ACTIONABLE = {"PAPER_BUY_CANDIDATE", "STRONG_GENESIS", "EXCEPTIONAL_GENESIS"}
PAPER_AGE_BANDS = {"EARLY_WATCH", "PRIME_GENESIS_WINDOW", "LATE_GENESIS_WINDOW"}
HISTORY_LIMIT = 192


def _data_dir() -> Path:
    return Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _n(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _maybe(value: Any) -> float | None:
    try:
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _same(chain: str, a: Any, b: Any) -> bool:
    if not a or not b:
        return False
    return str(a).lower() == str(b).lower() if chain in {"ethereum", "bsc"} else str(a) == str(b)


def _pair_age_minutes(created_at: Any, now: datetime) -> float | None:
    try:
        raw = float(created_at)
        if raw > 10_000_000_000:
            raw /= 1000.0
        return max(0.0, (now.timestamp() - raw) / 60.0)
    except (TypeError, ValueError):
        return None


def _key(chain: str, token: str, pair: str) -> str:
    if chain in {"ethereum", "bsc"}:
        token, pair = token.lower(), pair.lower()
    return f"{chain}:{token}:{pair}"


def _priority(row: dict) -> tuple:
    sources = row.get("sources") or [row.get("source")]
    source_text = " ".join(str(x or "") for x in sources)
    if "new_pools:fresh" in source_text:
        lane = 0
    elif "birdeye:new_listing" in source_text or "moonshot:new" in source_text:
        lane = 1
    elif "moonshot:rising" in source_text or "token-profiles/latest" in source_text:
        lane = 2
    elif "new_pools:deep" in source_text:
        lane = 3
    else:
        lane = 4
    return (lane, -_n(row.get("reserve_usd")), -int(row.get("source_confirmations") or 1))


def _prior(history: list[dict], now_epoch: float, seconds_ago: int) -> dict | None:
    eligible = [x for x in history if now_epoch - _n(x.get("ts")) >= seconds_ago]
    return max(eligible, key=lambda x: _n(x.get("ts")), default=None)


def _growth(current: float | None, prior: dict | None, field: str) -> float | None:
    if current is None or not prior:
        return None
    old = _maybe(prior.get(field))
    if old is None or old <= 0:
        return None
    return (current / old - 1.0) * 100.0


def _rpc_urls() -> list[str]:
    configured = str(os.getenv("SOLANA_RPC_URL") or "").strip()
    return list(dict.fromkeys(x for x in (
        configured,
        "https://solana-rpc.publicnode.com",
        "https://api.mainnet-beta.solana.com",
    ) if x))


def _rpc(url: str, method: str, params: list, timeout: int = 18):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "Wallet500-Genesis/1.0"}, method="POST")
    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("error"):
        raise RuntimeError(f"RPC_{method}_FAILED")
    return payload.get("result")


def _target_lp_amounts(mint: str, snap: dict) -> list[float]:
    out: list[float] = []
    pools = list(snap.get("pools") or [])
    pools.insert(0, snap)
    for pool in pools:
        if _same("solana", mint, pool.get("base_token_address")):
            amount = _maybe(pool.get("liquidity_base"))
        elif _same("solana", mint, pool.get("quote_token_address")):
            amount = _maybe(pool.get("liquidity_quote"))
        else:
            amount = None
        if amount is not None and amount > 0:
            out.append(amount)
    dedup: list[float] = []
    for amount in out:
        if not any(abs(amount - x) / max(amount, x, 1e-12) <= 0.02 for x in dedup):
            dedup.append(amount)
    return dedup


def solana_distribution_truth(mint: str, snap: dict) -> dict:
    attempts = []
    for url in _rpc_urls():
        try:
            supply_result = _rpc(url, "getTokenSupply", [mint, {"commitment": "confirmed"}]) or {}
            supply_value = supply_result.get("value") if isinstance(supply_result, dict) else {}
            supply = _maybe((supply_value or {}).get("uiAmountString"))
            largest_result = _rpc(url, "getTokenLargestAccounts", [mint, {"commitment": "confirmed"}]) or {}
            rows = largest_result.get("value") if isinstance(largest_result, dict) else None
            if not supply or supply <= 0 or not isinstance(rows, list):
                raise RuntimeError("DISTRIBUTION_INVALID")

            balances = []
            for row in rows:
                amount = _maybe((row or {}).get("uiAmountString"))
                if amount is not None and amount > 0:
                    balances.append({"address": (row or {}).get("address"), "amount": amount})

            expected_lp = _target_lp_amounts(mint, snap)
            excluded: set[int] = set()
            matches = []
            for expected in expected_lp:
                best = None
                for idx, row in enumerate(balances):
                    if idx in excluded:
                        continue
                    diff = abs(row["amount"] - expected) / max(row["amount"], expected, 1e-12)
                    if diff <= 0.12 and (best is None or diff < best[0]):
                        best = (diff, idx)
                if best is not None:
                    excluded.add(best[1])
                    matches.append({"address": balances[best[1]]["address"], "relative_diff": round(best[0], 4)})

            non_system = [row for idx, row in enumerate(balances) if idx not in excluded]
            top10 = sum(row["amount"] for row in non_system[:10]) / supply * 100.0
            largest = (non_system[0]["amount"] / supply * 100.0) if non_system else 0.0
            return {
                "verified": True,
                "status": "APPROX_LP_VAULT_EXCLUSION",
                "top10_ex_system_pct": round(top10, 4),
                "largest_non_system_wallet_pct": round(largest, 4),
                "supply_ui": supply,
                "lp_vault_matches": matches,
                "lp_vault_match_count": len(matches),
                "method": "getTokenLargestAccounts; exclude only balances matching exact-pair liquidity token amounts within 12%",
                "conservative": True,
                "attempts": attempts,
            }
        except Exception as exc:
            attempts.append({"rpc": url.split("//", 1)[-1].split("/", 1)[0], "error": f"{type(exc).__name__}:{str(exc)[:100]}"})
    return {"verified": False, "status": "DISTRIBUTION_UNAVAILABLE", "attempts": attempts}


def _history_features(record: dict, current: dict, now_epoch: float) -> dict:
    history = list(record.get("history") or [])
    last = history[-1] if history else None
    p30 = _prior(history, now_epoch, 25 * 60)
    p2h = _prior(history, now_epoch, 110 * 60)

    holders = _maybe(current.get("holders"))
    top10 = _maybe(current.get("top10_ex_system_pct"))
    liquidity = _maybe(current.get("liquidity_usd"))

    peak_liq = max([_n(x.get("liquidity_usd")) for x in history] + [_n(liquidity)])
    liq_dd = ((peak_liq - liquidity) / peak_liq * 100.0) if liquidity is not None and peak_liq > 0 else None

    current_m5 = _n(current.get("volume_m5"))
    previous_m5 = _n((last or {}).get("volume_m5"))
    baseline30_m5 = _n((p30 or {}).get("volume_m5"))

    return {
        "volume_15m_usd": current_m5 * 3.0,
        "prev_volume_15m_usd": previous_m5 * 3.0,
        "volume_30m_usd": current_m5 * 6.0,
        "baseline_volume_30m_usd": baseline30_m5 * 6.0,
        "unique_buyers_15m": 0,
        "prev_unique_buyers_15m": 0,
        "buys_15m": round(_n(current.get("buys_h1")) / 4.0),
        "sells_15m": round(_n(current.get("sells_h1")) / 4.0),
        "holder_growth_30m_pct": _growth(holders, p30, "holders"),
        "holder_growth_2h_pct": _growth(holders, p2h, "holders"),
        "top10_concentration_delta_pct": (
            top10 - _n(p30.get("top10_ex_system_pct"))
            if top10 is not None and p30 and p30.get("top10_ex_system_pct") is not None
            else None
        ),
        "liquidity_growth_30m_pct": _growth(liquidity, p30, "liquidity_usd"),
        "liquidity_growth_2h_pct": _growth(liquidity, p2h, "liquidity_usd"),
        "liquidity_drawdown_from_peak_pct": liq_dd,
        "measurement_method": "DEXSCREENER_M5_RUN_RATE_PLUS_FORWARD_STATE; UNIQUE_BUYERS_NOT_FABRICATED",
    }


def _shadow_score(candidate: dict, scored: dict) -> float:
    liquidity = _maybe(candidate.get("liquidity_usd"))
    holders = _maybe(candidate.get("holders"))
    top10 = _maybe(candidate.get("top10_ex_system_pct"))
    largest = _maybe(candidate.get("largest_non_system_wallet_pct"))
    score = 0.0

    if liquidity is not None and liquidity >= THRESHOLDS.preferred_liquidity_usd:
        score += 20
    elif liquidity is not None and liquidity >= THRESHOLDS.min_liquidity_usd:
        score += 15

    if holders is not None and holders >= THRESHOLDS.preferred_holders:
        score += 15
    elif holders is not None and holders >= THRESHOLDS.min_holders:
        score += 10

    if top10 is not None and largest is not None:
        if top10 <= THRESHOLDS.top10_preferred_pct and largest <= THRESHOLDS.largest_wallet_preferred_pct:
            score += 15
        elif top10 <= THRESHOLDS.top10_hard_max_pct and largest <= THRESHOLDS.largest_wallet_hard_max_pct:
            score += 8

    accel = scored.get("acceleration") or {}
    score += min(25.0, _n(accel.get("count")) * 6.0 + _n(accel.get("primary_count")) * 2.0)

    ratio = _n(accel.get("buy_sell_ratio_15m"))
    if ratio >= 1.5:
        score += 10
    elif ratio >= THRESHOLDS.min_buy_sell_ratio:
        score += 6

    if candidate.get("mint_authority_safe") is True and candidate.get("freeze_authority_safe") is True:
        score += 10

    confirmations = int(candidate.get("source_confirmations") or 1)
    score += min(5.0, float(confirmations) * 2.0)
    return round(min(100.0, score), 1)


def _shadow_ready(candidate: dict, scored: dict, shadow_score: float) -> bool:
    if candidate.get("chain") != "solana":
        return False
    if scored.get("age_band") not in PAPER_AGE_BANDS:
        return False
    if scored.get("extension_band") in {"VERY_EXTENDED", "LATE_NO_CHASE"}:
        return False
    if scored.get("extension_band") == "EXTENDED" and shadow_score < 85:
        return False
    if not (scored.get("acceleration") or {}).get("passed"):
        return False

    liquidity = _maybe(candidate.get("liquidity_usd"))
    holders = _maybe(candidate.get("holders"))
    top10 = _maybe(candidate.get("top10_ex_system_pct"))
    largest = _maybe(candidate.get("largest_non_system_wallet_pct"))
    if liquidity is None or liquidity < THRESHOLDS.min_liquidity_usd:
        return False
    if holders is None or holders < THRESHOLDS.min_holders:
        return False
    if top10 is None or top10 > THRESHOLDS.top10_hard_max_pct:
        return False
    if largest is None or largest > THRESHOLDS.largest_wallet_hard_max_pct:
        return False
    if candidate.get("mint_authority_safe") is not True or candidate.get("freeze_authority_safe") is not True:
        return False
    if candidate.get("transfer_restrictions_safe") is False:
        return False
    return shadow_score >= 75.0


def _paper_mode(candidate: dict) -> str | None:
    if candidate.get("status") in ACTIONABLE and (candidate.get("safety") or {}).get("passed") is True:
        return "VERIFIED_PAPER"
    if candidate.get("shadow_paper_ready") is True:
        return "SHADOW_PAPER_UNVERIFIED_LP"
    return None


def _open_paper_entry(candidate: dict, now: datetime) -> dict:
    price = _n(candidate.get("price_usd"))
    quantity = PAPER_ENTRY_USD / price
    return {
        "entry_id": f"{candidate['candidate_key']}:{int(now.timestamp())}",
        "candidate_key": candidate["candidate_key"],
        "chain": candidate.get("chain"),
        "token": candidate.get("token"),
        "symbol": candidate.get("symbol"),
        "pair_address": candidate.get("pair_address"),
        "dex_url": candidate.get("url"),
        "created_at": now.isoformat(),
        "paper_mode": _paper_mode(candidate),
        "verified_track_record": _paper_mode(candidate) == "VERIFIED_PAPER",
        "allocation_usd": PAPER_ENTRY_USD,
        "entry_price_usd": price,
        "initial_quantity": quantity,
        "remaining_quantity": quantity,
        "realized_cash_usd": 0.0,
        "tp50_done": False,
        "entry_genesis_score": candidate.get("genesis_score"),
        "entry_shadow_score": candidate.get("shadow_score"),
        "entry_status": candidate.get("status"),
        "entry_age_minutes": candidate.get("pair_age_minutes"),
        "entry_liquidity_usd": candidate.get("liquidity_usd"),
        "entry_holders": candidate.get("holders"),
        "entry_top10_pct": candidate.get("top10_ex_system_pct"),
        "entry_largest_wallet_pct": candidate.get("largest_non_system_wallet_pct"),
        "entry_acceleration_signals": (candidate.get("acceleration") or {}).get("signals") or [],
        "peak_price_usd": price,
        "current_price_usd": price,
        "current_value_usd": PAPER_ENTRY_USD,
        "pnl_pct": 0.0,
        "tracking_status": "OPEN",
        "last_marked_at": now.isoformat(),
    }


def _mark_entry(entry: dict, market: dict | None, now: datetime) -> dict:
    if not market:
        entry["tracking_status"] = "MARK_UNAVAILABLE"
        entry["last_marked_at"] = now.isoformat()
        return entry
    price = _n(market.get("price_usd"))
    if price <= 0:
        entry["tracking_status"] = "MARK_UNAVAILABLE"
        entry["last_marked_at"] = now.isoformat()
        return entry

    entry_price = _n(entry.get("entry_price_usd"))
    initial_qty = _n(entry.get("initial_quantity"))
    remaining = _n(entry.get("remaining_quantity"), initial_qty)
    realized = _n(entry.get("realized_cash_usd"))
    peak = max(_n(entry.get("peak_price_usd"), entry_price), price)

    if not entry.get("tp50_done") and entry_price > 0 and price >= entry_price * 2.0:
        sold = initial_qty * 0.5
        realized += sold * entry_price * 2.0
        remaining = max(0.0, remaining - sold)
        entry["tp50_done"] = True
        entry["tp50_at"] = now.isoformat()
        entry["tp50_price_usd"] = entry_price * 2.0

    token_value = remaining * price
    total_value = realized + token_value
    allocation = _n(entry.get("allocation_usd"), PAPER_ENTRY_USD)
    pnl_pct = (total_value / allocation - 1.0) * 100.0 if allocation > 0 else 0.0
    drawdown = (price / peak - 1.0) * 100.0 if peak > 0 else 0.0

    entry.update({
        "remaining_quantity": remaining,
        "realized_cash_usd": round(realized, 8),
        "peak_price_usd": peak,
        "current_price_usd": price,
        "current_token_value_usd": round(token_value, 8),
        "current_value_usd": round(total_value, 8),
        "pnl_pct": round(pnl_pct, 4),
        "drawdown_from_peak_pct": round(drawdown, 4),
        "current_liquidity_usd": _n(market.get("liquidity_usd")),
        "tracking_status": "LIQUIDITY_FAILED" if _n(market.get("liquidity_usd")) < THRESHOLDS.min_liquidity_usd else "OPEN",
        "last_marked_at": now.isoformat(),
    })
    return entry


def _paper_totals(entries: dict[str, dict]) -> dict:
    rows = list(entries.values())
    allocated = sum(_n(x.get("allocation_usd")) for x in rows)
    current = sum(_n(x.get("current_value_usd")) for x in rows)
    return {
        "entries": len(rows),
        "verified_entries": sum(x.get("verified_track_record") is True for x in rows),
        "shadow_entries": sum(x.get("paper_mode") == "SHADOW_PAPER_UNVERIFIED_LP" for x in rows),
        "allocated_usd": round(allocated, 4),
        "current_value_usd": round(current, 4),
        "roi_pct": round((current / allocated - 1.0) * 100.0, 4) if allocated else 0.0,
        "tp50_completed": sum(x.get("tp50_done") is True for x in rows),
    }


def _compact_candidate(row: dict) -> dict:
    keep = (
        "candidate_key", "chain", "token", "symbol", "name", "pair_address", "dex", "url",
        "price_usd", "liquidity_usd", "market_cap", "fdv", "pair_age_minutes", "pair_created_at",
        "gain_from_baseline_pct", "gain_basis", "price_change_m5", "price_change_h1", "price_change_h6", "price_change_h24",
        "volume_m5", "volume_h1", "buys_h1", "sells_h1", "holders", "holder_truth_status",
        "top10_ex_system_pct", "largest_non_system_wallet_pct", "distribution_status", "lp_vault_match_count",
        "mint_authority_safe", "freeze_authority_safe", "transfer_restrictions_safe", "lp_integrity_safe",
        "source", "sources", "source_confirmations", "genesis_score", "shadow_score", "shadow_paper_ready",
        "status", "age_band", "extension_band", "safety", "acceleration", "subscores", "measurement_method",
    )
    return {k: row.get(k) for k in keep if k in row}


def run(data_dir: Path | None = None, now: datetime | None = None) -> dict:
    data_dir = data_dir or _data_dir()
    now = now or _now()
    now_epoch = now.timestamp()
    state_path = data_dir / "genesis-state.json"
    paper_path = data_dir / "genesis-paper.json"
    radar_path = data_dir / "genesis-radar.json"
    health_path = data_dir / "genesis-health.json"

    state = _load(state_path, {"version": 1, "records": {}, "mintability_state": {}, "discovery_cursor": {}})
    records = state.get("records") if isinstance(state.get("records"), dict) else {}
    paper = _load(paper_path, {"version": 1, "paper_entry_usd": PAPER_ENTRY_USD, "entries": {}})
    entries = paper.get("entries") if isinstance(paper.get("entries"), dict) else {}

    errors: list[dict] = []
    discovered: list[dict] = []
    next_cursor = dict(state.get("discovery_cursor") or {})
    try:
        discovered, next_cursor = discover_tokens(
            CHAINS,
            limit_per_chain=int(os.getenv("GENESIS_DISCOVERY_LIMIT_PER_CHAIN", "120")),
            start_pages=state.get("discovery_cursor") or {},
            pages_per_run=1,
            max_page=15,
        )
    except Exception as exc:
        errors.append({"stage": "discovery", "error": f"{type(exc).__name__}:{str(exc)[:240]}"})

    max_snapshots = max(20, int(os.getenv("GENESIS_MAX_SNAPSHOTS", "90")))
    selected = sorted(discovered, key=_priority)[:max_snapshots]
    raw_candidates: list[dict] = []
    seen_keys: set[str] = set()

    for discovery in selected:
        chain = str(discovery.get("chain") or "").lower()
        token = str(discovery.get("token") or "").strip()
        if chain not in CHAINS or not token:
            continue
        try:
            snap = snapshot(chain, token)
        except Exception as exc:
            errors.append({"stage": "market_snapshot", "chain": chain, "token": token, "error": f"{type(exc).__name__}:{str(exc)[:160]}"})
            continue
        if not snap or not snap.get("pair_address") or _n(snap.get("price_usd")) <= 0:
            continue
        age_minutes = _pair_age_minutes(snap.get("pair_created_at"), now)
        if age_minutes is None or age_minutes > 10080:
            continue
        candidate_key = _key(chain, token, str(snap["pair_address"]))
        if candidate_key in seen_keys:
            continue
        seen_keys.add(candidate_key)
        target_side = snap.get("target_token_side")
        symbol = discovery.get("symbol") or discovery.get("birdeye_symbol")
        if not symbol:
            symbol = snap.get("base_token_symbol") if target_side == "BASE" else snap.get("quote_token_symbol")
        raw_candidates.append({
            **snap,
            "candidate_key": candidate_key,
            "chain": chain,
            "token": token,
            "symbol": symbol,
            "name": discovery.get("token_name") or discovery.get("name") or discovery.get("birdeye_name"),
            "source": discovery.get("source"),
            "sources": discovery.get("sources") or [discovery.get("source")],
            "source_confirmations": discovery.get("source_confirmations") or 1,
            "pair_age_minutes": round(age_minutes, 2),
            "quality_wallet_buyers": 0,
            "high_confidence_wallet_buyers": 0,
            "organic_acceleration_confirmed": False,
            "organic_social_confirmed": False,
            "lp_integrity_safe": None,
        })

    deep_limit = max(1, int(os.getenv("GENESIS_MAX_SOLANA_DEEP", "18")))
    solana_deep = sorted(
        [x for x in raw_candidates if x.get("chain") == "solana" and _n(x.get("liquidity_usd")) >= THRESHOLDS.min_liquidity_usd and _n(x.get("pair_age_minutes")) <= 1440],
        key=lambda x: _n(x.get("liquidity_usd")),
        reverse=True,
    )[:deep_limit]
    deep_keys = {x["candidate_key"] for x in solana_deep}
    mint_truth: dict[str, dict] = {}
    next_mint_state = state.get("mintability_state") if isinstance(state.get("mintability_state"), dict) else {}
    if solana_deep:
        try:
            mint_truth, next_mint_state = resolve_mintability(
                [str(x.get("token")) for x in solana_deep],
                state=next_mint_state,
                checked_at=now.isoformat(),
            )
        except Exception as exc:
            errors.append({"stage": "mintability", "error": f"{type(exc).__name__}:{str(exc)[:200]}"})

    ranked: list[dict] = []
    for candidate in raw_candidates:
        key = candidate["candidate_key"]
        rec = records.get(key) if isinstance(records.get(key), dict) else {}
        history = list(rec.get("history") or [])

        if key in deep_keys:
            token = str(candidate.get("token"))
            truth = mint_truth.get(token) or (next_mint_state.get("tokens") or {}).get(token) or {}
            mint_verified = truth.get("mintability_verified") is True
            mint_safe = mint_verified and truth.get("mintable") is False and truth.get("mint_authority") is None
            freeze = truth.get("freeze_authority")
            candidate["mint_authority_safe"] = bool(mint_safe)
            candidate["freeze_authority_safe"] = bool(mint_verified and freeze is None)
            candidate["transfer_restrictions_safe"] = True if truth.get("program_owner") == LEGACY_TOKEN_PROGRAM and mint_safe and freeze is None else None
            candidate["mintability_status"] = truth.get("status")

            try:
                holders = fetch_rpc_holder_truth(token, timeout=int(os.getenv("GENESIS_HOLDER_TIMEOUT", "18")))
            except Exception as exc:
                holders = {"verified": False, "status": f"ERROR:{type(exc).__name__}"}
            if holders.get("verified") is True:
                candidate["holders"] = int(holders.get("holder_count") or 0)
            candidate["holder_truth_status"] = holders.get("status")

            distribution = solana_distribution_truth(token, candidate)
            candidate["distribution_status"] = distribution.get("status")
            candidate["lp_vault_match_count"] = distribution.get("lp_vault_match_count", 0)
            if distribution.get("verified") is True:
                candidate["top10_ex_system_pct"] = distribution.get("top10_ex_system_pct")
                candidate["largest_non_system_wallet_pct"] = distribution.get("largest_non_system_wallet_pct")
        else:
            candidate.setdefault("mint_authority_safe", None)
            candidate.setdefault("freeze_authority_safe", None)
            candidate.setdefault("transfer_restrictions_safe", None)
            candidate.setdefault("holders", None)
            candidate.setdefault("top10_ex_system_pct", None)
            candidate.setdefault("largest_non_system_wallet_pct", None)
            candidate.setdefault("holder_truth_status", "NOT_DEEP_VERIFIED_THIS_RUN")
            candidate.setdefault("distribution_status", "NOT_DEEP_VERIFIED_THIS_RUN")

        candidate.update(_history_features(rec, candidate, now_epoch))

        first_price = _n(rec.get("first_price_usd")) or _n(candidate.get("price_usd"))
        first_seen_gain = (_n(candidate.get("price_usd")) / first_price - 1.0) * 100.0 if first_price > 0 else 0.0
        provider_gain = max(0.0, _n(candidate.get("price_change_h24")), _n(candidate.get("price_change_h6")), _n(candidate.get("price_change_h1")))
        candidate["gain_from_baseline_pct"] = round(max(first_seen_gain, provider_gain), 4)
        candidate["gain_basis"] = "MAX_FIRST_SEEN_AND_PROVIDER_WINDOW_GAIN"

        scored = genesis_score(candidate)
        shadow = _shadow_score(candidate, scored)
        candidate.update(scored)
        candidate["shadow_score"] = shadow
        candidate["shadow_paper_ready"] = _shadow_ready(candidate, scored, shadow)
        ranked.append(candidate)

        history.append({
            "ts": now_epoch,
            "price_usd": candidate.get("price_usd"),
            "liquidity_usd": candidate.get("liquidity_usd"),
            "volume_m5": candidate.get("volume_m5"),
            "holders": candidate.get("holders"),
            "top10_ex_system_pct": candidate.get("top10_ex_system_pct"),
            "largest_non_system_wallet_pct": candidate.get("largest_non_system_wallet_pct"),
        })
        records[key] = {
            "first_seen_at": rec.get("first_seen_at") or now.isoformat(),
            "first_price_usd": first_price,
            "last_seen_at": now.isoformat(),
            "last_seen_epoch": now_epoch,
            "chain": candidate.get("chain"),
            "token": candidate.get("token"),
            "pair_address": candidate.get("pair_address"),
            "history": history[-HISTORY_LIMIT:],
        }

    ranked.sort(key=lambda x: (_n(x.get("shadow_score")), _n(x.get("genesis_score"))), reverse=True)
    current_by_key = {x["candidate_key"]: x for x in ranked}
    new_entries: list[dict] = []

    for candidate in ranked:
        mode = _paper_mode(candidate)
        if not mode or candidate["candidate_key"] in entries:
            continue
        entry = _open_paper_entry(candidate, now)
        entries[candidate["candidate_key"]] = entry
        new_entries.append(dict(entry))

    for key, entry in list(entries.items()):
        market = current_by_key.get(key)
        if market is None:
            try:
                market = snapshot(str(entry.get("chain")), str(entry.get("token")), str(entry.get("pair_address")))
            except Exception:
                market = None
        entries[key] = _mark_entry(entry, market, now)

    cutoff = now_epoch - 8 * 86400
    records = {
        k: v for k, v in records.items()
        if _n((v or {}).get("last_seen_epoch"), now_epoch) >= cutoff or k in entries
    }

    diagnostics = discovery_diagnostics()
    state = {
        "version": 2,
        "updated_at": now.isoformat(),
        "records": records,
        "mintability_state": next_mint_state,
        "discovery_cursor": next_cursor,
    }
    paper = {
        "version": 2,
        "updated_at": now.isoformat(),
        "paper_entry_usd": PAPER_ENTRY_USD,
        "real_money_execution": False,
        "truth_rule": "SHADOW_PAPER_NEVER_COUNTS_AS_VERIFIED_TRACK_RECORD",
        "totals": _paper_totals(entries),
        "entries": entries,
    }

    counts = {
        "discovered": len(discovered),
        "snapshotted_genesis": len(raw_candidates),
        "solana_deep_verified_attempted": len(solana_deep),
        "watch_or_better": sum(x.get("status") not in {"IGNORE", "BLOCKED", "OUTSIDE_GENESIS", "DISCOVERY_ONLY"} for x in ranked),
        "evidence_ready_or_better": sum(_n(x.get("genesis_score")) >= 65 for x in ranked),
        "shadow_paper_ready": sum(x.get("shadow_paper_ready") is True for x in ranked),
        "new_paper_entries": len(new_entries),
        "paper_entries_total": len(entries),
        "late_no_chase": sum(x.get("extension_band") == "LATE_NO_CHASE" for x in ranked),
    }
    radar = {
        "version": 2,
        "generated_at": now.isoformat(),
        "status": "LIVE",
        "lane": "GENESIS_RADAR_ISOLATED_NEW_COIN_RESEARCH",
        "paper_entry_usd": PAPER_ENTRY_USD,
        "automatic_real_buy": False,
        "production_track_record_contamination": False,
        "scope": {"discovery": list(CHAINS), "deep_paper_lane": ["solana"], "new_entry_age_max_hours": 24},
        "counts": counts,
        "new_paper_entries": new_entries,
        "candidates": [_compact_candidate(x) for x in ranked[:100]],
        "discovery_diagnostics": diagnostics,
        "errors": errors[-40:],
    }
    health = {
        "version": 1,
        "generated_at": now.isoformat(),
        "status": "LIVE" if raw_candidates else "DEGRADED_NO_GENESIS_SNAPSHOTS",
        "paper_entry_usd": PAPER_ENTRY_USD,
        "counts": counts,
        "discovery_health": diagnostics.get("health") if isinstance(diagnostics, dict) else None,
        "errors_count": len(errors),
    }

    _write(state_path, state)
    _write(paper_path, paper)
    _write(radar_path, radar)
    _write(health_path, health)
    return radar


def main() -> None:
    payload = run()
    print("GENESIS_RADAR_LIVE", payload.get("counts"))


if __name__ == "__main__":
    main()
