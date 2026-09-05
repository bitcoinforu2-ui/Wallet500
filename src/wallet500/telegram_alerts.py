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

MIN_MARKET_AGE_DAYS = 180
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _norm_addr(value: object) -> str:
    return str(value or "").strip().lower()


def _pair_key(row: dict) -> str:
    chain = str(row.get("chain") or "unknown").lower()
    token = str(row.get("token") or row.get("mint") or row.get("token_address") or "")
    pair = str(row.get("pair_address") or "")
    if chain in {"ethereum", "bsc", "bnb", "eth"}:
        token = token.lower()
        pair = pair.lower()
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
    if not _mature_market_verified(row):
        return None
    if row.get("qualification") not in {"QUALIFIED", "REVIVAL_QUALIFIED"}:
        return None
    if row.get("live_survival_gate") != "ACTIVE":
        return None
    if row.get("pump_dump_blocked"):
        return None
    if not _exact_pair_locked(row):
        return None
    if row.get("holder_cluster_production_status") != "PASS":
        return None
    if row.get("holder_cluster_verification_complete") is not True:
        return None

    score = float(row.get("anomaly_score") or 0)
    liquidity = float(row.get("live_liquidity_usd") or row.get("liquidity_usd") or 0)
    volume = float(row.get("live_volume_h1") or row.get("volume_h1") or 0)
    activity = int(row.get("live_activity_h1") or 0)
    risk = str(row.get("pump_dump_risk_level") or "").upper()
    if liquidity < 50_000 or volume < 15_000 or activity < 50:
        return None
    if risk in {"HIGH", "CRITICAL"}:
        return None
    if score >= 90 and volume >= 30_000 and risk == "LOW":
        return "HIGH_CONVICTION"
    return "QUALIFIED"


def _is_actionable_real_alert(row: object) -> bool:
    return bool(
        isinstance(row, dict)
        and row.get("status") == "REAL_ALERT"
        and row.get("actionable_research_alert") is True
    )


def _merge_display_context(active: dict, real: dict) -> dict:
    """Keep production-gate truth from active while enriching the Telegram display from REAL ALERT."""
    merged = dict(active)
    display_keys = (
        "symbol",
        "name",
        "token_address",
        "dex",
        "dex_url",
        "price_usd",
        "liquidity_usd",
        "execution_pool_liquidity_usd",
        "market_age_days",
        "score",
        "source_lanes",
        "source_lane_count",
        "evidence_envelope_status",
        "evidence_ready",
        "evidence_positive_lanes",
        "evidence_verified_lanes",
        "status",
        "actionable_research_alert",
        "first_alert_at",
    )
    for key in display_keys:
        value = real.get(key)
        if value not in (None, "", [], {}):
            merged[key] = value
    if real.get("dex_url"):
        merged["url"] = real["dex_url"]
    return merged


def _message(
    row: dict,
    tier: str,
    sent_at: str | None = None,
    alert_event_id: str | None = None,
) -> str:
    chain = str(row.get("chain") or "unknown").upper().replace("BSC", "BNB")
    symbol = str(row.get("symbol") or row.get("name") or "UNKNOWN")
    token = str(row.get("token") or row.get("mint") or row.get("token_address") or "unknown")
    pair = str(row.get("pair_address") or "unknown")
    dex = str(row.get("dex") or "unknown")
    score = float(row.get("score") or row.get("anomaly_score") or 0)
    risk = str(row.get("pump_dump_risk_level") or "n/a").upper()
    liquidity = (
        row.get("execution_pool_liquidity_usd")
        or row.get("live_liquidity_usd")
        or row.get("liquidity_usd")
    )
    volume = row.get("live_volume_h1") or row.get("volume_h1")
    buys = int(row.get("buys_h1") or 0)
    sells = int(row.get("sells_h1") or 0)
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
    sent_at = sent_at or datetime.now(timezone.utc).isoformat()
    sent_israel = _fmt_israel_time(sent_at)
    signal_israel = _fmt_israel_time(row.get("first_alert_at"))

    title = "🔥 HIGH-CONVICTION BUY REVIEW" if tier == "HIGH_CONVICTION" else "🚨 BUY REVIEW"
    pair_age_text = f"{float(pair_age):.0f}m" if pair_age is not None else "n/a"
    promotion = "EVIDENCE_READY → ACTIONABLE" if evidence_ready else "VERIFIED → ACTIONABLE"

    lines = [
        f"{title} — WALLET500",
        "🆕 NEW REAL ALERT",
        f"📅 תאריך ושעת שליחת ההתראה (ישראל): {sent_israel}",
        f"🕒 T0 אות מקורי (ישראל): {signal_israel}",
    ]
    if alert_event_id:
        lines.append(f"🧾 Alert ID: {alert_event_id}")
    lines.extend(
        [
            "⚠️ MANUAL DECISION ONLY — NO AUTOMATIC TRADE",
            f"Promotion: {promotion} ✅",
            f"Token: {symbol}",
            f"Chain: {chain}",
            f"Contract: {token}",
            f"Pair: {pair}",
            f"DEX: {dex}",
            "Pair identity: EXACT LOCK ✅",
            f"Pair checked: {pair_checked}",
            f"Market age: ≥{market_age}d ✅",
            f"Age proof: {age_source}",
            f"Current pair age: {pair_age_text}",
            f"Research/Revival score: {score:.2f}/100",
            f"Price: {_fmt_money(price)}",
            f"Liquidity: {_fmt_money(liquidity)} ✅ min $50K",
            f"Volume 1H: {_fmt_money(volume)}",
            f"Buys/Sells 1H: {buys}/{sells}",
            f"Pump/Dump Risk: {risk}",
            "Holder/Cluster evidence: COMPLETE PASS",
            "Actionable research alert: YES ✅",
        ]
    )
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


