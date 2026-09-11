from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings

DATA = Path("data")
REAL_PRECURSOR_STATUSES = {"HIGH_CONVICTION_PRECURSOR", "PRE_BREAKOUT_CANDIDATE", "EARLY_REVIVAL_WATCH"}
REAL_WAKING_STATUSES = {"WAKING_CONFIRMED_RESEARCH", "WAKING_STRONG_RESEARCH"}
EVM_CHAINS = {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast"}
SOURCE_LANE_TOTAL = 7
WATCH_TRACKING_VERSION = 2
WATCH_NEW_TTL_HOURS = 24
WATCH_DISPLAY_TZ = ZoneInfo("Asia/Jerusalem")

PRE_WAVE_MIN_CEX_SPOT_SCORE = 35.0
PRE_WAVE_MIN_CEX_SPOT_CONFIRMATIONS = 3
PRE_WAVE_MIN_CEX_SPOT_EXCHANGES = 3
PRE_WAVE_MAX_24H_CHANGE_PCT = 35.0
PRE_WAVE_MIN_DEX_VOLUME_H1_USD = 1_000.0
PRE_WAVE_MIN_DEX_VOLUME_H24_USD = 10_000.0
PRE_WAVE_MIN_ACTIVITY_H1 = 10
PRE_WAVE_MIN_PAIR_AGE_MINUTES = 45.0
PRE_WAVE_SOFT_MULTICHAIN_BLOCKERS = {"VOLUME_H1_LT_15K", "TXNS_H1_LT_50"}
CEX_SPOT_MAX_AGE_SECONDS = 45 * 60
MULTICHAIN_MAX_AGE_SECONDS = 45 * 60


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _key(chain: object, token: object) -> str | None:
    c = str(chain or "").strip().lower()
    t = str(token or "").strip()
    if not c or not t:
        return None
    if c in EVM_CHAINS:
        t = t.lower()
    return f"{c}:{t}"


def _num(v, default=0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _opt_num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _parse_dt(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _source_fresh(row: dict, now_dt: datetime, max_age_seconds: int) -> bool:
    observed = _parse_dt(row.get("_source_generated_at") if isinstance(row, dict) else None)
    if observed is None:
        return False
    age = (now_dt - observed).total_seconds()
    return 0 <= age <= max_age_seconds


def _watch_is_new_24h(watch_added_at: object, now_dt: datetime) -> bool:
    observed = _parse_dt(watch_added_at)
    if observed is None:
        return False
    age_seconds = (now_dt - observed).total_seconds()
    return 0 <= age_seconds < WATCH_NEW_TTL_HOURS * 3600


def _watch_label(watch_added_at: object) -> str:
    observed = _parse_dt(watch_added_at)
    if observed is None:
        return ""
    return observed.astimezone(WATCH_DISPLAY_TZ).strftime("%d/%m %H:%M IL")


def _earliest_timestamp(*values: object) -> str | None:
    parsed = [(dt, str(value)) for value in values if (dt := _parse_dt(value)) is not None]
    if not parsed:
        return None
    return min(parsed, key=lambda x: x[0])[1]


def _age_ok(*rows: dict) -> tuple[bool, int | None]:
    ages = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_age_verified") is True:
            try:
                ages.append(int(float(row.get("market_age_min_days"))))
            except (TypeError, ValueError):
                pass
        truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
        if truth.get("market_age_verified_60d_plus") is True:
            try:
                ages.append(int(float(truth.get("market_age_days"))))
            except (TypeError, ValueError):
                pass
    if not ages:
        return False, None
    age = min(ages)
    return age >= 180, age


def _row_pair(row: dict) -> str | None:
    pair = str(row.get("pair_address") or row.get("entry_pair_address") or row.get("dex_pair_address") or "").strip()
    return pair or None


def _row_pair_exact(row: dict) -> bool:
    truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
    identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    return bool(
        str(row.get("identity_status") or "").startswith("DEX_VERIFIED")
        or row.get("identity_verified") is True
        or row.get("token_identity_verified") is True
        or row.get("exact_pair_verified") is True
        or truth.get("exact_pair_verified") is True
        or identity.get("exact_pair_verified") is True
        or row.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
        or row.get("measurement_status") == "VERIFIED_EXACT_PAIR"
        or row.get("pair_identity_locked") is True
        or row.get("qualification") in {"QUALIFIED", "REVIVAL_QUALIFIED"}
    )


def _pair_truth(*rows: dict) -> tuple[str | None, bool]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        pair = _row_pair(row)
        if pair and _row_pair_exact(row):
            return pair, True
    return None, False


def _row_execution_liquidity(row: dict) -> tuple[float, float | None, str] | None:
    if not isinstance(row, dict) or not _row_pair(row) or not _row_pair_exact(row):
        return None
    total = _num(row.get("dex_total_liquidity_usd"), -1)
    total_value = total if total >= 0 else None
    execution = _num(row.get("execution_pool_liquidity_usd"), -1)
    if execution < 0:
        truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
        execution = _num(truth.get("execution_pool_liquidity_usd"), -1)
    if execution >= 0:
        return execution, total_value, "EXECUTION_POOL_LIQUIDITY_USD"
    for key in ("dex_pair_liquidity_usd", "dex_liquidity_usd", "liquidity_usd", "current_liquidity_usd"):
        value = _num(row.get(key), -1)
        if value >= 0:
            return value, total_value, f"LEGACY_EXACT_PAIR:{key}"
    return None


def _execution_liquidity_truth(*rows: dict) -> tuple[float, float | None, str | None, str | None]:
    """Return liquidity for an exact executable pair, never token-wide TVL."""
    explicit = []
    legacy = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pair = _row_pair(row)
        if not pair or not _row_pair_exact(row):
            continue
        total = _num(row.get("dex_total_liquidity_usd"), -1)
        total_value = total if total >= 0 else None
        execution = _num(row.get("execution_pool_liquidity_usd"), -1)
        if execution < 0:
            truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
            execution = _num(truth.get("execution_pool_liquidity_usd"), -1)
        if execution >= 0:
            explicit.append((execution, total_value, pair, "EXECUTION_POOL_LIQUIDITY_USD"))
            continue
        for key in ("dex_pair_liquidity_usd", "dex_liquidity_usd", "liquidity_usd", "current_liquidity_usd"):
            value = _num(row.get(key), -1)
            if value >= 0:
                legacy.append((value, total_value, pair, f"LEGACY_EXACT_PAIR:{key}"))
                break
    candidates = explicit if explicit else legacy
    if not candidates:
        return 0.0, None, None, None
    return max(candidates, key=lambda x: x[0])


def _same_pair(a: object, b: object) -> bool:
    return bool(a and b and str(a).strip().lower() == str(b).strip().lower())


def _pair_context(pair: str | None, *rows: dict) -> dict:
    if not pair:
        return {}
    matches = [r for r in rows if isinstance(r, dict) and _same_pair(_row_pair(r), pair) and _row_pair_exact(r)]
    if not matches:
        return {}

    def rank(row: dict):
        liq = _row_execution_liquidity(row)
        value = liq[0] if liq else -1.0
        explicit = 1 if row.get("execution_pool_liquidity_usd") not in (None, "") else 0
        return explicit, value

    matches.sort(key=rank, reverse=True)
    out = dict(matches[0])
    fields = (
        "dex", "dex_id", "dex_url", "url", "dex_link", "pool_type", "protocol",
        "market_protocol", "market_program", "price_usd", "dex_price_usd",
        "current_price_usd", "reference_price", "dex_volume_h1", "dex_volume_h24",
        "volume_h1", "volume_h24", "buys_h1", "sells_h1", "buys_h24", "sells_h24",
        "pair_created_at", "execution_depth_verified", "execution_depth_usd_1pct",
        "execution_depth_usd_2pct", "execution_depth_usd_5pct", "execution_depth_source",
        "concentrated_liquidity_pool",
    )
    for row in matches[1:]:
        for field in fields:
            if out.get(field) in (None, "") and row.get(field) not in (None, ""):
                out[field] = row.get(field)
    out["pair_address"] = pair
    out["pair_metadata_atomic"] = True
    return out


def _identity_truth(*rows: dict) -> tuple[str | None, str | None, bool]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
        truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
        chain = str(_first(row.get("chain"), row.get("network")) or "").strip().lower()
        token = str(_first(row.get("token_address"), row.get("token"), row.get("mint")) or "").strip()
        exact = (
            str(row.get("identity_status") or "").startswith("DEX_VERIFIED")
            or row.get("identity_verified") is True
            or row.get("token_identity_verified") is True
            or identity.get("exact_mint_verified") is True
            or truth.get("exact_identity_verified") is True
            or row.get("network_verified") is True
            or row.get("qualification") in {"QUALIFIED", "REVIVAL_QUALIFIED"}
        )
        if chain and token and exact:
            return chain, token, True
    return None, None, False


def _price(*rows: dict) -> float | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        market = row.get("market") if isinstance(row.get("market"), dict) else {}
        for value in (row.get("price_usd"), row.get("dex_price_usd"), row.get("current_price_usd"), row.get("reference_price"), market.get("price_usd")):
            v = _num(value, 0)
            if v > 0:
                return v
    return None


def _symbol(*rows: dict) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        s = str(_first(row.get("symbol"), row.get("base_token_symbol"), row.get("name")) or "").strip()
        if s:
            if s.upper().endswith("USDT"):
                s = s[:-4]
            return s
    return "UNKNOWN"


def _index_rows(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        k = _key(_first(row.get("chain"), row.get("network")), _first(row.get("token_address"), row.get("token"), row.get("mint")))
        if k:
            out[k] = row
    return out


def _spot_rows(payload: dict) -> list[dict]:
    rows = payload.get("candidates") if isinstance(payload, dict) else []
    stamp = payload.get("generated_at") if isinstance(payload, dict) else None
    return [{**x, "_source_generated_at": stamp} for x in rows or [] if isinstance(x, dict)]


def _multichain_rows(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    out = []
    stamp = payload.get("generated_at")
    for name in ("veteran_watch", "dna_watch", "items"):
        for row in payload.get(name) or []:
            if isinstance(row, dict):
                out.append({**row, "_source_generated_at": stamp})
    return out


def _spot_lane_positive(row: dict, now_dt: datetime) -> bool:
    if not isinstance(row, dict):
        return False
    if not _source_fresh(row, now_dt, CEX_SPOT_MAX_AGE_SECONDS):
        return False
    if not (str(row.get("identity_status") or "").startswith("DEX_VERIFIED") or row.get("identity_verified") is True):
        return False
    if not row.get("chain") or not row.get("token_address") or not _row_pair(row):
        return False
    if row.get("market_age_verified") is not True:
        return False
    if row.get("leveraged_product") is True:
        return False
    score = _num(row.get("spot_revival_score"), 0)
    confirmations = int(_num(row.get("coherent_confirmations"), 0))
    exchanges = {str(x).lower() for x in row.get("exchanges") or [] if str(x).strip()}
    return score >= PRE_WAVE_MIN_CEX_SPOT_SCORE and confirmations >= PRE_WAVE_MIN_CEX_SPOT_CONFIRMATIONS and len(exchanges) >= PRE_WAVE_MIN_CEX_SPOT_EXCHANGES


def _multichain_strong(row: dict, now_dt: datetime) -> bool:
    gate = row.get("real_time_gate") if isinstance(row.get("real_time_gate"), dict) else {}
    turnover = _num(gate.get("turnover_h1"), 0)
    buys = int(_num(row.get("buys_h1"), 0))
    sells = int(_num(row.get("sells_h1"), 0))
    txns = int(_num(gate.get("txns_h1"), buys + sells))
    buy_sell = _num(gate.get("buy_sell_ratio_h1"), (buys / max(sells, 1) if txns else 0))
    onchain_strength = turnover >= 0.20 or buy_sell >= 1.18 or txns >= 100
    return bool(
        isinstance(row, dict)
        and _source_fresh(row, now_dt, MULTICHAIN_MAX_AGE_SECONDS)
        and row.get("status") == "DNA_WATCH_RESEARCH"
        and not (row.get("blockers") or [])
        and row.get("chase_risk") is not True
        and row.get("token_identity_verified") is True
        and row.get("market_age_verified") is True
        and _row_pair(row)
        and onchain_strength
    )


def _source_score(precursor: dict, waking: dict, cex: dict, active: dict, revival: dict, cex_spot: dict, multichain: dict, now_dt: datetime) -> tuple[list[str], int]:
    lanes = []
    if active and active.get("qualification") in {"QUALIFIED", "REVIVAL_QUALIFIED"}:
        lanes.append("ACTIVE_PRODUCTION_GATE")
    if precursor and precursor.get("status") in REAL_PRECURSOR_STATUSES:
        lanes.append("REVIVAL_PRECURSOR")
    if waking and waking.get("confirmation_status") in REAL_WAKING_STATUSES:
        lanes.append("WAKING_CONFIRMATION")
    if cex and _num(cex.get("cex_revival_score")) >= 35 and int(cex.get("coherent_confirmations") or 0) >= 2:
        lanes.append("CEX_REVIVAL")
    if _spot_lane_positive(cex_spot, now_dt):
        lanes.append("CEX_SPOT_BREADTH")
    if _multichain_strong(multichain, now_dt):
        lanes.append("MULTICHAIN_VETERAN_REVIVAL")
    if revival and (revival.get("watch_status") in {"WAKING_MARKET_ONLY", "ABSORPTION_WATCH_DISCOVERY_EXPANSION"} or (revival.get("order_flow_absorption") or {}).get("signal") is True):
        lanes.append("REVIVAL_MARKET_STRUCTURE")
    return lanes, len(set(lanes))


def _risk_blocked(*rows: dict) -> tuple[bool, list[str]]:
    reasons = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or row.get("qualification") or "")
        if status in {"LATE_MOVE_DO_NOT_CHASE", "PUMP_DUMP_RISK", "FAILED_SURVIVAL", "BLOCKED_TRUTH"}:
            if status != "BLOCKED_TRUTH" or row.get("production_effect") is not False:
                reasons.append(status)
        if row.get("pump_dump_blocked") is True:
            reasons.append("PUMP_DUMP_BLOCKED")
        if row.get("actionable_eligible") is False and status in REAL_PRECURSOR_STATUSES:
            reasons.append("ACTIONABLE_ELIGIBILITY_FALSE")
    return bool(reasons), sorted(set(reasons))


def _signal_context(precursor: dict, waking: dict, cex: dict, cex_spot: dict, multichain: dict, revival: dict, envelope: dict) -> tuple[float, str | None, dict]:
    market = envelope.get("market") if isinstance(envelope.get("market"), dict) else {}
    components = {
        "PRECURSOR_CONFIDENCE": _opt_num(precursor.get("confidence_adjusted_score")),
        "PRECURSOR_AVAILABLE_EVIDENCE": _opt_num(precursor.get("normalized_score_available_evidence")),
        "CEX_REVIVAL": _opt_num(cex.get("cex_revival_score")),
        "CEX_SPOT_BREADTH": _opt_num(cex_spot.get("spot_revival_score")),
        "MULTICHAIN_VETERAN_DNA": _opt_num(multichain.get("winner_dna_score_research")),
        "REVIVAL_VERIFIED": _opt_num(revival.get("revival_score_verified")),
        "REVIVAL_RAW": _opt_num(revival.get("revival_score")),
        "WAKING_CONFIRMATION": _opt_num(waking.get("confirmation_score")),
        "ENVELOPE_MARKET_VERIFIED": _opt_num(market.get("revival_score_verified")),
    }
    present = {k: v for k, v in components.items() if v is not None}
    leader = max(present, key=present.get) if present else None
    signal = max(present.values(), default=0.0)
    clean = {k: (round(v, 2) if v is not None else None) for k, v in components.items()}
    return round(signal, 2), leader, clean


def _readiness(*, exact_identity: bool, exact_pair: bool, age_ok: bool, liquidity_ok: bool, risk_clear: bool, strong_decision: bool, independent_confirmation: bool) -> tuple[dict[str, bool], int]:
    gates = {
        "EXACT_IDENTITY": bool(exact_identity),
        "EXACT_DEX_PAIR": bool(exact_pair),
        "VETERAN_AGE_180D": bool(age_ok),
        "EXECUTION_LIQUIDITY": bool(liquidity_ok),
        "RISK_CLEAR": bool(risk_clear),
        "STRONG_DECISION_LANE": bool(strong_decision),
        "INDEPENDENT_CONFIRMATION": bool(independent_confirmation),
    }
    return gates, sum(1 for passed in gates.values() if passed)


def _clarity_tier(blockers: list[str], risk_reasons: list[str], liquidity_ok: bool) -> tuple[str, str]:
    if not blockers:
        return "REAL_ALERT", "CLEAR"
    if risk_reasons:
        return "BLOCKED", "HIGH"
    if not liquidity_ok:
        return "BLOCKED", "MEDIUM"
    if len(set(blockers)) == 1 and blockers[0] in {"NO_STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION_LT_2"}:
        return "NEAR_ALERT", "CLEAR"
    return "VERIFIED_WATCH", "CLEAR"


def _pair_age_minutes(pair_ctx: dict, now_dt: datetime) -> float | None:
    raw = pair_ctx.get("pair_created_at") if isinstance(pair_ctx, dict) else None
    try:
        ts = float(raw)
        if ts <= 0:
            return None
        if ts > 10_000_000_000:
            ts /= 1000.0
        created = datetime.fromtimestamp(ts, tz=timezone.utc)
        if created > now_dt:
            return None
        return (now_dt - created).total_seconds() / 60.0
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _pre_wave_spot_ok(cex_spot: dict, pair: str | None, now_dt: datetime) -> tuple[bool, dict]:
    score = _num(cex_spot.get("spot_revival_score"), 0)
    confirmations = int(_num(cex_spot.get("coherent_confirmations"), 0))
    exchanges = sorted({str(x).lower() for x in cex_spot.get("exchanges") or [] if str(x).strip()})
    change24 = _opt_num(cex_spot.get("change_24h_max_pct"))
    features = {str(x) for x in cex_spot.get("coherent_feature_hits") or []}
    pair_match = _same_pair(_row_pair(cex_spot), pair)
    acceleration = bool(features & {"PRICE_ACCEL", "VOLUME_ACCEL"}) or _num(cex_spot.get("price_acceleration_max_pct"), 0) > 0 or _num(cex_spot.get("volume_acceleration_max_pct"), 0) > 0
    ok = bool(
        _spot_lane_positive(cex_spot, now_dt)
        and pair_match
        and acceleration
        and (change24 is None or change24 < PRE_WAVE_MAX_24H_CHANGE_PCT)
    )
    return ok, {
        "spot_score": round(score, 2),
        "spot_confirmations": confirmations,
        "spot_exchange_count": len(exchanges),
        "spot_exchanges": exchanges,
        "spot_change_24h_max_pct": change24,
        "spot_acceleration_present": acceleration,
        "spot_pair_match": pair_match,
    }


def _pre_wave_multichain_ok(multichain: dict, pair: str | None, min_liq: float, now_dt: datetime) -> tuple[bool, dict]:
    gate = multichain.get("real_time_gate") if isinstance(multichain.get("real_time_gate"), dict) else {}
    liq = _num(_first(multichain.get("execution_pool_liquidity_usd"), multichain.get("dex_liquidity_usd"), multichain.get("liquidity_usd")), 0)
    vol_h1 = _num(_first(gate.get("volume_h1_usd"), multichain.get("volume_h1"), multichain.get("dex_volume_h1")), 0)
    vol_h24 = _num(_first(multichain.get("volume_h24"), multichain.get("dex_volume_h24")), 0)
    buys = int(_num(_first(multichain.get("buys_h1"), gate.get("buys_h1")), 0))
    sells = int(_num(_first(multichain.get("sells_h1"), gate.get("sells_h1")), 0))
    txns = int(_num(gate.get("txns_h1"), buys + sells))
    h1 = _num(_first(gate.get("price_change_h1_pct"), multichain.get("price_change_h1")), 0)
    h24 = _num(_first(gate.get("price_change_h24_pct"), multichain.get("price_change_h24")), 0)
    blockers = {str(x) for x in multichain.get("blockers") or []}
    hard_blockers = sorted(blockers - PRE_WAVE_SOFT_MULTICHAIN_BLOCKERS)
    pair_match = _same_pair(_row_pair(multichain), pair)
    ok = bool(
        multichain
        and _source_fresh(multichain, now_dt, MULTICHAIN_MAX_AGE_SECONDS)
        and multichain.get("token_identity_verified") is True
        and multichain.get("market_age_verified") is True
        and _num(multichain.get("market_age_min_days"), 0) >= 180
        and pair_match
        and liq >= min_liq
        and vol_h1 >= PRE_WAVE_MIN_DEX_VOLUME_H1_USD
        and txns >= PRE_WAVE_MIN_ACTIVITY_H1
        and not hard_blockers
        and multichain.get("chase_risk") is not True
        and h1 <= 25
        and h24 < PRE_WAVE_MAX_24H_CHANGE_PCT
    )
    return ok, {
        "multichain_pair_match": pair_match,
        "multichain_liquidity_usd": round(liq, 2),
        "multichain_volume_h1_usd": round(vol_h1, 2),
        "multichain_volume_h24_usd": round(vol_h24, 2),
        "multichain_activity_h1": txns,
        "multichain_price_change_h1_pct": round(h1, 4),
        "multichain_price_change_h24_pct": round(h24, 4),
        "multichain_soft_blockers": sorted(blockers & PRE_WAVE_SOFT_MULTICHAIN_BLOCKERS),
        "multichain_hard_blockers": hard_blockers,
    }


def _pre_wave_eligible(*, exact_identity: bool, exact_pair: bool, age_ok: bool, liquidity_ok: bool, risk_clear: bool, pair: str | None, pair_ctx: dict, cex_spot: dict, multichain: dict, min_liq: float, now_dt: datetime) -> tuple[bool, dict]:
    spot_ok, spot_metrics = _pre_wave_spot_ok(cex_spot, pair, now_dt)
    market_ok, market_metrics = _pre_wave_multichain_ok(multichain, pair, min_liq, now_dt)
    pair_age = _pair_age_minutes(pair_ctx, now_dt)
    pair_age_ok = pair_age is None or pair_age >= PRE_WAVE_MIN_PAIR_AGE_MINUTES
    hard_truth = bool(exact_identity and exact_pair and age_ok and liquidity_ok and risk_clear and pair_age_ok)
    return bool(hard_truth and spot_ok and market_ok), {
        "exact_identity": bool(exact_identity),
        "exact_pair": bool(exact_pair),
        "veteran_age_180d": bool(age_ok),
        "execution_liquidity": bool(liquidity_ok),
        "risk_clear": bool(risk_clear),
        "pair_age_minutes": round(pair_age, 2) if pair_age is not None else None,
        "pair_age_ok": pair_age_ok,
        "cex_spot_breadth": spot_ok,
        "multichain_market_activity": market_ok,
        **spot_metrics,
        **market_metrics,
    }


def build(data_dir: Path = DATA) -> dict:
    cfg = Settings()
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    previous_payload = _load(data_dir / "real-alerts.json", {})
    previous_tracking = previous_payload.get("watch_tracking") if isinstance(previous_payload.get("watch_tracking"), dict) else {}
    tracking_initialized = int(previous_tracking.get("version") or 0) == WATCH_TRACKING_VERSION
    previous_registry = previous_tracking.get("active_registry") if isinstance(previous_tracking.get("active_registry"), dict) else {}
    previous_baseline_keys = set(previous_tracking.get("baseline_keys") or [])
    previous_watch_rows = _index_rows(list(previous_payload.get("verified_watch") or []))

    cex_payload = _load(data_dir / "cex-revival-radar.json", {})
    cex_spot_payload = _load(data_dir / "cex-spot-identity-radar.json", {})
    multichain_payload = _load(data_dir / "multichain-veteran-revival.json", {})
    precursor_payload = _load(data_dir / "revival-precursor-latest.json", {})
    waking_payload = _load(data_dir / "waking-confirmation-latest.json", {})
    revival_payload = _load(data_dir / "revival-1000-latest.json", {})
    envelope_payload = _load(data_dir / "candidate-evidence-envelope.json", {})
    active_rows = _load(data_dir / "active-qualified-candidates.json", [])

    cex_rows = list(cex_payload.get("alerts") or [])
    cex_spot_rows = _spot_rows(cex_spot_payload)
    multichain_rows = _multichain_rows(multichain_payload)
    precursor_rows = list(precursor_payload.get("targets") or [])
    waking_rows = list(waking_payload.get("targets") or [])
    revival_rows = list(revival_payload.get("coins") or [])
    envelope_rows = list(envelope_payload.get("candidates") or [])
    active_rows = active_rows if isinstance(active_rows, list) else []

    indexes = {
        "cex": _index_rows(cex_rows),
        "cex_spot": _index_rows(cex_spot_rows),
        "multichain": _index_rows(multichain_rows),
        "precursor": _index_rows(precursor_rows),
        "waking": _index_rows(waking_rows),
        "revival": _index_rows(revival_rows),
        "envelope": _index_rows(envelope_rows),
        "active": _index_rows(active_rows),
    }
    keys = set().union(*(set(index) for index in indexes.values()))

    real_alerts = []
    pre_wave_alerts = []
    verified_watch = []
    for k in keys:
        cex = indexes["cex"].get(k) or {}
        cex_spot = indexes["cex_spot"].get(k) or {}
        multichain = indexes["multichain"].get(k) or {}
        precursor = indexes["precursor"].get(k) or {}
        waking = indexes["waking"].get(k) or {}
        revival = indexes["revival"].get(k) or {}
        envelope = indexes["envelope"].get(k) or {}
        active = indexes["active"].get(k) or {}
        rows = (active, precursor, waking, cex, cex_spot, multichain, revival, envelope)

        chain, token, exact_identity = _identity_truth(*rows)
        pair, exact_pair = _pair_truth(*rows)
        execution_liq, total_dex_liq, execution_pair, liquidity_source = _execution_liquidity_truth(*rows)
        if execution_pair:
            pair = execution_pair
            exact_pair = True
        pair_ctx = _pair_context(pair, *rows)

        age_ok, age_days = _age_ok(*rows)
        lanes, lane_count = _source_score(precursor, waking, cex, active, revival, cex_spot, multichain, now_dt)
        blocked, risk_reasons = _risk_blocked(*rows)
        precursor_status = precursor.get("status")
        production_pass = active.get("qualification") in {"QUALIFIED", "REVIVAL_QUALIFIED"}
        precursor_pass = precursor_status in REAL_PRECURSOR_STATUSES
        multichain_pass = _multichain_strong(multichain, now_dt)
        envelope_status = str(envelope.get("status") or "")
        envelope_coverage = envelope.get("coverage") if isinstance(envelope.get("coverage"), dict) else {}
        evidence_positive_lanes = list(envelope_coverage.get("positive_independent_lanes") or [])
        evidence_verified_lanes = list(envelope_coverage.get("verified_independent_lanes") or [])

        liquidity_ok = execution_liq >= cfg.verified_min_liquidity_usd
        strong_decision = production_pass or precursor_pass or multichain_pass
        independent_confirmation = production_pass or lane_count >= 2

        blockers = []
        if not exact_identity:
            blockers.append("EXACT_IDENTITY_REQUIRED")
        if not exact_pair:
            blockers.append("EXACT_DEX_PAIR_REQUIRED")
        if not age_ok:
            blockers.append("VERIFIED_MARKET_AGE_180D_REQUIRED")
        if not liquidity_ok:
            blockers.append(f"EXECUTION_POOL_LIQUIDITY_LT_{int(cfg.verified_min_liquidity_usd/1000)}K")
        if blocked:
            blockers.extend(risk_reasons)
        if not strong_decision:
            blockers.append("NO_STRONG_DECISION_LANE")
        if not independent_confirmation:
            blockers.append("INDEPENDENT_CONFIRMATION_LT_2")
        blockers = sorted(set(blockers))

        signal_score, signal_leader, score_components = _signal_context(precursor, waking, cex, cex_spot, multichain, revival, envelope)
        readiness_gates, readiness_passed = _readiness(
            exact_identity=exact_identity,
            exact_pair=exact_pair,
            age_ok=age_ok,
            liquidity_ok=liquidity_ok,
            risk_clear=not blocked,
            strong_decision=strong_decision,
            independent_confirmation=independent_confirmation,
        )
        radar_tier, risk_level = _clarity_tier(blockers, risk_reasons, liquidity_ok)
        missing_gates = [name for name, passed in readiness_gates.items() if not passed]

        pair_dex = _first(pair_ctx.get("dex"), pair_ctx.get("dex_id"))
        pair_url = _first(pair_ctx.get("dex_url"), pair_ctx.get("url"), pair_ctx.get("dex_link"))
        pair_price = _price(pair_ctx) if pair_ctx else None
        cex_milestones = cex.get("milestones") if isinstance(cex.get("milestones"), dict) else {}
        spot_milestones = cex_spot.get("milestones") if isinstance(cex_spot.get("milestones"), dict) else {}
        first_alert_at = _earliest_timestamp(
            (cex_milestones.get("first_alert") or {}).get("observed_at"),
            (spot_milestones.get("first_watch") or {}).get("observed_at"),
            (spot_milestones.get("first_alert") or {}).get("observed_at"),
            (precursor.get("t0") or {}).get("observed_at"),
            active.get("qualified_at"),
        )

        pre_wave_ok, pre_wave_gates = _pre_wave_eligible(
            exact_identity=exact_identity,
            exact_pair=exact_pair,
            age_ok=age_ok,
            liquidity_ok=liquidity_ok,
            risk_clear=not blocked,
            pair=pair,
            pair_ctx=pair_ctx,
            cex_spot=cex_spot,
            multichain=multichain,
            min_liq=cfg.verified_min_liquidity_usd,
            now_dt=now_dt,
        )

        item = {
            "symbol": _symbol(active, precursor, waking, cex, cex_spot, multichain, revival, envelope),
            "chain": chain,
            "token_address": token,
            "pair_address": pair,
            "dex": pair_dex,
            "dex_url": pair_url,
            "price_usd": pair_price if pair_price is not None else _price(*[r for r in rows if _same_pair(_row_pair(r), pair)]),
            "pair_metadata_atomic": bool(pair_ctx),
            "liquidity_usd": execution_liq,
            "execution_pool_liquidity_usd": execution_liq,
            "dex_total_liquidity_usd": total_dex_liq,
            "liquidity_gate_metric": "EXECUTION_POOL_LIQUIDITY_USD",
            "liquidity_truth_source": liquidity_source,
            "market_age_days": age_days,
            "score": signal_score,
            "signal_score": signal_score,
            "signal_leader": signal_leader,
            "score_semantics": "MAX_AVAILABLE_SIGNAL_NOT_PROBABILITY",
            "score_components": score_components,
            "source_lanes": sorted(set(lanes)),
            "source_lane_count": lane_count,
            "source_lane_total": SOURCE_LANE_TOTAL,
            "confirmation_count": lane_count,
            "confirmation_total": SOURCE_LANE_TOTAL,
            "precursor_status": precursor_status,
            "waking_status": waking.get("confirmation_status"),
            "cex_score": cex.get("cex_revival_score"),
            "cex_confirmations": cex.get("coherent_confirmations"),
            "cex_spot_score": cex_spot.get("spot_revival_score"),
            "cex_spot_confirmations": cex_spot.get("coherent_confirmations"),
            "cex_spot_exchanges": cex_spot.get("exchanges") or [],
            "multichain_status": multichain.get("status"),
            "multichain_score": multichain.get("winner_dna_score_research"),
            "evidence_envelope_status": envelope_status or None,
            "evidence_ready": envelope_status == "EVIDENCE_READY",
            "evidence_positive_lanes": evidence_positive_lanes,
            "evidence_verified_lanes": evidence_verified_lanes,
            "evidence_positive_count": int(envelope_coverage.get("positive_independent_count") or len(evidence_positive_lanes)),
            "evidence_verified_count": int(envelope_coverage.get("verified_independent_count") or len(evidence_verified_lanes)),
            "readiness_gates": readiness_gates,
            "readiness_passed": readiness_passed,
            "readiness_total": len(readiness_gates),
            "readiness_pct": round(100.0 * readiness_passed / max(1, len(readiness_gates)), 1),
            "missing_gates": missing_gates,
            "radar_tier": radar_tier,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "why_now": sorted(set(lanes)),
            "first_alert_at": first_alert_at,
            "exact_identity_verified": exact_identity,
            "exact_pair_verified": exact_pair,
            "market_age_verified": age_ok,
            "blockers": blockers,
            "automatic_buy": False,
        }
        for f in ("dex_volume_h1", "dex_volume_h24", "volume_h1", "volume_h24", "buys_h1", "sells_h1", "buys_h24", "sells_h24", "pair_created_at", "concentrated_liquidity_pool", "execution_depth_verified", "execution_depth_usd_5pct"):
            if pair_ctx.get(f) not in (None, ""):
                item[f] = pair_ctx.get(f)

        if not blockers:
            item["status"] = "REAL_ALERT"
            item["actionable_research_alert"] = True
            real_alerts.append(item)
        else:
            watch_interest = bool(
                lane_count >= 1
                or envelope_status in {"EVIDENCE_READY", "VERIFIED_WATCH"}
                or revival.get("watch_status") == "WAKING_MARKET_ONLY"
                or pre_wave_ok
            )
            if exact_identity and exact_pair and age_ok and watch_interest:
                if tracking_initialized:
                    if k in previous_registry:
                        watch_added_at = previous_registry[k]
                        watch_is_new = k not in previous_baseline_keys and _watch_is_new_24h(watch_added_at, now_dt)
                    else:
                        watch_added_at = now
                        watch_is_new = True
                else:
                    legacy_row = previous_watch_rows.get(k) or {}
                    watch_added_at = _first(legacy_row.get("watch_added_at"), legacy_row.get("first_alert_at"), item.get("first_alert_at"), now)
                    watch_is_new = False
                watch_label = _watch_label(watch_added_at)
                item["watch_added_at"] = watch_added_at
                item["watch_is_new_24h"] = watch_is_new
                item["watch_entered_label"] = watch_label
                watch_context = [f"🕒 WATCH SINCE · {watch_label}", *sorted(set(lanes))]
                if watch_is_new:
                    watch_context.insert(0, f"🆕 NEW WATCH · {watch_label}")
                item["why_now"] = watch_context
                item["status"] = "EVIDENCE_READY_NOT_REAL_ALERT" if envelope_status == "EVIDENCE_READY" else "VERIFIED_WATCH_NOT_REAL_ALERT"
                item["actionable_research_alert"] = False
                verified_watch.append(item)

                if pre_wave_ok:
                    pre = dict(item)
                    pre.update({
                        "status": "PRE_WAVE_ALERT",
                        "radar_tier": "PRE_WAVE_ALERT",
                        "user_alert_eligible": True,
                        "manual_decision_only": True,
                        "research_only": False,
                        "actionable_research_alert": False,
                        "automatic_buy": False,
                        "pre_wave_gates": pre_wave_gates,
                        "full_real_alert_pending_gates": missing_gates,
                        "pre_wave_reason_codes": [
                            "EXACT_IDENTITY_PAIR_AGE_LIQUIDITY_RISK_PASS",
                            "MULTI_EXCHANGE_CEX_SPOT_ACCELERATION",
                            "ONCHAIN_ACTIVITY_PRESENT_BEFORE_FULL_PRODUCTION_CONFIRMATION",
                        ],
                    })
                    pre_wave_alerts.append(pre)

    identity_pending = []
    for row in cex_rows:
        if str(row.get("identity_status") or "").startswith("DEX_VERIFIED"):
            continue
        identity_pending.append({
            "symbol": _symbol(row),
            "cex_score": row.get("cex_revival_score"),
            "market_age_days": row.get("market_age_min_days"),
            "coherent_confirmations": row.get("coherent_confirmations"),
            "identity_status": row.get("identity_status") or "IDENTITY_PENDING",
            "identity_blocker": row.get("identity_blocker") or "EXACT_IDENTITY_NOT_VERIFIED",
            "status": "IDENTITY_PENDING_NOT_ACTIONABLE",
            "radar_tier": "IDENTITY_PENDING",
            "actionable_research_alert": False,
        })

    tier_priority = {"NEAR_ALERT": 3, "VERIFIED_WATCH": 2, "BLOCKED": 1}
    real_alerts.sort(key=lambda x: (x.get("signal_score") or 0, x.get("source_lane_count") or 0, x.get("execution_pool_liquidity_usd") or 0), reverse=True)
    pre_wave_alerts.sort(key=lambda x: (
        _num(x.get("cex_spot_score"), 0),
        _num((x.get("pre_wave_gates") or {}).get("multichain_volume_h1_usd"), 0),
        _num(x.get("execution_pool_liquidity_usd"), 0),
    ), reverse=True)
    verified_watch.sort(key=lambda x: (
        tier_priority.get(x.get("radar_tier"), 0),
        x.get("watch_is_new_24h") is True,
        str(x.get("watch_added_at") or ""),
        x.get("readiness_passed") or 0,
        x.get("evidence_ready") is True,
        x.get("source_lane_count") or 0,
        x.get("signal_score") or 0,
    ), reverse=True)
    identity_pending.sort(key=lambda x: (x.get("cex_score") or 0, x.get("coherent_confirmations") or 0), reverse=True)

    evidence_ready_count = sum(1 for row in envelope_rows if isinstance(row, dict) and row.get("status") == "EVIDENCE_READY")
    near_count = sum(1 for row in verified_watch if row.get("radar_tier") == "NEAR_ALERT")
    blocked_count = sum(1 for row in verified_watch if row.get("radar_tier") == "BLOCKED")
    plain_watch_count = sum(1 for row in verified_watch if row.get("radar_tier") == "VERIFIED_WATCH")
    new_watch_count = sum(1 for row in verified_watch if row.get("watch_is_new_24h") is True)
    active_registry = {}
    for row in verified_watch:
        rk = _key(row.get("chain"), row.get("token_address"))
        if rk and row.get("watch_added_at"):
            active_registry[rk] = row.get("watch_added_at")
    baseline_keys = sorted(k for k in previous_baseline_keys if k in active_registry) if tracking_initialized else sorted(active_registry.keys())

    return {
        "version": 4,
        "generated_at": now,
        "mode": "FAIL_CLOSED_REAL_ALERT_FEED_V4_PRE_WAVE_MULTICHAIN",
        "score_contract": {
            "signal_score_semantics": "maximum currently available subsystem signal; not a probability and not overall conviction",
            "confirmation_total_lanes": SOURCE_LANE_TOTAL,
            "readiness_gate_total": 7,
            "readiness_is_gate_completion_not_profit_probability": True,
            "radar_tiers": ["REAL_ALERT", "PRE_WAVE_ALERT", "NEAR_ALERT", "VERIFIED_WATCH", "BLOCKED", "IDENTITY_PENDING"],
        },
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "minimum_market_age_days": 180,
            "minimum_execution_pool_liquidity_usd": cfg.verified_min_liquidity_usd,
            "liquidity_gate_metric": "EXECUTION_POOL_LIQUIDITY_USD",
            "dex_total_liquidity_is_informational_only": True,
            "exact_onchain_identity_required": True,
            "exact_dex_pair_required": True,
            "pair_market_metadata_must_match_exact_pair": True,
            "symbol_only_never_actionable": True,
            "cex_only_never_real_alert": True,
            "production_gate_or_strong_precursor_or_multichain_decision_required": True,
            "non_production_alert_requires_min_independent_lanes": 2,
            "cex_spot_exact_identity_lane_enabled": True,
            "multichain_veteran_strong_lane_enabled": True,
            "pre_wave_user_alert_is_not_real_alert": True,
            "pre_wave_never_automatic_buy": True,
            "pre_wave_does_not_weaken_real_alert_gates": True,
            "pre_wave_requires_exact_identity_pair_age_liquidity_and_clear_risk": True,
            "pre_wave_requires_exact_cex_spot_breadth": True,
            "pre_wave_min_cex_spot_confirmations": PRE_WAVE_MIN_CEX_SPOT_CONFIRMATIONS,
            "pre_wave_min_cex_spot_exchanges": PRE_WAVE_MIN_CEX_SPOT_EXCHANGES,
            "pre_wave_max_change_24h_pct": PRE_WAVE_MAX_24H_CHANGE_PCT,
            "pre_wave_min_dex_volume_h1_usd": PRE_WAVE_MIN_DEX_VOLUME_H1_USD,
            "pre_wave_min_activity_h1": PRE_WAVE_MIN_ACTIVITY_H1,
            "cex_spot_max_age_seconds": CEX_SPOT_MAX_AGE_SECONDS,
            "multichain_max_age_seconds": MULTICHAIN_MAX_AGE_SECONDS,
            "stale_multichain_or_spot_never_promotes": True,
            "evidence_ready_is_visible_but_does_not_auto_promote_to_real_alert": True,
            "late_move_or_pump_dump_never_real_alert": True,
            "label_meaning": "REAL_ALERT is strict manual review; PRE_WAVE_ALERT is an earlier manual-review warning, never an instruction or automatic trade.",
        },
        "watch_tracking": {
            "version": WATCH_TRACKING_VERSION,
            "new_watch_ttl_hours": WATCH_NEW_TTL_HOURS,
            "display_timezone": "Asia/Jerusalem",
            "new_watch_24h_count": new_watch_count,
            "active_registry": active_registry,
            "baseline_keys": baseline_keys,
        },
        "counts": {
            "real_alerts": len(real_alerts),
            "pre_wave_alerts": len(pre_wave_alerts),
            "near_alert_not_real": near_count,
            "verified_watch_core": plain_watch_count,
            "blocked_verified_watch": blocked_count,
            "verified_watch_not_real": len(verified_watch),
            "new_watch_24h": new_watch_count,
            "evidence_ready_research": evidence_ready_count,
            "identity_pending_not_actionable": len(identity_pending),
        },
        "latest_real_alert": real_alerts[0] if real_alerts else None,
        "latest_pre_wave_alert": pre_wave_alerts[0] if pre_wave_alerts else None,
        "alerts": real_alerts,
        "pre_wave_alerts": pre_wave_alerts[:50],
        "verified_watch": verified_watch[:50],
        "identity_pending": identity_pending[:50],
    }


def _sanitize_pre_wave_rows(payload: dict, min_liq: float) -> tuple[list[dict], int]:
    from .liquidity_truth_guard import annotate_row
    kept = []
    rejected = 0
    for row in payload.get("pre_wave_alerts") or []:
        if not isinstance(row, dict):
            rejected += 1
            continue
        clean = annotate_row(row)
        liq = _num(_first(clean.get("execution_pool_liquidity_usd"), clean.get("liquidity_usd")), 0)
        h1 = _num(_first(clean.get("dex_volume_h1"), clean.get("volume_h1")), 0)
        h24 = _num(_first(clean.get("dex_volume_h24"), clean.get("volume_h24")), 0)
        concentrated_unverified = clean.get("concentrated_liquidity_pool") is True and clean.get("execution_depth_verified") is not True
        if (
            concentrated_unverified
            or liq < min_liq
            or (h1 < PRE_WAVE_MIN_DEX_VOLUME_H1_USD and h24 < PRE_WAVE_MIN_DEX_VOLUME_H24_USD)
            or clean.get("exact_identity_verified") is not True
            or clean.get("exact_pair_verified") is not True
            or clean.get("market_age_verified") is not True
            or clean.get("risk_reasons")
        ):
            rejected += 1
            continue
        clean["pre_wave_liquidity_guard_pass"] = True
        kept.append(clean)
    return kept, rejected


def run(data_dir: Path = DATA) -> dict:
    from .liquidity_truth_guard import sanitize_real_alerts
    cfg = Settings()
    path = data_dir / "real-alerts.json"
    payload = build(data_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sanitize_real_alerts(path)
    final_payload = _load(path, {})
    pre_wave, rejected = _sanitize_pre_wave_rows(final_payload, cfg.verified_min_liquidity_usd)
    final_payload["pre_wave_alerts"] = pre_wave[:50]
    final_payload["latest_pre_wave_alert"] = pre_wave[0] if pre_wave else None
    counts = final_payload.get("counts") if isinstance(final_payload.get("counts"), dict) else {}
    counts["pre_wave_alerts"] = len(pre_wave)
    counts["pre_wave_liquidity_guard_rejections"] = rejected
    final_payload["counts"] = counts
    truth = final_payload.get("truth_contract") if isinstance(final_payload.get("truth_contract"), dict) else {}
    truth["producer_liquidity_sanitized_before_publish"] = True
    truth["pre_wave_rows_liquidity_sanitized_before_publish"] = True
    final_payload["truth_contract"] = truth
    path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return final_payload.get("counts") or {}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
