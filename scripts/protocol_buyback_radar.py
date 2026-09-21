from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/protocol-buyback-registry.json"
CONFIG = ROOT / "data/unified-watch-config.json"
EVENTS = ROOT / "data/close-watch-events.json"
OUT = ROOT / "data/protocol-buyback-radar.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
HARD_RISK_KINDS = {
    "identity_mismatch",
    "price_source_mismatch",
    "honeypot_or_transfer_block",
    "extreme_tax",
    "mint_or_freeze_risk",
    "critical_liquidity_drain",
    "unverified_contract_migration",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def chain_name(value) -> str:
    raw = str(value or "").strip().lower()
    return ALIASES.get(raw, raw)


def norm_addr(chain: str, value) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def identity(row: dict):
    c = chain_name(row.get("network") or row.get("chain"))
    t = norm_addr(c, row.get("contract") or row.get("token_address"))
    p = norm_addr(c, row.get("pair") or row.get("pair_address"))
    if not c or not t or not p:
        return None
    return c, t, p, f"{c}:{t}:{p}"


def parse_ts(value):
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def merged_entries(registry: dict, config: dict) -> list[dict]:
    """Registry is the generic source of truth; config sensors remain compatible."""
    defaults = registry.get("defaults") if isinstance(registry.get("defaults"), dict) else {}
    rows = []
    seen = set()

    for raw in registry.get("entries") or []:
        if not isinstance(raw, dict) or raw.get("active") is not True:
            continue
        row = dict(defaults)
        row.update(raw)
        i = identity(row)
        if i is None or i[3] in seen:
            continue
        seen.add(i[3])
        rows.append(row)

    for token in config.get("tokens") or []:
        if not isinstance(token, dict):
            continue
        sensor = (token.get("free_intel") or {}).get("buyback_sensor")
        if not isinstance(sensor, dict) or sensor.get("enabled") is not True:
            continue
        i = identity(token)
        if i is None or i[3] in seen:
            continue
        seen.add(i[3])
        row = dict(defaults)
        row.update(token)
        row["protocol_name"] = sensor.get("protocol_name") or token.get("symbol")
        row["buyback_sensor"] = sensor
        rows.append(row)

    return rows


def current_events(events: list[dict], key: str, window_minutes: float, current: datetime):
    out = []
    for e in events:
        if not isinstance(e, dict):
            continue
        i = identity(e)
        if i is None or i[3] != key:
            continue
        ts = parse_ts(e.get("event_time") or e.get("observed_at"))
        if ts is None:
            continue
        age = (current - ts).total_seconds() / 60.0
        if -2 <= age <= window_minutes:
            out.append((ts, e))
    out.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in out]


def newest(events: list[dict], kind: str):
    return next((e for e in events if str(e.get("kind") or "") == kind), None)


def newest_market(events: list[dict]):
    return next(
        (
            e
            for e in events
            if e.get("kind") == "verified_market_snapshot"
            and e.get("identity_verified") is True
        ),
        None,
    )


def positive_family_count(events: list[dict]) -> int:
    families = set()
    for e in events:
        if num(e.get("direction"), 0.0) <= 0:
            continue
        if num(e.get("strength"), 0.0) < 30 or num(e.get("confidence"), 0.0) < 60:
            continue
        fam = str(e.get("family") or "")
        if fam in {"supply_tokenomics", "fundamental_usage", "market_microstructure"}:
            continue
        if fam:
            families.add(fam)
    return len(families)


