from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MIN_PRODUCTION_LIQUIDITY_USD = 50_000.0
STAGES = (
    "OBSERVE",
    "EARLY_WATCH",
    "PRE_BUY",
    "ENTRY_ZONE",
    "HOLD_ADD",
    "TAKE_PROFIT_WARNING",
    "EXIT_RISK_OFF",
)


def _f(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _read(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _base_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    for quote in ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI", "USD"):
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)]
    return s


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _identity_for(identity_payload: dict, symbol: str) -> dict:
    base = _base_symbol(symbol)
    best = {}
    for row in _walk_dicts(identity_payload):
        row_symbol = str(row.get("symbol") or row.get("base_symbol") or "").upper()
        if row_symbol not in {symbol.upper(), base}:
            continue
        if len(row) > len(best):
            best = row
    return best


def _bool(row: dict, *keys: str) -> bool:
    return any(row.get(k) is True for k in keys)


def _liquidity(row: dict) -> float:
    keys = (
        "verified_execution_liquidity_usd",
        "execution_liquidity_usd",
        "selected_pair_liquidity_usd",
        "pair_liquidity_usd",
        "liquidity_usd",
    )
    return max((_f(row.get(k)) for k in keys), default=0.0)


def classify(candidate: dict, identity: dict, previous_stage: str | None = None) -> dict:
    features = set(candidate.get("shadow_features") or [])
    dispersion = _f(candidate.get("price_dispersion_ratio"))
    volume_step = _f(candidate.get("volume_step_multiple"))
    regional_gap = _f(candidate.get("regional_lead_gap_pct"))
    venues = int(candidate.get("usd_like_venues") or 0)

    exact_identity = _bool(identity, "identity_verified", "exact_pair_verified", "dex_verified") or str(identity.get("identity_status") or "").upper() == "DEX_VERIFIED"
    liquidity = _liquidity(identity)
    liquidity_verified = liquidity >= MIN_PRODUCTION_LIQUIDITY_USD

    blockers = []
    if not exact_identity:
        blockers.append("EXACT_PAIR_IDENTITY_NOT_VERIFIED")
    if liquidity <= 0:
        blockers.append("VERIFIED_EXECUTION_LIQUIDITY_MISSING")
    elif not liquidity_verified:
        blockers.append("VERIFIED_EXECUTION_LIQUIDITY_BELOW_50K")

    composite = "MARKET_FRAGMENTATION_COMPOSITE_SHADOW" in features
    early = bool(features)
    persistent_confirmation = composite or len(features) >= 2
    price_structure_healthy = 1.0 <= dispersion <= 1.35 or dispersion == 0
    risk_dislocation = dispersion >= 1.75
    volume_confirmed = volume_step >= 1.5

    stage = "OBSERVE"
    reasons = []
    if early:
        stage = "EARLY_WATCH"
        reasons.append("EARLY_FRAGMENTATION_OR_ACCELERATION")
    if persistent_confirmation:
        stage = "PRE_BUY"
        reasons.append("MULTI_SIGNAL_PERSISTENCE")

    higher_gate = exact_identity and liquidity_verified
    if higher_gate and persistent_confirmation and volume_confirmed and price_structure_healthy:
        stage = "ENTRY_ZONE"
        reasons.append("STRICT_IDENTITY_LIQUIDITY_AND_MOMENTUM_CONFIRMATION")
    if higher_gate and previous_stage in {"ENTRY_ZONE", "HOLD_ADD"} and persistent_confirmation and price_structure_healthy:
        stage = "HOLD_ADD"
        reasons.append("CONFIRMATION_PERSISTS_WITHOUT_DANGEROUS_DISLOCATION")

    if previous_stage in {"ENTRY_ZONE", "HOLD_ADD", "TAKE_PROFIT_WARNING"}:
        if risk_dislocation or (volume_step > 0 and volume_step < 0.8):
            stage = "TAKE_PROFIT_WARNING"
            reasons.append("POST_ENTRY_DISPERSION_OR_VOLUME_DETERIORATION")
        if (liquidity > 0 and liquidity < MIN_PRODUCTION_LIQUIDITY_USD) or not exact_identity:
            stage = "EXIT_RISK_OFF"
            reasons.append("POST_ENTRY_HARD_GATE_INVALIDATED")

    return {
        "stage": stage,
        "shadow_only": True,
        "research_only": True,
        "affects_score": False,
        "actionable": False,
        "automatic_buy": False,
        "automatic_sell": False,
        "evidence": {
            "shadow_features": sorted(features),
            "price_dispersion_ratio": dispersion,
            "regional_lead_gap_pct": regional_gap,
            "volume_step_multiple": volume_step,
            "usd_like_venues": venues,
            "exact_pair_identity_verified": exact_identity,
            "verified_execution_liquidity_usd": liquidity if liquidity > 0 else None,
            "production_liquidity_reference_usd": MIN_PRODUCTION_LIQUIDITY_USD,
        },
        "blockers": blockers,
        "reasons": reasons,
    }


