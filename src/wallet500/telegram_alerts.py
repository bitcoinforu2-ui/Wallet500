from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from wallet500.policy import (
    CANONICAL_MIN_EXECUTION_LIQUIDITY_USD,
    CANONICAL_MIN_MARKET_AGE_DAYS,
)

MIN_MARKET_AGE_DAYS = CANONICAL_MIN_MARKET_AGE_DAYS
MIN_LIQUIDITY_USD = CANONICAL_MIN_EXECUTION_LIQUIDITY_USD
MIN_VOLUME_H1_USD = 15_000.0
MIN_ACTIVITY_H1 = 50
PRE_WAVE_MIN_VOLUME_H1_USD = 1_000.0
PRE_WAVE_MIN_CEX_CONFIRMATIONS = 3
PRE_WAVE_MIN_CEX_EXCHANGES = 3
CANONICAL_REAL_READINESS_TOTAL = 7
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
EVM_CHAINS = {"ethereum", "bsc", "bnb", "eth", "base", "arbitrum", "optimism", "polygon", "avalanche"}


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _norm_addr(value: object) -> str:
    return str(value or "").strip().lower()


def _pair_key(row: dict) -> str:
    chain = str(row.get("chain") or "unknown").lower()
    token = str(row.get("token") or row.get("mint") or row.get("token_address") or "")
    pair = str(row.get("pair_address") or "")
    if chain in EVM_CHAINS:
        token, pair = token.lower(), pair.lower()
    return f"{chain}:{token}:{pair}"


def _alert_event_id(key: str, sent_at: str) -> str:
    return hashlib.sha256(f"{key}|{sent_at}".encode("utf-8")).hexdigest()[:16]


def _exact_pair_locked(row: dict) -> bool:
    pair = _norm_addr(row.get("pair_address"))
    locked = _norm_addr(row.get("locked_pair_address"))
    return bool(pair and locked and pair == locked and row.get("pair_identity_locked") is True)


def _mature_market_verified(row: dict) -> bool:
    if row.get("market_age_verified") is not True:
        return False
    try:
        return int(row.get("market_age_min_days") or 0) >= MIN_MARKET_AGE_DAYS
    except Exception:
        return False


def _fmt_money(v) -> str:
    try:
        n = float(v)
    except Exception:
        return "n/a"
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n / 1_000:.1f}K"
    if abs(n) >= 1:
        return f"${n:.2f}"
    if n == 0:
        return "$0"
    return f"${n:.8f}".rstrip("0").rstrip(".")