def evaluate(entry: dict, all_events: list[dict], current: datetime | None = None) -> dict:
    current = current or datetime.now(timezone.utc)
    i = identity(entry)
    if i is None:
        return {
            "status": "BLOCKED_IDENTITY",
            "candidate": False,
            "blockers": ["EXACT_CHAIN_CONTRACT_PAIR_MISSING"],
        }

    chain, contract, pair, key = i
    window = float(entry.get("fusion_window_minutes") or 180)
    events = current_events(all_events, key, window, current)

    hard = sorted(
        {
            str(e.get("kind") or "hard_risk")
            for e in events
            if e.get("hard_risk") is True or str(e.get("kind") or "") in HARD_RISK_KINDS
        }
    )

    market = newest_market(events)
    execution = newest(events, "buyback_execution")
    acceleration = newest(events, "buyback_acceleration")
    revenue = next(
        (
            e
            for e in events
            if e.get("kind") == "revenue_change" and e.get("lead_signal") is True
        ),
        None,
    )

    min_liq = float(entry.get("min_liquidity_usd") or 50000)
    min_vol = float(entry.get("min_volume_h1_usd") or 15000)
    min_activity = int(entry.get("min_activity_h1") or 50)
    min_ratio = float(entry.get("min_buy_sell_ratio") or 1.2)
    pre_threshold = float(entry.get("radar_pre_execution_score") or 38)
    exec_threshold = float(entry.get("radar_execution_score") or 50)

    score = 0.0
    reasons = []
    blockers = []
    stage = "WATCH"

    execution_usd = 0.0
    multiple7 = None
    pressure_bps = None
    pressure_liq_pct = None
    if execution:
        execution_usd = num(
            execution.get("observed_execution_delta_usd"),
            num(execution.get("latest_buyback_usd"), 0.0),
        ) or 0.0
        multiple7 = num(execution.get("multiple_vs_7d"))
        pressure_bps = num(execution.get("buyback_pressure_bps_mcap"))
        pressure_liq_pct = num(execution.get("buyback_to_liquidity_pct"))
        score += 20
        reasons.append(f"BUYBACK_EXECUTION_{execution_usd:.0f}")
        if execution_usd >= 250_000:
            score += 5
        if execution_usd >= 1_000_000:
            score += 10
        if execution_usd >= 2_000_000:
            score += 5
        if execution.get("cross_source_corroborated") is True:
            score += 5
            reasons.append("CROSS_SOURCE_CORROBORATED")

    if acceleration:
        multiple7 = num(acceleration.get("multiple_vs_7d"), multiple7)
    if multiple7 is not None and multiple7 >= 1.25:
        score += 5
        reasons.append(f"BUYBACK_ACCEL_{multiple7:.2f}X")
        if multiple7 >= 1.5:
            score += 5
        if multiple7 >= 2.0:
            score += 5

    if pressure_bps is not None and pressure_bps >= 2:
        score += 5
        reasons.append(f"MCAP_PRESSURE_{pressure_bps:.2f}BPS")
        if pressure_bps >= 5:
            score += 5
        if pressure_bps >= 10:
            score += 5

    if pressure_liq_pct is not None and pressure_liq_pct >= 5:
        score += 5
        reasons.append(f"LIQ_PRESSURE_{pressure_liq_pct:.2f}PCT")
        if pressure_liq_pct >= 10:
            score += 5

    expected_buyback = 0.0
    revenue_multiple = None
    if revenue:
        expected_buyback = num(revenue.get("expected_buyback_funding_usd"), 0.0) or 0.0
        revenue_multiple = num(revenue.get("revenue_multiple_vs_7d"))
        score += 10
        reasons.append(f"REVENUE_FUNDS_BUYBACK_{expected_buyback:.0f}")
        if revenue_multiple is not None and revenue_multiple >= 1.5:
            score += 5
            reasons.append(f"REVENUE_ACCEL_{revenue_multiple:.2f}X")

    market_confirmed = False
    late_extension = False
    market_view = {}
    if market:
        liq = num(market.get("liquidity_usd"), 0.0) or 0.0
        vol = num(market.get("volume_h1_usd"), 0.0) or 0.0
        buys = int(num(market.get("buys_h1"), 0.0) or 0)
        sells = int(num(market.get("sells_h1"), 0.0) or 0)
        activity = buys + sells
        ratio = (buys + 1.0) / (sells + 1.0)
        h1 = num(market.get("price_change_h1_pct"), 0.0) or 0.0
        h24 = num(market.get("price_change_h24_pct"), 0.0) or 0.0
        market_view = {
            "price_usd": num(market.get("price_usd")),
            "liquidity_usd": liq,
            "volume_h1_usd": vol,
            "buys_h1": buys,
            "sells_h1": sells,
            "buy_sell_ratio": round(ratio, 4),
            "price_change_h1_pct": h1,
            "price_change_h24_pct": h24,
        }
        if liq >= min_liq:
            score += 5
            reasons.append("LIQUIDITY_OK")
        else:
            blockers.append("LIQUIDITY_BELOW_RADAR_MINIMUM")
        if vol >= min_vol:
            score += 5
            reasons.append("VOLUME_ACTIVE")
        if activity >= min_activity:
            score += 5
            reasons.append("ACTIVITY_ACTIVE")
        if ratio >= min_ratio:
            score += 5
            reasons.append(f"BUY_PRESSURE_{ratio:.2f}X")
            if ratio >= 2.0:
                score += 3
        market_confirmed = bool(
            liq >= min_liq
            and vol >= min_vol
            and activity >= min_activity
            and ratio >= min_ratio
        )
        max_h1 = float(entry.get("max_h1_extension_pct") or 25)
        max_h24 = float(entry.get("max_h24_extension_pct") or 150)
        late_extension = h1 > max_h1 or h24 > max_h24
        if late_extension:
            score -= 10
            reasons.append("PRICE_ALREADY_EXTENDED")
    else:
        blockers.append("CURRENT_EXACT_MARKET_SNAPSHOT_MISSING")

    other_families = positive_family_count(events)
    if other_families:
        score += min(10, other_families * 2)
        reasons.append(f"OTHER_POSITIVE_FAMILIES_{other_families}")

    negative_liq = next(
        (
            e
            for e in events
            if e.get("kind") == "liquidity_change"
            and num(e.get("direction"), 0.0) < 0
        ),
        None,
    )
    if negative_liq:
        score -= 12
        reasons.append("LIQUIDITY_DETERIORATION")

    score = max(0.0, min(100.0, score))

    if hard:
        blockers.append("HARD_RISK_PRESENT")
    if execution:
        stage = "EXECUTION_CONFIRMED" if market_confirmed else "EXECUTION_WATCH"
        candidate = bool(score >= exec_threshold and market_confirmed and not hard)
    elif revenue:
        stage = "PRE_EXECUTION_FUNDING_PRESSURE"
        candidate = bool(score >= pre_threshold and market_confirmed and not hard)
    else:
        candidate = False

    if candidate and late_extension:
        stage += "_EXTENDED"
    priority = "HIGHEST" if candidate and not late_extension else "HIGH" if candidate else "RESEARCH"

    return {
        "id": entry.get("id"),
        "protocol_name": entry.get("protocol_name"),
        "symbol": str(entry.get("symbol") or "").upper(),
        "network": chain,
        "contract": contract,
        "pair": pair,
        "dex_url": entry.get("dex_url") or "",
        "identity_key": key,
        "status": stage,
        "radar_score": round(score, 1),
        "candidate": candidate,
        "priority": priority,
        "close_watch": "HIGHEST" if candidate else "RESEARCH",
        "collector_priority": 1 if candidate else 5,
        "first_seen_at": (
            (execution or revenue or market or {}).get("event_time")
            or (execution or revenue or market or {}).get("observed_at")
        ),
        "reasons": list(dict.fromkeys(reasons)),
        "blockers": list(dict.fromkeys(blockers)),
        "hard_risks": hard,
        "market_confirmed": market_confirmed,
        "late_extension": late_extension,
        "execution": {
            "observed_execution_delta_usd": round(execution_usd, 2),
            "multiple_vs_7d": multiple7,
            "buyback_pressure_bps_mcap": pressure_bps,
            "buyback_to_liquidity_pct": pressure_liq_pct,
        },
        "funding": {
            "expected_buyback_funding_usd": round(expected_buyback, 2),
            "revenue_multiple_vs_7d": revenue_multiple,
        },
        "market": market_view,
        "other_positive_families": other_families,
        "candidate_type": "PROTOCOL_BUYBACK_PRESSURE",
        "research_only": True,
        "direct_buy_eligible": False,
        "telegram_eligible": False,
        "telegram_policy": "FINAL_BUY_ONLY_VIA_CANONICAL_ENGINE",
        "truth_contract": {
            "exact_identity_required": True,
            "ticker_only_mapping_forbidden": True,
            "buyback_signal_is_not_buy": True,
            "revenue_signal_does_not_prove_execution": True,
            "hard_risk_blocks_escalation": True,
            "current_market_confirmation_required": True,
            "no_direct_telegram": True,
        },
    }


