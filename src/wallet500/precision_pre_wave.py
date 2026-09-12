from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
MODE = "MANUAL_REVIEW_PRECISION_PRE_WAVE_6OF7_V1"
MIN_AGE_DAYS = 180
MIN_LIQUIDITY_USD = 50_000.0
MIN_SOURCE_LANES = 2
MIN_EARLY_SCORE = 35.0
MIN_EARLY_CONFIRMATIONS = 2
MIN_CURRENT_CONFIRMATIONS = 2
MIN_VOLUME_H1_USD = 10_000.0
MIN_TURNOVER_H1 = 0.08
MIN_ACTIVITY_H1 = 20
MAX_SOURCE_AGE_SECONDS = 45 * 60
EARLY_MAX_MOVE_PCT = 20.0
MAX_REVIEW_MOVE_PCT = 35.0


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _parse_dt(v: Any) -> datetime | None:
    raw = str(v or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fresh(stamp: Any, now: datetime) -> bool:
    dt = _parse_dt(stamp)
    if dt is None:
        return False
    age = (now - dt).total_seconds()
    return 0 <= age <= MAX_SOURCE_AGE_SECONDS


def _base_symbol(v: Any) -> str:
    s = str(v or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()
    return s[:-4] if s.endswith("USDT") else s


def _addr(v: Any) -> str:
    return str(v or "").strip().lower()


def _index_symbol(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict):
            key = _base_symbol(row.get("symbol") or row.get("base_symbol"))
            if key:
                out[key] = row
    return out


def _real_keys(payload: dict) -> set[tuple[str, str, str]]:
    out = set()
    for row in payload.get("alerts") or []:
        if not isinstance(row, dict) or row.get("status") != "REAL_ALERT":
            continue
        out.add((str(row.get("chain") or "").lower(), _addr(row.get("token_address")), _addr(row.get("pair_address"))))
    return out


def build(near: dict, pending: dict, identity: dict, real: dict, observed_at: str | None = None) -> dict:
    now = _parse_dt(observed_at) if observed_at else datetime.now(timezone.utc)
    now = now or datetime.now(timezone.utc)
    near_rows = [x for x in near.get("near_alert_leaderboard") or [] if isinstance(x, dict)]
    pending_index = _index_symbol([x for x in pending.get("candidates") or [] if isinstance(x, dict)])
    identity_index = _index_symbol([x for x in identity.get("candidates") or [] if isinstance(x, dict)])
    already_real = _real_keys(real if isinstance(real, dict) else {})
    identity_fresh = _fresh(identity.get("generated_at"), now)

    candidates = []
    rejected = []
    for row in near_rows:
        symbol = _base_symbol(row.get("symbol"))
        p = pending_index.get(symbol, {})
        i = identity_index.get(symbol, {})
        missing = [str(x) for x in row.get("missing_gates") or []]
        blockers = {str(x) for x in row.get("blockers") or []}
        reasons: list[str] = []

        key = (str(row.get("chain") or "").lower(), _addr(row.get("token_address")), _addr(row.get("pair_address")))
        if key in already_real:
            reasons.append("ALREADY_REAL_ALERT")
        if int(row.get("readiness_passed") or 0) != 6 or int(row.get("readiness_total") or 7) != 7:
            reasons.append("NOT_EXACT_6_OF_7")
        if missing != ["STRONG_DECISION_LANE"]:
            reasons.append("MISSING_GATE_NOT_STRONG_DECISION_ONLY")
        if blockers != {"NO_STRONG_DECISION_LANE"}:
            reasons.append("EXTRA_BLOCKER")
        if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
            reasons.append("EXACT_IDENTITY_PAIR_REQUIRED")
        if row.get("market_age_verified") is not True:
            reasons.append("MARKET_AGE_UNVERIFIED")
        if row.get("market_activity_verified") is not True:
            reasons.append("MARKET_ACTIVITY_UNVERIFIED")
        if _num(row.get("execution_pool_liquidity_usd")) < MIN_LIQUIDITY_USD:
            reasons.append("LIQUIDITY_LT_50K")
        if int(row.get("source_lane_count") or 0) < MIN_SOURCE_LANES:
            reasons.append("SOURCE_LANES_LT_2")
        if not identity_fresh:
            reasons.append("CEX_IDENTITY_SOURCE_STALE")
        if i and _addr(i.get("pair_address")) and _addr(i.get("pair_address")) != _addr(row.get("pair_address")):
            reasons.append("PAIR_MISMATCH")

        early_score = _num(p.get("first_alert_score"), _num(i.get("first_alert_score")))
        early_conf = int(_num(p.get("first_alert_coherent_confirmations"), _num(i.get("first_alert_coherent_confirmations"))))
        current_conf = int(_num(p.get("current_coherent_confirmations"), _num(i.get("coherent_confirmations"))))
        current_move = p.get("current_change_24h_max_pct")
        if current_move is None:
            current_move = i.get("current_change_24h_max_pct")
        current_move_num = _num(current_move, 9999.0)

        if early_score < MIN_EARLY_SCORE:
            reasons.append("EARLY_SCORE_LT_35")
        if early_conf < MIN_EARLY_CONFIRMATIONS:
            reasons.append("EARLY_CONFIRMATIONS_LT_2")
        if current_conf < MIN_CURRENT_CONFIRMATIONS:
            reasons.append("CURRENT_CONFIRMATIONS_LT_2")

        volume_h1 = _num(row.get("dex_volume_h1"))
        turnover_h1 = _num(row.get("turnover_h1"))
        activity_h1 = int(_num(row.get("buys_h1")) + _num(row.get("sells_h1")))
        if not (volume_h1 >= MIN_VOLUME_H1_USD or turnover_h1 >= MIN_TURNOVER_H1):
            reasons.append("ONCHAIN_ACTIVITY_TOO_WEAK")
        if activity_h1 < MIN_ACTIVITY_H1:
            reasons.append("TXNS_H1_LT_20")

        first_price = _num(p.get("first_alert_reference_price"), _num(i.get("first_alert_reference_price")))
        current_price = _num(row.get("price_usd"), 0.0)
        extension = ((current_price / first_price - 1.0) * 100.0) if first_price > 0 and current_price > 0 else None
        timing_metric = max(current_move_num, extension if extension is not None else -9999.0)
        if timing_metric <= EARLY_MAX_MOVE_PCT:
            timing = "EARLY_REVIEW"
            user_alert_eligible = True
        elif timing_metric <= MAX_REVIEW_MOVE_PCT:
            timing = "EXTENDED_WAIT_RETEST"
            user_alert_eligible = True
        else:
            timing = "LATE_DO_NOT_CHASE"
            user_alert_eligible = False

        hard_reasons = [r for r in reasons if r != "ALREADY_REAL_ALERT"]
        if hard_reasons or "ALREADY_REAL_ALERT" in reasons:
            rejected.append({"symbol": symbol, "reasons": reasons, "timing": timing})
            continue

        candidates.append({
            "symbol": symbol,
            "chain": row.get("chain"),
            "token_address": row.get("token_address"),
            "pair_address": row.get("pair_address"),
            "dex_url": row.get("dex_url"),
            "status": "PRECISION_PRE_WAVE_ALERT" if user_alert_eligible else "PRECISION_PRE_WAVE_LATE_NO_ALERT",
            "readiness": "6/7",
            "only_missing_gate": "STRONG_DECISION_LANE",
            "only_blocker": "NO_STRONG_DECISION_LANE",
            "source_lane_count": int(row.get("source_lane_count") or 0),
            "signal_score": row.get("signal_score"),
            "first_alert_at": p.get("first_alert_observed_at") or i.get("first_alert_observed_at"),
            "first_alert_reference_price": first_price or None,
            "first_alert_score": early_score,
            "first_alert_confirmations": early_conf,
            "current_cex_confirmations": current_conf,
            "current_change_24h_max_pct": current_move_num if current_move_num != 9999.0 else None,
            "current_price_usd": current_price or None,
            "move_from_first_alert_pct": round(extension, 4) if extension is not None else None,
            "execution_pool_liquidity_usd": _num(row.get("execution_pool_liquidity_usd")),
            "dex_volume_h1": volume_h1,
            "turnover_h1": turnover_h1,
            "buys_h1": int(_num(row.get("buys_h1"))),
            "sells_h1": int(_num(row.get("sells_h1"))),
            "timing": timing,
            "user_alert_eligible": user_alert_eligible,
            "manual_review_only": True,
            "automatic_buy": False,
            "automatic_trade": False,
        })

    return {
        "version": 1,
        "mode": MODE,
        "generated_at": now.isoformat(),
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "real_alert_gate_unchanged": True,
            "real_alert_still_requires_7_of_7": True,
            "precision_pre_wave_requires_6_of_7": True,
            "only_missing_gate": "STRONG_DECISION_LANE",
            "only_allowed_blocker": "NO_STRONG_DECISION_LANE",
            "exact_identity_and_pair_required": True,
            "minimum_market_age_days": MIN_AGE_DAYS,
            "minimum_execution_liquidity_usd": MIN_LIQUIDITY_USD,
            "minimum_source_lanes": MIN_SOURCE_LANES,
            "minimum_early_confirmations": MIN_EARLY_CONFIRMATIONS,
            "minimum_current_confirmations": MIN_CURRENT_CONFIRMATIONS,
            "source_max_age_seconds": MAX_SOURCE_AGE_SECONDS,
            "late_do_not_chase_threshold_pct": MAX_REVIEW_MOVE_PCT,
            "late_candidates_never_user_alert": True,
            "no_automatic_buy": True,
            "no_automatic_trade": True,
        },
        "candidate_count": len(candidates),
        "user_alert_eligible_count": sum(1 for x in candidates if x.get("user_alert_eligible") is True),
        "candidates": candidates,
        "rejected_count": len(rejected),
        "rejected": rejected[:100],
    }


def run(data_dir: str | Path = DATA, observed_at: str | None = None) -> dict:
    data = Path(data_dir)
    payload = build(
        _load(data / "near-alert-observatory.json", {}),
        _load(data / "cex-early-revival-pending.json", {}),
        _load(data / "cex-spot-identity-radar.json", {}),
        _load(data / "real-alerts.json", {}),
        observed_at=observed_at,
    )
    _write(data / "precision-pre-wave.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