def _send(bot_token: str, chat_id: str, text: str, max_attempts: int = 3) -> tuple[int | None, int]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read().decode("utf-8", errors="replace")
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Telegram HTTP {response.status}")
                payload = json.loads(raw) if raw else {}
                if payload.get("ok") is not True:
                    raise RuntimeError("Telegram API returned ok=false")
                result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                message_id = result.get("message_id")
                return int(message_id) if message_id is not None else None, attempt
        except urllib.error.HTTPError as exc:
            last_error = exc
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= max_attempts:
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
    real_index = {
        _pair_key(row): row
        for row in real_rows
        if isinstance(row, dict) and _is_actionable_real_alert(row)
    }

    state = _load(state_path, {})
    if not isinstance(state, dict):
        state = {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(bot_token and chat_id)
    now = datetime.now(timezone.utc).isoformat()
    now_israel = _fmt_israel_time(now)
    delivered = []
    eligible = []
    errors = []
    active_now: set[str] = set()

    for row in candidates:
        if not isinstance(row, dict):
            continue
        tier = _tier(row)
        if not tier:
            continue
        key = _pair_key(row)
        real = real_index.get(key)
        if not _is_actionable_real_alert(real):
            continue

        active_now.add(key)
        display = _merge_display_context(row, real)
        fingerprint = f"REAL_ALERT:{tier}:{_norm_addr(row.get('locked_pair_address'))}"
        eligible.append(
            {
                "key": key,
                "tier": tier,
                "symbol": display.get("symbol"),
                "pair_address": row.get("pair_address"),
                "market_age_min_days": row.get("market_age_min_days"),
                "promotion": "EVIDENCE_READY_TO_ACTIONABLE" if display.get("evidence_ready") else "VERIFIED_TO_ACTIONABLE",
                "dex_url": display.get("dex_url") or display.get("url"),
            }
        )

        previous = sent.get(key) if isinstance(sent.get(key), dict) else {}
        if previous.get("actionable") is True:
            continue
        if not configured:
            continue

        event_id = _alert_event_id(key, now)
        try:
            telegram_message_id, attempts = _send(
                bot_token,
                chat_id,
                _message(display, tier, sent_at=now, alert_event_id=event_id),
            )
            sent[key] = {
                "fingerprint": fingerprint,
                "alert_event_id": event_id,
                "telegram_message_id": telegram_message_id,
                "delivery_attempts": attempts,
                "tier": tier,
                "symbol": display.get("symbol"),
                "pair_address": row.get("pair_address"),
                "actionable": True,
                "sent_at": now,
                "sent_at_israel": now_israel,
                "dex_url": display.get("dex_url") or display.get("url"),
            }
            delivered.append(
                {
                    "key": key,
                    "alert_event_id": event_id,
                    "telegram_message_id": telegram_message_id,
                    "delivery_attempts": attempts,
                    "tier": tier,
                    "symbol": display.get("symbol"),
                    "pair_address": row.get("pair_address"),
                    "sent_at": now,
                    "sent_at_israel": now_israel,
                    "dex_url": display.get("dex_url") or display.get("url"),
                }
            )
        except Exception as exc:
            errors.append({"key": key, "alert_event_id": event_id, "error": f"{type(exc).__name__}: {exc}"[:300]})

    # Re-arm a token after it leaves the actionable state, so a later fresh
    # promotion back into ACTIONABLE creates a new Telegram alert.
    for key, info in list(sent.items()):
        if not isinstance(info, dict):
            continue
        if info.get("actionable") is True and key not in active_now:
            info["actionable"] = False
            info["cleared_at"] = now
            sent[key] = info

    if len(sent) > 5000:
        sent = dict(
            sorted(
                sent.items(),
                key=lambda kv: kv[1].get("sent_at", "") if isinstance(kv[1], dict) else "",
                reverse=True,
            )[:5000]
        )

    report = {
        "version": 9,
        "updated_at": now,
        "updated_at_israel": now_israel,
        "configured": configured,
        "candidate_count": len(candidates),
        "real_alert_count": len(real_rows),
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "eligible": eligible,
        "delivered": delivered,
        "errors": errors,
        "policy": {
            "source": source_name,
            "real_alert_source": real_source_name,
            "transition_rule": "send once when an exact-pair candidate ENTERS actionable REAL_ALERT; re-arm after it leaves actionable state",
            "requires": [
                "matching real-alerts.json row with status=REAL_ALERT and actionable_research_alert=true",
                "market_age_verified=true",
                "market_age_min_days>=180",
                "qualification=QUALIFIED or REVIVAL_QUALIFIED",
                "live_survival_gate=ACTIVE",
                "pump_dump_blocked=false",
                "pair_identity_locked=true",
                "pair_address=locked_pair_address",
                "holder_cluster_production_status=PASS",
                "holder_cluster_verification_complete=true",
                "liquidity>=50000",
                "volume_h1>=15000",
                "activity_h1>=50",
                "risk not HIGH/CRITICAL",
            ],
            "high_conviction": "score>=90, liquidity>=50000, volume_h1>=30000, risk=LOW",
            "manual_execution": "Telegram is a review alert only; no automatic trade is executed",
            "dedupe": "one alert per transition into actionable state for chain+token+exact_pair",
            "telegram_timestamp": "every delivered message includes explicit Asia/Jerusalem send date/time plus original signal T0",
            "delivery_retries": "up to 3 attempts on transient Telegram/network failures",
            "audit_id": "each delivery has a stable alert_event_id derived from exact-pair key plus send timestamp",
        },
    }
    _write(state_path, {"updated_at": now, "updated_at_israel": now_israel, "sent": sent})
    _write(out / "telegram-alert-report.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
