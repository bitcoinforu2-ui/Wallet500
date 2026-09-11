from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA = Path("data")
EVIDENCE = DATA / "revival-prewaking-wallet-evidence.json"
STATE = DATA / "wallet-accumulation-prospective-state.json"
REPORT = DATA / "wallet-accumulation-prospective.json"
VERSION = "WALLET500_WALLET_ACCUMULATION_PROSPECTIVE_V1"
MODE = "RESEARCH_ONLY_EXACT_PAIR_PROSPECTIVE_WALLET_ACCUMULATION"
HORIZON_SECONDS = 24 * 60 * 60


def _load(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return default


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _f(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _exact_pair_price(mint: str, pair: str) -> float | None:
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair}"
    req = Request(url, headers={"User-Agent": "Wallet500/1.0"})
    try:
        with urlopen(req, timeout=15) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    candidates = raw.get("pairs") if isinstance(raw, dict) else None
    if not isinstance(candidates, list):
        return None
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if str(item.get("chainId") or "").lower() != "solana":
            continue
        if str(item.get("pairAddress") or "").lower() != pair.lower():
            continue
        base = str((item.get("baseToken") or {}).get("address") or "")
        quote = str((item.get("quoteToken") or {}).get("address") or "")
        if mint not in {base, quote}:
            continue
        price = _f(item.get("priceUsd"))
        if price is not None and price > 0:
            return price
    return None


def _wallet_snapshot(row: dict) -> dict:
    windows = row.get("windows") if isinstance(row.get("windows"), dict) else {}
    out = {}
    for name in ("h1", "h4", "h24"):
        src = windows.get(name) if isinstance(windows.get(name), dict) else {}
        out[name] = {
            "resolved_swaps": int(src.get("resolved_swaps") or 0),
            "unique_buyers": int(src.get("unique_buyers") or 0),
            "unique_sellers": int(src.get("unique_sellers") or 0),
            "first_seen_buyers_since_monitor_t0": int(src.get("first_seen_buyers_since_monitor_t0") or 0),
            "net_accumulating_wallets": int(src.get("net_accumulating_wallets") or 0),
            "net_distributing_wallets": int(src.get("net_distributing_wallets") or 0),
            "wallet_buy_sell_ratio": _f(src.get("wallet_buy_sell_ratio")),
        }
    return out


def _research_accumulation_marker(snapshot: dict) -> bool:
    # Experimental marker only. It is never consumed by production or alert logic.
    for name in ("h1", "h4"):
        w = snapshot.get(name) or {}
        ratio = _f(w.get("wallet_buy_sell_ratio"))
        if (
            int(w.get("resolved_swaps") or 0) >= 3
            and int(w.get("net_accumulating_wallets") or 0) > int(w.get("net_distributing_wallets") or 0)
            and int(w.get("unique_buyers") or 0) >= int(w.get("unique_sellers") or 0)
            and ratio is not None and ratio > 1.0
        ):
            return True
    return False


def _new_state(evidence: dict, now: datetime, price_fetcher) -> dict:
    bridge = ((evidence.get("selection_policy") or {}).get("wallet_insight_priority_bridge") or {})
    selected = [str(x) for x in (bridge.get("selected_tokens") or []) if x]
    rows = {str(r.get("token_address") or ""): r for r in (evidence.get("tokens") or []) if isinstance(r, dict)}
    cohort = []
    for mint in selected[:8]:
        row = rows.get(mint) or {}
        pair = str(row.get("exact_pair") or "")
        if not pair:
            continue
        snap = _wallet_snapshot(row)
        price = price_fetcher(mint, pair)
        cohort.append({
            "identity": f"solana|{mint}|{pair}",
            "token_address": mint,
            "symbol": row.get("symbol"),
            "exact_pair": pair,
            "enrolled_at": _iso(now),
            "baseline_price_usd": price,
            "baseline_wallet_snapshot": snap,
            "first_research_accumulation_marker_at": _iso(now) if _research_accumulation_marker(snap) else None,
            "observations": [],
        })
    return {
        "version": VERSION,
        "mode": MODE,
        "cohort_started_at": _iso(now),
        "horizon_seconds": HORIZON_SECONDS,
        "locked_cohort": True,
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "cohort": cohort,
    }


def run(*, now: datetime | None = None, price_fetcher=_exact_pair_price) -> dict:
    now = now or _now()
    evidence = _load(EVIDENCE, {})
    state = _load(STATE, {})
    if state.get("version") != VERSION or not state.get("locked_cohort"):
        state = _new_state(evidence, now, price_fetcher)

    rows = {str(r.get("token_address") or ""): r for r in (evidence.get("tokens") or []) if isinstance(r, dict)}
    for item in state.get("cohort") or []:
        mint = str(item.get("token_address") or "")
        pair = str(item.get("exact_pair") or "")
        row = rows.get(mint) or {}
        snap = _wallet_snapshot(row)
        price = price_fetcher(mint, pair) if mint and pair else None
        marker = _research_accumulation_marker(snap)
        if marker and not item.get("first_research_accumulation_marker_at"):
            item["first_research_accumulation_marker_at"] = _iso(now)
        base = _f(item.get("baseline_price_usd"))
        ret = ((price / base) - 1.0) * 100.0 if price is not None and base else None
        obs = {
            "observed_at": _iso(now),
            "source_generated_at": evidence.get("generated_at"),
            "wallet_status": row.get("status"),
            "coverage_quality": (row.get("coverage") or {}).get("coverage_quality"),
            "research_accumulation_marker": marker,
            "wallet_snapshot": snap,
            "price_usd": price,
            "return_from_baseline_pct": ret,
        }
        previous = item.setdefault("observations", [])
        if not previous or previous[-1].get("source_generated_at") != obs["source_generated_at"]:
            previous.append(obs)

    started = _dt(state.get("cohort_started_at")) or now
    elapsed = max(0, int((now - started).total_seconds()))
    complete = elapsed >= int(state.get("horizon_seconds") or HORIZON_SECONDS)
    summaries = []
    for item in state.get("cohort") or []:
        returns = [_f(o.get("return_from_baseline_pct")) for o in (item.get("observations") or [])]
        returns = [x for x in returns if x is not None]
        summaries.append({
            "identity": item.get("identity"),
            "symbol": item.get("symbol"),
            "baseline_price_usd": item.get("baseline_price_usd"),
            "first_research_accumulation_marker_at": item.get("first_research_accumulation_marker_at"),
            "observations": len(item.get("observations") or []),
            "max_return_pct": max(returns) if returns else None,
            "min_return_pct": min(returns) if returns else None,
            "latest_return_pct": returns[-1] if returns else None,
        })

    report = {
        "version": VERSION,
        "mode": MODE,
        "generated_at": _iso(now),
        "phase": "COMPLETE_24H" if complete else "COLLECTING_24H",
        "elapsed_seconds": elapsed,
        "horizon_seconds": HORIZON_SECONDS,
        "cohort_size": len(state.get("cohort") or []),
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "truth_contract": {
            "cohort_locked_at_first_run": True,
            "exact_chain_token_pair_required": True,
            "dex_price_must_match_exact_pair_and_token": True,
            "research_marker_never_promotes_candidate": True,
            "research_marker_never_changes_production_thresholds": True,
            "future_observations_appended_only_after_enrollment": True,
            "missing_price_is_null_not_guessed": True,
        },
        "experimental_marker_definition": "h1_or_h4: resolved_swaps>=3 AND net_accumulating>net_distributing AND unique_buyers>=unique_sellers AND buy_sell_ratio>1",
        "tokens": summaries,
    }
    _write(STATE, state)
    _write(REPORT, report)
    return report


def main() -> None:
    report = run()
    print(json.dumps({"phase": report.get("phase"), "cohort_size": report.get("cohort_size"), "elapsed_seconds": report.get("elapsed_seconds")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