def _update_state(previous: dict, rows: list[dict], now: str) -> dict:
    first = previous.get("first_stage_observed") if isinstance(previous.get("first_stage_observed"), dict) else {}
    first = {k: dict(v) if isinstance(v, dict) else {} for k, v in first.items()}
    latest = previous.get("latest_stage") if isinstance(previous.get("latest_stage"), dict) else {}
    latest = dict(latest)
    new_events = 0
    for row in rows:
        symbol = row["symbol"]
        stage = row["stage"]
        latest[symbol] = {"stage": stage, "observed_at": row.get("observed_at") or now}
        if stage == "OBSERVE":
            continue
        bucket = first.setdefault(symbol, {})
        if stage not in bucket:
            bucket[stage] = {
                "observed_at": row.get("observed_at") or now,
                "immutable": True,
                "evidence_at_first_observation": row.get("evidence"),
            }
            new_events += 1
    return {
        "version": 1,
        "updated_at": now,
        "mode": "FORWARD_ONLY_CEX_MARKET_TIMING_SHADOW_STATE_V1",
        "research_only": True,
        "production_effect": False,
        "no_hindsight": True,
        "new_stage_events": new_events,
        "first_stage_observed": first,
        "latest_stage": latest,
    }


def run(out: Path, now: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc).isoformat()
    frag = _read(out / "cex-market-fragmentation-research.json", {})
    identity = _read(out / "cex-spot-identity-radar.json", {})
    previous = _read(out / "cex-market-timing-shadow-state.json", {})
    previous_latest = previous.get("latest_stage") if isinstance(previous.get("latest_stage"), dict) else {}

    rows = []
    for candidate in frag.get("current_shadow_candidates") or []:
        symbol = str(candidate.get("symbol") or "").upper()
        if not symbol:
            continue
        prev = previous_latest.get(symbol) if isinstance(previous_latest.get(symbol), dict) else {}
        result = classify(candidate, _identity_for(identity, symbol), prev.get("stage"))
        rows.append({"symbol": symbol, "observed_at": candidate.get("observed_at") or now, **result})

    order = {name: i for i, name in enumerate(STAGES)}
    rows.sort(key=lambda r: order.get(r["stage"], 0), reverse=True)
    state = _update_state(previous, rows, now)
    (out / "cex-market-timing-shadow-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

    counts = {stage: sum(1 for row in rows if row["stage"] == stage) for stage in STAGES}
    payload = {
        "version": 1,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_CEX_MARKET_TIMING_SHADOW_V1",
        "research_only": True,
        "shadow_only": True,
        "production_effect": False,
        "affects_score": False,
        "actionable": False,
        "automatic_buy": False,
        "automatic_sell": False,
        "production_thresholds_modified": False,
        "liquidity_minimum_modified": False,
        "identity_rules_modified": False,
        "truth_contract": {
            "no_hindsight": True,
            "stage_first_observation_is_forward_only_and_immutable": True,
            "entry_or_hold_requires_exact_pair_identity": True,
            "entry_or_hold_requires_verified_execution_liquidity_gte_50000": True,
            "missing_identity_or_liquidity_fails_closed": True,
            "timing_stage_never_changes_production_score": True,
            "timing_stage_never_triggers_automatic_trade": True,
            "retrospective_lsk_case_never_backfills_stage_history": True,
        },
        "stage_definitions": list(STAGES),
        "counts": counts,
        "rows": rows[:200],
        "new_forward_stage_events": state.get("new_stage_events", 0),
    }
    (out / "cex-market-timing-shadow.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(Path("data")), indent=2))
