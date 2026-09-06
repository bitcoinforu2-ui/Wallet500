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
SOURCE_LANE_TOTAL = 5
WATCH_TRACKING_VERSION = 2
WATCH_NEW_TTL_HOURS = 24
WATCH_DISPLAY_TZ = ZoneInfo("Asia/Jerusalem")


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


def _age_ok(*rows: dict) -> tuple[bool, int | None]:
    ages = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_age_verified") is True:
            try:
                ages.append(int(row.get("market_age_min_days")))
            except (TypeError, ValueError):
                pass
        truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
        if truth.get("market_age_verified_180d_plus") is True:
            try:
                ages.append(int(truth.get("market_age_days")))
            except (TypeError, ValueError):
                pass
    if not ages:
        return False, None
    age = min(ages)
    return age >= 180, age


def _row_pair(row: dict) -> str | None:
    pair = str(
        row.get("pair_address")
        or row.get("entry_pair_address")
        or row.get("dex_pair_address")
        or ""
    ).strip()
    return pair or None


def _row_pair_exact(row: dict) -> bool:
    truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
    return bool(
        str(row.get("identity_status") or "").startswith("DEX_VERIFIED")
        or row.get("exact_pair_verified") is True
        or truth.get("exact_pair_verified") is True
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
        for value in (
            row.get("price_usd"),
            row.get("dex_price_usd"),
            row.get("current_price_usd"),
            row.get("reference_price"),
            market.get("price_usd"),
        ):
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
        k = _key(
            _first(row.get("chain"), row.get("network")),
            _first(row.get("token_address"), row.get("token"), row.get("mint")),
        )
        if k:
            out[k] = row
    return out


def _source_score(precursor: dict, waking: dict, cex: dict, active: dict, revival: dict) -> tuple[list[str], int]:
    lanes = []
    if active and active.get("qualification") in {"QUALIFIED", "REVIVAL_QUALIFIED"}:
        lanes.append("ACTIVE_PRODUCTION_GATE")
    if precursor and precursor.get("status") in REAL_PRECURSOR_STATUSES:
        lanes.append("REVIVAL_PRECURSOR")
    if waking and waking.get("confirmation_status") in REAL_WAKING_STATUSES:
        lanes.append("WAKING_CONFIRMATION")
    if cex and _num(cex.get("cex_revival_score")) >= 35 and int(cex.get("coherent_confirmations") or 0) >= 2:
        lanes.append("CEX_REVIVAL")
    if revival and (
        revival.get("watch_status") in {"WAKING_MARKET_ONLY", "ABSORPTION_WATCH_DISCOVERY_EXPANSION"}
        or (revival.get("order_flow_absorption") or {}).get("signal") is True
    ):
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


def _signal_context(precursor: dict, waking: dict, cex: dict, revival: dict, envelope: dict) -> tuple[float, str | None, dict]:
    market = envelope.get("market") if isinstance(envelope.get("market"), dict) else {}
    components = {
        "PRECURSOR_CONFIDENCE": _opt_num(precursor.get("confidence_adjusted_score")),
        "PRECURSOR_AVAILABLE_EVIDENCE": _opt_num(precursor.get("normalized_score_available_evidence")),
        "CEX_REVIVAL": _opt_num(cex.get("cex_revival_score")),
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


def _readiness(
    *,
    exact_identity: bool,
    exact_pair: bool,
    age_ok: bool,
    liquidity_ok: bool,
    risk_clear: bool,
    strong_decision: bool,
    independent_confirmation: bool,
) -> tuple[dict[str, bool], int]:
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


def build(data_dir: Path = DATA) -> dict:
    cfg = Settings()
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    previous_payload = _load(data_dir / "real-alerts.json", {})
    previous_tracking = previous_payload.get("watch_tracking") if isinstance(previous_payload.get("watch_tracking"), dict) else {}
    previous_tracking_version = int(previous_tracking.get("version") or 0)
    tracking_initialized = previous_tracking_version == WATCH_TRACKING_VERSION
    previous_registry = previous_tracking.get("active_registry") if isinstance(previous_tracking.get("active_registry"), dict) else {}
    previous_baseline_keys = set(previous_tracking.get("baseline_keys") or [])
    previous_watch_rows = _index_rows(list(previous_payload.get("verified_watch") or []))

    cex_payload = _load(data_dir / "cex-revival-radar.json", {})
    precursor_payload = _load(data_dir / "revival-precursor-latest.json", {})
    waking_payload = _load(data_dir / "waking-confirmation-latest.json", {})
    revival_payload = _load(data_dir / "revival-1000-latest.json", {})
    envelope_payload = _load(data_dir / "candidate-evidence-envelope.json", {})
    active_rows = _load(data_dir / "active-qualified-candidates.json", [])

    cex_rows = list(cex_payload.get("alerts") or [])
    precursor_rows = list(precursor_payload.get("targets") or [])
    waking_rows = list(waking_payload.get("targets") or [])
    revival_rows = list(revival_payload.get("coins") or [])
    envelope_rows = list(envelope_payload.get("candidates") or [])
    active_rows = active_rows if isinstance(active_rows, list) else []

    indexes = {
        "cex": _index_rows(cex_rows),
        "precursor": _index_rows(precursor_rows),
        "waking": _index_rows(waking_rows),
        "revival": _index_rows(revival_rows),
        "envelope": _index_rows(envelope_rows),
        "active": _index_rows(active_rows),
    }
    keys = set().union(*(set(index) for index in indexes.values()))

    real_alerts = []
    verified_watch = []
    for k in keys:
        cex = indexes["cex"].get(k) or {}
        precursor = indexes["precursor"].get(k) or {}
        waking = indexes["waking"].get(k) or {}
        revival = indexes["revival"].get(k) or {}
        envelope = indexes["envelope"].get(k) or {}
        active = indexes["active"].get(k) or {}
        rows = (active, precursor, waking, cex, revival, envelope)
        chain, token, exact_identity = _identity_truth(*rows)
        pair, exact_pair = _pair_truth(*rows)
        execution_liq, total_dex_liq, execution_pair, liquidity_source = _execution_liquidity_truth(*rows)
        if execution_pair:
            pair = execution_pair
            exact_pair = True
        age_ok, age_days = _age_ok(*rows)
        lanes, lane_count = _source_score(precursor, waking, cex, active, revival)
        blocked, risk_reasons = _risk_blocked(*rows)
        precursor_status = precursor.get("status")
        production_pass = active.get("qualification") in {"QUALIFIED", "REVIVAL_QUALIFIED"}
        precursor_pass = precursor_status in REAL_PRECURSOR_STATUSES
        envelope_status = str(envelope.get("status") or "")
        envelope_coverage = envelope.get("coverage") if isinstance(envelope.get("coverage"), dict) else {}
        evidence_positive_lanes = list(envelope_coverage.get("positive_independent_lanes") or [])
        evidence_verified_lanes = list(envelope_coverage.get("verified_independent_lanes") or [])

        liquidity_ok = execution_liq >= cfg.verified_min_liquidity_usd
        strong_decision = production_pass or precursor_pass
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

        signal_score, signal_leader, score_components = _signal_context(precursor, waking, cex, revival, envelope)
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

        item = {
            "symbol": _symbol(active, precursor, waking, cex, revival, envelope),
            "chain": chain,
            "token_address": token,
            "pair_address": pair,
            "dex": _first(cex.get("dex"), active.get("dex"), revival.get("dex")),
            "dex_url": _first(cex.get("dex_url"), active.get("url"), revival.get("dex_url"), revival.get("dex_link"), envelope.get("dex_url")),
            "price_usd": _price(active, precursor, waking, cex, revival, envelope),
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
            "first_alert_at": _first((cex.get("milestones") or {}).get("first_alert", {}).get("observed_at"), precursor.get("t0", {}).get("observed_at"), active.get("qualified_at")),
            "exact_identity_verified": exact_identity,
            "exact_pair_verified": exact_pair,
            "market_age_verified": age_ok,
            "blockers": blockers,
        }
        if not blockers:
            item["status"] = "REAL_ALERT"
            item["actionable_research_alert"] = True
            real_alerts.append(item)
        else:
            watch_interest = bool(
                lane_count >= 1
                or envelope_status in {"EVIDENCE_READY", "VERIFIED_WATCH"}
                or revival.get("watch_status") == "WAKING_MARKET_ONLY"
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
    verified_watch.sort(
        key=lambda x: (
            tier_priority.get(x.get("radar_tier"), 0),
            x.get("watch_is_new_24h") is True,
            str(x.get("watch_added_at") or ""),
            x.get("readiness_passed") or 0,
            x.get("evidence_ready") is True,
            x.get("source_lane_count") or 0,
            x.get("signal_score") or 0,
        ),
        reverse=True,
    )
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
    if tracking_initialized:
        baseline_keys = sorted(k for k in previous_baseline_keys if k in active_registry)
    else:
        baseline_keys = sorted(active_registry.keys())

    return {
        "version": 3,
        "generated_at": now,
        "mode": "FAIL_CLOSED_REAL_ALERT_FEED_V3_EVIDENCE_ENVELOPE",
        "score_contract": {
            "signal_score_semantics": "maximum currently available subsystem signal; not a probability and not overall conviction",
            "confirmation_total_lanes": SOURCE_LANE_TOTAL,
            "readiness_gate_total": 7,
            "readiness_is_gate_completion_not_profit_probability": True,
            "radar_tiers": ["REAL_ALERT", "NEAR_ALERT", "VERIFIED_WATCH", "BLOCKED", "IDENTITY_PENDING"],
        },
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "minimum_market_age_days": 180,
            "minimum_execution_pool_liquidity_usd": cfg.verified_min_liquidity_usd,
            "liquidity_gate_metric": "EXECUTION_POOL_LIQUIDITY_USD",
            "dex_total_liquidity_is_informational_only": True,
            "exact_onchain_identity_required": True,
            "exact_dex_pair_required": True,
            "symbol_only_never_actionable": True,
            "cex_only_never_real_alert": True,
            "production_gate_or_strong_precursor_required": True,
            "non_production_alert_requires_min_independent_lanes": 2,
            "evidence_ready_is_visible_but_does_not_auto_promote_to_real_alert": True,
            "late_move_or_pump_dump_never_real_alert": True,
            "label_meaning": "REAL_ALERT means the system's strict research alert criteria are met; it is not a guarantee of profit or an instruction to buy.",
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
            "near_alert_not_real": near_count,
            "verified_watch_core": plain_watch_count,
            "blocked_verified_watch": blocked_count,
            "verified_watch_not_real": len(verified_watch),
            "new_watch_24h": new_watch_count,
            "evidence_ready_research": evidence_ready_count,
            "identity_pending_not_actionable": len(identity_pending),
        },
        "latest_real_alert": real_alerts[0] if real_alerts else None,
        "alerts": real_alerts,
        "verified_watch": verified_watch[:50],
        "identity_pending": identity_pending[:50],
    }


def run(data_dir: Path = DATA) -> dict:
    from .liquidity_truth_guard import sanitize_real_alerts

    path = data_dir / "real-alerts.json"
    payload = build(data_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sanitize_real_alerts(path)
    final_payload = _load(path, {})
    truth = final_payload.get("truth_contract") if isinstance(final_payload.get("truth_contract"), dict) else {}
    truth["producer_liquidity_sanitized_before_publish"] = True
    final_payload["truth_contract"] = truth
    path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return final_payload.get("counts") or {}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))