def main() -> int:
    registry = load(REGISTRY, {"defaults": {}, "entries": []})
    config = load(CONFIG, {"tokens": []})
    event_doc = load(EVENTS, {"events": []})
    events = [e for e in (event_doc.get("events") or []) if isinstance(e, dict)]
    current = datetime.now(timezone.utc)

    entries = merged_entries(registry, config)
    rows = [evaluate(entry, events, current=current) for entry in entries]
    candidates = [row for row in rows if row.get("candidate") is True]
    candidates.sort(
        key=lambda x: (
            0 if str(x.get("status") or "").startswith("EXECUTION_CONFIRMED") else 1,
            -float(x.get("radar_score") or 0),
            -float((x.get("market") or {}).get("liquidity_usd") or 0),
        )
    )

    out = {
        "version": 1,
        "generated_at": current.isoformat(),
        "mode": "GENERIC_EXACT_IDENTITY_BUYBACK_PRESSURE_RADAR",
        "registry_entries": len(entries),
        "evaluated": len(rows),
        "candidate_count": len(candidates),
        "execution_candidate_count": sum(
            str(x.get("status") or "").startswith("EXECUTION_CONFIRMED")
            for x in candidates
        ),
        "pre_execution_candidate_count": sum(
            str(x.get("status") or "").startswith("PRE_EXECUTION")
            for x in candidates
        ),
        "truth_contract": {
            "candidate_is_research_close_watch_not_buy": True,
            "no_direct_telegram": True,
            "canonical_buy_gate_unchanged": True,
        },
        "candidates": candidates,
        "evaluations": rows,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "registry_entries": len(entries),
        "candidate_count": len(candidates),
        "execution_candidate_count": out["execution_candidate_count"],
        "pre_execution_candidate_count": out["pre_execution_candidate_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