def _fmt_israel_time(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "n/a"
    try:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return raw


def _tier(row: dict) -> str | None:
    """Legacy production-candidate validation.

    This remains supported as additional context, but it is no longer the only path
    to a Telegram REAL ALERT. The canonical real-alerts.json producer can promote a
    valid REAL ALERT through other verified decision lanes as well.
    """
    if not _mature_market_verified(row):
        return None
    if row.get("qualification") not in {"QUALIFIED", "REVIVAL_QUALIFIED"}:
        return None
    if row.get("live_survival_gate") != "ACTIVE" or row.get("pump_dump_blocked"):
        return None
    if not _exact_pair_locked(row):
        return None
    if row.get("holder_cluster_production_status") != "PASS":
        return None
    if row.get("holder_cluster_verification_complete") is not True:
        return None

    try:
        score = float(row.get("anomaly_score") or 0)
        liquidity = float(row.get("execution_pool_liquidity_usd") or row.get("live_liquidity_usd") or row.get("liquidity_usd") or 0)
        volume = float(row.get("live_volume_h1") or row.get("volume_h1") or 0)
        activity = int(row.get("live_activity_h1") or 0)
    except (TypeError, ValueError):
        return None
    risk = str(row.get("pump_dump_risk_level") or "").upper()
    if liquidity < MIN_LIQUIDITY_USD or volume < MIN_VOLUME_H1_USD or activity < MIN_ACTIVITY_H1:
        return None
    if risk in {"HIGH", "CRITICAL"}:
        return None
    if score >= 90 and volume >= 30_000 and risk == "LOW":
        return "HIGH_CONVICTION"
    return "QUALIFIED"


def _is_actionable_real_alert(row: object) -> bool:
    return bool(isinstance(row, dict) and row.get("status") == "REAL_ALERT" and row.get("actionable_research_alert") is True)


def _canonical_real_tier(row: object) -> str | None:
    """Validate the published canonical REAL ALERT itself, fail closed.

    real-alerts.json is produced only after the full decision snapshot and is then
    sanitized by the liquidity/activity truth guard. Telegram must therefore follow
    that canonical exact-pair transition instead of depending on the legacy
    active-qualified-candidates.json list, which is not a complete index of all
    valid REAL ALERT decision lanes.
    """
    if not _is_actionable_real_alert(row) or not isinstance(row, dict):
        return None
    if row.get("automatic_buy") is not False:
        return None
    if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
        return None
    if row.get("market_age_verified") is not True:
        return None
    if not str(row.get("chain") or "").strip() or not str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip():
        return None
    if not str(row.get("pair_address") or "").strip():
        return None

    try:
        age = int(float(row.get("market_age_days") or row.get("market_age_min_days") or 0))
        liquidity = float(row.get("execution_pool_liquidity_usd") or row.get("liquidity_usd") or 0)
        readiness_passed = int(row.get("readiness_passed") or 0)
        readiness_total = int(row.get("readiness_total") or 0)
        score = float(row.get("score") or row.get("signal_score") or 0)
        volume = float(row.get("dex_volume_h1") or row.get("volume_h1") or 0)
    except (TypeError, ValueError):
        return None

    if age < MIN_MARKET_AGE_DAYS or liquidity < MIN_LIQUIDITY_USD:
        return None
    if str(row.get("radar_tier") or "") != "REAL_ALERT":
        return None
    if readiness_total < CANONICAL_REAL_READINESS_TOTAL or readiness_passed != readiness_total:
        return None
    readiness = row.get("readiness_gates") if isinstance(row.get("readiness_gates"), dict) else {}
    if len(readiness) < CANONICAL_REAL_READINESS_TOTAL or any(v is not True for v in readiness.values()):
        return None
    if row.get("missing_gates"):
        return None
    if row.get("blockers") or row.get("risk_reasons"):
        return None
    risk = str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper()
    if risk in {"HIGH", "CRITICAL"}:
        return None

    # Concentrated pools remain fail-closed unless real execution depth was verified.
    if row.get("concentrated_liquidity_pool") is True and row.get("execution_depth_verified") is not True:
        return None
    activity_truth = row.get("dex_activity_truth") if isinstance(row.get("dex_activity_truth"), dict) else {}
    if activity_truth.get("blockers"):
        return None

    if score >= 90 and volume >= 30_000 and str(row.get("pump_dump_risk_level") or "").upper() == "LOW":
        return "HIGH_CONVICTION"
    return "QUALIFIED"


def _is_pre_wave_alert(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("status") != "PRE_WAVE_ALERT" or row.get("user_alert_eligible") is not True:
        return False
    if row.get("manual_decision_only") is not True or row.get("automatic_buy") is not False:
        return False
    if row.get("research_only") is True or row.get("actionable_research_alert") is True:
        return False
    if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
        return False
    if row.get("market_age_verified") is not True:
        return False
    try:
        if int(row.get("market_age_days") or 0) < MIN_MARKET_AGE_DAYS:
            return False
        liq = float(row.get("execution_pool_liquidity_usd") or row.get("liquidity_usd") or 0)
        volume = float(row.get("dex_volume_h1") or row.get("volume_h1") or 0)
        spot_conf = int(row.get("cex_spot_confirmations") or 0)
        spot_exchanges = len(set(row.get("cex_spot_exchanges") or []))
    except (TypeError, ValueError):
        return False
    if liq < MIN_LIQUIDITY_USD or volume < PRE_WAVE_MIN_VOLUME_H1_USD:
        return False
    if spot_conf < PRE_WAVE_MIN_CEX_CONFIRMATIONS or spot_exchanges < PRE_WAVE_MIN_CEX_EXCHANGES:
        return False
    if row.get("risk_reasons"):
        return False
    gates = row.get("pre_wave_gates") if isinstance(row.get("pre_wave_gates"), dict) else {}
    if gates.get("cex_spot_breadth") is not True or gates.get("multichain_market_activity") is not True:
        return False
    return True


def _merge_display_context(active: dict, real: dict) -> dict:
    merged = dict(active)
    for key in (
        "symbol", "name", "chain", "token_address", "pair_address", "dex", "dex_url", "price_usd",
        "liquidity_usd", "execution_pool_liquidity_usd", "market_age_days", "market_age_verified", "score",
        "signal_score", "source_lanes", "source_lane_count", "evidence_envelope_status", "evidence_ready",
        "evidence_positive_lanes", "evidence_verified_lanes", "status", "radar_tier", "risk_level", "risk_reasons",
        "actionable_research_alert", "first_alert_at", "readiness_passed", "readiness_total", "readiness_gates",
        "dex_volume_h1", "volume_h1", "buys_h1", "sells_h1", "automatic_buy", "exact_identity_verified",
        "exact_pair_verified", "dex_activity_truth", "concentrated_liquidity_pool", "execution_depth_verified",
    ):
        value = real.get(key)
        if value not in (None, "", [], {}):
            merged[key] = value
    if real.get("dex_url"):
        merged["url"] = real["dex_url"]
    return merged


def _message(row: dict, tier: str, sent_at: str | None = None, alert_event_id: str | None = None) -> str:
    chain = str(row.get("chain") or "unknown").upper().replace("BSC", "BNB")
    symbol = str(row.get("symbol") or row.get("name") or "UNKNOWN")
    token = str(row.get("token") or row.get("mint") or row.get("token_address") or "unknown")
    pair = str(row.get("pair_address") or "unknown")
    dex = str(row.get("dex") or "unknown")
    score = float(row.get("score") or row.get("anomaly_score") or row.get("signal_score") or 0)
    risk = str(row.get("pump_dump_risk_level") or row.get("risk_level") or "n/a").upper()
    liquidity = row.get("execution_pool_liquidity_usd") or row.get("live_liquidity_usd") or row.get("liquidity_usd")
    volume = row.get("live_volume_h1") or row.get("dex_volume_h1") or row.get("volume_h1")
    buys, sells = int(row.get("buys_h1") or 0), int(row.get("sells_h1") or 0)
    price = row.get("price_usd")
    pair_age = row.get("pair_age_minutes")
    market_age = int(row.get("market_age_days") or row.get("market_age_min_days") or 0)
    dex_url = row.get("dex_url") or row.get("url") or ""
    pair_checked = row.get("survival_checked_at") or row.get("holder_cluster_checked_at") or "n/a"
    age_source = row.get("market_age_evidence_source") or "verified market evidence"
    positive_lanes = list(row.get("evidence_positive_lanes") or [])
    verified_lanes = list(row.get("evidence_verified_lanes") or [])
    source_lanes = list(row.get("source_lanes") or [])
    evidence_ready = row.get("evidence_ready") is True or row.get("evidence_envelope_status") == "EVIDENCE_READY"
    readiness_passed = int(row.get("readiness_passed") or 0)
    readiness_total = int(row.get("readiness_total") or 0)
    holder_pass = row.get("holder_cluster_production_status") == "PASS" and row.get("holder_cluster_verification_complete") is True
    sent_at = sent_at or datetime.now(timezone.utc).isoformat()
    sent_israel = _fmt_israel_time(sent_at)
    signal_israel = _fmt_israel_time(row.get("first_alert_at"))
    title = "🔥 HIGH-CONVICTION BUY REVIEW" if tier == "HIGH_CONVICTION" else "🚨 BUY REVIEW"
    pair_age_text = f"{float(pair_age):.0f}m" if pair_age is not None else "n/a"
    promotion = "EVIDENCE_READY → ACTIONABLE" if evidence_ready else "VERIFIED → ACTIONABLE"
    lines = [
        f"{title} — WALLET500", "🆕 NEW REAL ALERT",
        f"📅 תאריך ושעת שליחת ההתראה (ישראל): {sent_israel}",
        f"🕒 T0 אות מקורי (ישראל): {signal_israel}",
    ]
    if alert_event_id:
        lines.append(f"🧾 Alert ID: {alert_event_id}")
    lines.extend([
        "⚠️ MANUAL DECISION ONLY — NO AUTOMATIC TRADE", f"Promotion: {promotion} ✅",
        f"Token: {symbol}", f"Chain: {chain}", f"Contract: {token}", f"Pair: {pair}", f"DEX: {dex}",
        "Pair identity: EXACT VERIFIED ✅", f"Pair checked: {pair_checked}", f"Market age: ≥{market_age}d ✅",
        f"Age proof: {age_source}", f"Current pair age: {pair_age_text}", f"Research/Revival score: {score:.2f}/100",
        f"Price: {_fmt_money(price)}", f"Liquidity: {_fmt_money(liquidity)} ✅ min ${MIN_LIQUIDITY_USD/1000:.0f}K",
        f"Volume 1H: {_fmt_money(volume)}", f"Buys/Sells 1H: {buys}/{sells}", f"Pump/Dump Risk: {risk}",
    ])
    if readiness_total:
        lines.append(f"Canonical REAL ALERT readiness: {readiness_passed}/{readiness_total} ✅")
    if holder_pass:
        lines.append("Holder/Cluster evidence: COMPLETE PASS")
    lines.append("Actionable research alert: YES ✅")
    if source_lanes:
        lines.append(f"Decision lanes: {', '.join(map(str, source_lanes))}")
    if positive_lanes:
        lines.append(f"Positive evidence: {', '.join(map(str, positive_lanes))}")
    if verified_lanes:
        lines.append(f"Verified evidence: {', '.join(map(str, verified_lanes))}")
    lines.append("Verified Intelligence. The Pure Truth.")
    if dex_url:
        lines.append(f"🔗 OPEN DEX: {dex_url}")
    return "\n".join(lines)


def _pre_wave_message(row: dict, sent_at: str | None = None, alert_event_id: str | None = None) -> str:
    chain = str(row.get("chain") or "unknown").upper().replace("BSC", "BNB")
    symbol = str(row.get("symbol") or row.get("name") or "UNKNOWN")
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or "unknown")
    pair = str(row.get("pair_address") or "unknown")
    dex = str(row.get("dex") or "unknown")
    sent_at = sent_at or datetime.now(timezone.utc).isoformat()
    gates = row.get("pre_wave_gates") if isinstance(row.get("pre_wave_gates"), dict) else {}
    missing = list(row.get("full_real_alert_pending_gates") or [])
    exchanges = list(row.get("cex_spot_exchanges") or [])
    liquidity = row.get("execution_pool_liquidity_usd") or row.get("liquidity_usd")
    volume = row.get("dex_volume_h1") or row.get("volume_h1")
    price = row.get("price_usd")
    dex_url = row.get("dex_url") or row.get("url") or ""
    lines = [
        "🔥🔥🔥 PRE-WAVE ALERT — WALLET500",
        "⚠️ MANUAL REVIEW ONLY — NOT A BUY ORDER — NO AUTOMATIC TRADE",
        f"📅 נשלח (ישראל): {_fmt_israel_time(sent_at)}",
        f"🕒 אות מוקדם ראשון (ישראל): {_fmt_israel_time(row.get('first_alert_at'))}",
    ]
    if alert_event_id:
        lines.append(f"🧾 Alert ID: {alert_event_id}")
    lines.extend([
        f"Token: {symbol}", f"Chain: {chain}", f"Contract: {token}", f"Pair: {pair}", f"DEX: {dex}",
        "Exact identity + exact pair: PASS ✅", f"Market age: ≥{int(row.get('market_age_days') or 0)}d ✅",
        f"Price: {_fmt_money(price)}", f"Liquidity: {_fmt_money(liquidity)} ✅", f"DEX Volume 1H: {_fmt_money(volume)}",
        f"CEX Spot score: {float(row.get('cex_spot_score') or 0):.1f}",
        f"CEX confirmations: {int(row.get('cex_spot_confirmations') or 0)}",
        f"CEX exchanges: {', '.join(map(str, exchanges)) if exchanges else 'n/a'}",
        f"Spot 24H move at detection: {gates.get('spot_change_24h_max_pct') if gates.get('spot_change_24h_max_pct') is not None else 'n/a'}%",
        "On-chain activity before full production confirmation: PASS ✅",
        f"Full REAL ALERT still pending: {', '.join(map(str, missing)) if missing else 'none'}",
        "Verified Intelligence. The Pure Truth.",
    ])
    if dex_url:
        lines.append(f"🔗 OPEN DEX: {dex_url}")
    return "\n".join(lines)


def _send(bot_token: str, chat_id: str, text: str, max_attempts: int = 3) -> tuple[int | None, int]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read().decode("utf-8", errors="replace")
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"Telegram HTTP {response.status}")
                payload = json.loads(raw) if raw else {}
                if payload.get("ok") is not True:
                    raise RuntimeError("Telegram API returned ok=false")
                result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                message_id = result.get("message_id")
                return int(message_id) if message_id is not None else None, attempt
        except urllib.error.HTTPError as exc:
            last_error = exc
            if not (exc.code == 429 or 500 <= exc.code < 600) or attempt >= max_attempts:
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt >= max_attempts:
                raise
        time.sleep(float(attempt))
    raise RuntimeError(f"Telegram delivery failed after {max_attempts} attempts: {last_error}")


def run() -> dict:
    out = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
    source_name = os.getenv("WALLET500_ALERT_INPUT", "active-qualified-candidates.json")
    real_source_name = os.getenv("WALLET500_REAL_ALERT_INPUT", "real-alerts.json")
    candidates = _load(out / source_name, [])
    real_payload = _load(out / real_source_name, {})
    state_path = out / "telegram-alert-state.json"
    if not isinstance(candidates, list):
        candidates = []

    real_rows = list(real_payload.get("alerts") or []) if isinstance(real_payload, dict) else []
    pre_wave_rows = list(real_payload.get("pre_wave_alerts") or []) if isinstance(real_payload, dict) else []
    candidate_index = {_pair_key(row): row for row in candidates if isinstance(row, dict) and _pair_key(row)}

    state = _load(state_path, {})
    if not isinstance(state, dict):
        state = {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(bot_token and chat_id)
    if not configured:
        existing = _load(out / "telegram-alert-report.json", {})
        skipped = {
            "status": "SKIPPED_UNCONFIGURED_NO_STATE_WRITE",
            "reason": "TELEGRAM_SECRETS_NOT_PRESENT_IN_THIS_LANE",
            "preserved_existing_report": isinstance(existing, dict) and bool(existing),
        }
        print(json.dumps(skipped, indent=2, ensure_ascii=False))
        return existing if isinstance(existing, dict) else skipped

    now = datetime.now(timezone.utc).isoformat()
    now_israel = _fmt_israel_time(now)
    delivered, eligible, errors = [], [], []
    active_real_now: set[str] = set()
    active_pre_wave_now: set[str] = set()

    # Canonical REAL ALERTs are the transition source. Legacy production candidates
    # may enrich the message/tier when present, but their absence must never suppress
    # a fully validated canonical REAL ALERT.
    for real in real_rows:
        if not isinstance(real, dict) or not _is_actionable_real_alert(real):
            continue
        key = _pair_key(real)
        if not key or key.endswith("::"):
            continue
        active = candidate_index.get(key) or {}
        tier = _tier(active) if active else None
        if not tier:
            tier = _canonical_real_tier(real)
        if not tier:
            continue
        active_real_now.add(key)
        display = _merge_display_context(active, real) if active else dict(real)
        pair_address = display.get("pair_address") or real.get("pair_address")
        fingerprint_pair = _norm_addr(active.get("locked_pair_address") or pair_address)
        fingerprint = f"REAL_ALERT:{tier}:{fingerprint_pair}"
        eligible.append({
            "alert_type": "REAL_ALERT",
            "key": key,
            "tier": tier,
            "symbol": display.get("symbol"),
            "pair_address": pair_address,
            "market_age_min_days": active.get("market_age_min_days") or real.get("market_age_days") or real.get("market_age_min_days"),
            "promotion": "EVIDENCE_READY_TO_ACTIONABLE" if display.get("evidence_ready") else "VERIFIED_TO_ACTIONABLE",
            "dex_url": display.get("dex_url") or display.get("url"),
            "delivery_truth_source": "CANONICAL_REAL_ALERT" if not active else "CANONICAL_REAL_ALERT_PLUS_LEGACY_CONTEXT",
        })
        previous = sent.get(key) if isinstance(sent.get(key), dict) else {}
        if previous.get("actionable") is True:
            continue
        event_id = _alert_event_id(key, now)
        try:
            telegram_message_id, attempts = _send(bot_token, chat_id, _message(display, tier, sent_at=now, alert_event_id=event_id))
            sent[key] = {
                "fingerprint": fingerprint,
                "alert_event_id": event_id,
                "telegram_message_id": telegram_message_id,
                "delivery_attempts": attempts,
                "tier": tier,
                "symbol": display.get("symbol"),
                "pair_address": pair_address,
                "actionable": True,
                "sent_at": now,
                "sent_at_israel": now_israel,
                "dex_url": display.get("dex_url") or display.get("url"),
                "delivery_truth_source": "CANONICAL_REAL_ALERT",
            }
            delivered.append({
                "alert_type": "REAL_ALERT",
                "key": key,
                "alert_event_id": event_id,
                "telegram_message_id": telegram_message_id,
                "delivery_attempts": attempts,
                "tier": tier,
                "symbol": display.get("symbol"),
                "pair_address": pair_address,
                "sent_at": now,
                "sent_at_israel": now_israel,
                "dex_url": display.get("dex_url") or display.get("url"),
                "delivery_truth_source": "CANONICAL_REAL_ALERT",
            })
        except Exception as exc:
            errors.append({"alert_type": "REAL_ALERT", "key": key, "alert_event_id": event_id, "error": f"{type(exc).__name__}: {exc}"[:300]})

    for row in pre_wave_rows:
        if not _is_pre_wave_alert(row):
            continue
        key = _pair_key(row)
        state_key = f"PRE_WAVE:{key}"
        active_pre_wave_now.add(state_key)
        eligible.append({
            "alert_type": "PRE_WAVE_ALERT",
            "key": key,
            "tier": "PRE_WAVE",
            "symbol": row.get("symbol"),
            "pair_address": row.get("pair_address"),
            "market_age_min_days": row.get("market_age_days"),
            "promotion": "EARLY_MANUAL_REVIEW",
            "dex_url": row.get("dex_url") or row.get("url"),
        })
        previous = sent.get(state_key) if isinstance(sent.get(state_key), dict) else {}
        if previous.get("pre_wave_active") is True:
            continue
        event_id = _alert_event_id(state_key, now)
        try:
            telegram_message_id, attempts = _send(bot_token, chat_id, _pre_wave_message(row, sent_at=now, alert_event_id=event_id))
            sent[state_key] = {
                "fingerprint": f"PRE_WAVE:{_norm_addr(row.get('pair_address'))}",
                "alert_event_id": event_id,
                "telegram_message_id": telegram_message_id,
                "delivery_attempts": attempts,
                "tier": "PRE_WAVE",
                "symbol": row.get("symbol"),
                "pair_address": row.get("pair_address"),
                "pre_wave_active": True,
                "actionable": False,
                "sent_at": now,
                "sent_at_israel": now_israel,
                "dex_url": row.get("dex_url") or row.get("url"),
            }
            delivered.append({
                "alert_type": "PRE_WAVE_ALERT",
                "key": key,
                "alert_event_id": event_id,
                "telegram_message_id": telegram_message_id,
                "delivery_attempts": attempts,
                "tier": "PRE_WAVE",
                "symbol": row.get("symbol"),
                "pair_address": row.get("pair_address"),
                "sent_at": now,
                "sent_at_israel": now_israel,
                "dex_url": row.get("dex_url") or row.get("url"),
            })
        except Exception as exc:
            errors.append({"alert_type": "PRE_WAVE_ALERT", "key": key, "alert_event_id": event_id, "error": f"{type(exc).__name__}: {exc}"[:300]})

    for key, info in list(sent.items()):
        if not isinstance(info, dict):
            continue
        if key.startswith("PRE_WAVE:"):
            if info.get("pre_wave_active") is True and key not in active_pre_wave_now:
                info["pre_wave_active"] = False
                info["cleared_at"] = now
                sent[key] = info
        elif info.get("actionable") is True and key not in active_real_now:
            info["actionable"] = False
            info["cleared_at"] = now
            sent[key] = info

    if len(sent) > 5000:
        sent = dict(sorted(sent.items(), key=lambda kv: kv[1].get("sent_at", "") if isinstance(kv[1], dict) else "", reverse=True)[:5000])

    report = {
        "version": 13,
        "updated_at": now,
        "updated_at_israel": now_israel,
        "configured": True,
        "candidate_count": len(candidates),
        "real_alert_count": len(real_rows),
        "pre_wave_alert_count": len(pre_wave_rows),
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "eligible": eligible,
        "delivered": delivered,
        "errors": errors,
        "policy": {
            "source": real_source_name,
            "legacy_candidate_context_source": source_name,
            "real_alert_source": real_source_name,
            "lane": "PRODUCTION_CANONICAL_REAL_ALERT_PLUS_PRE_WAVE_TELEGRAM_V13",
            "canonical_policy_source": "wallet500.policy",
            "transition_rule": "send once when an exact-pair canonical REAL_ALERT passes the published fail-closed readiness contract; legacy active candidates enrich but never suppress it; PRE_WAVE remains separate",
            "research_only_notifications": "FORBIDDEN",
            "pre_wave": {
                "meaning": "earlier manual-review warning, separate from REAL_ALERT and never a buy instruction",
                "requires": [
                    "status=PRE_WAVE_ALERT and user_alert_eligible=true",
                    "research_only=false and actionable_research_alert=false and automatic_buy=false",
                    "exact identity + exact pair + verified market age >=180d",
                    f"verified execution liquidity>={int(MIN_LIQUIDITY_USD)}",
                    f"DEX volume_h1>={int(PRE_WAVE_MIN_VOLUME_H1_USD)}",
                    f"CEX spot confirmations>={PRE_WAVE_MIN_CEX_CONFIRMATIONS} across >= {PRE_WAVE_MIN_CEX_EXCHANGES} exchanges",
                    "multichain on-chain activity gate=true and risk clear",
                ],
                "format": "three fire symbols + explicit manual review / not a buy order",
            },
            "real_alert_requires": [
                "canonical real-alerts.json row with status=REAL_ALERT and actionable_research_alert=true",
                "automatic_buy=false",
                "exact_identity_verified=true and exact_pair_verified=true",
                f"market_age_verified=true and market_age_days>={MIN_MARKET_AGE_DAYS}",
                f"execution_pool_liquidity_usd>={int(MIN_LIQUIDITY_USD)}",
                f"readiness_passed=readiness_total>={CANONICAL_REAL_READINESS_TOTAL} with every readiness gate true",
                "missing_gates=[], blockers=[], risk_reasons=[]",
                "radar_tier=REAL_ALERT and risk not HIGH/CRITICAL",
                "concentrated pools require verified execution depth",
                "post-producer DEX activity truth must have no blockers",
            ],
            "legacy_candidate_policy": "OPTIONAL_CONTEXT_ONLY_NEVER_A_REAL_ALERT_DELIVERY_DEPENDENCY",
            "research_90d_15k_lane": "SEPARATE_NON_PRODUCTION_LANE; NEVER REDEFINES REAL_ALERT",
            "high_conviction": f"canonical score>=90 and volume_h1>=30000 with explicit LOW pump/dump risk; otherwise QUALIFIED",
            "manual_execution": "Telegram alerts are review alerts only; no automatic trade is executed",
            "dedupe": "separate transition state for REAL_ALERT and PRE_WAVE per chain+token+exact_pair; later REAL_ALERT remains independently deliverable",
            "telegram_timestamp": "every delivered message includes explicit Asia/Jerusalem send date/time plus original signal T0",
            "delivery_retries": "up to 3 attempts on transient Telegram/network failures",
            "audit_id": "each delivery has a stable alert_event_id derived from exact-pair stage key plus send timestamp",
            "state_writer": "only configured production lanes may write Telegram state/report; unconfigured scan lanes are read-only no-ops",
        },
    }
    _write(state_path, {"updated_at": now, "updated_at_israel": now_israel, "sent": sent})
    _write(out / "telegram-alert-report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == "__main__":
    run()
