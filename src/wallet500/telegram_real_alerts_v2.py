from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .telegram_alerts import (
    _alert_event_id,
    _fmt_israel_time,
    _fmt_money,
    _load,
    _pair_key,
    _send,
    _write,
)

MIN_MARKET_AGE_DAYS = 180
MIN_LIQUIDITY_USD = 50_000.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_real_alert(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("status") != "REAL_ALERT" or row.get("actionable_research_alert") is not True:
        return False
    if row.get("exact_identity_verified") is not True:
        return False
    if row.get("exact_pair_verified") is not True:
        return False
    if row.get("market_age_verified") is not True:
        return False
    try:
        if int(row.get("market_age_days") or 0) < MIN_MARKET_AGE_DAYS:
            return False
        liquidity = float(row.get("execution_pool_liquidity_usd") or row.get("liquidity_usd") or 0)
    except (TypeError, ValueError):
        return False
    if liquidity < MIN_LIQUIDITY_USD:
        return False
    if list(row.get("blockers") or []):
        return False
    return bool(row.get("chain") and row.get("token_address") and row.get("pair_address"))


def _tier(row: dict) -> str:
    try:
        score = float(row.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    return "HIGH_CONVICTION" if score >= 90 else "QUALIFIED"


def _message(row: dict, tier: str, sent_at: str, event_id: str) -> str:
    symbol = str(row.get("symbol") or "UNKNOWN")
    chain = str(row.get("chain") or "unknown").upper().replace("BSC", "BNB")
    token = str(row.get("token_address") or "unknown")
    pair = str(row.get("pair_address") or "unknown")
    dex = str(row.get("dex") or "unknown")
    dex_url = str(row.get("dex_url") or "")
    sent_israel = _fmt_israel_time(sent_at)
    t0_israel = _fmt_israel_time(row.get("first_alert_at"))
    try:
        age = int(row.get("market_age_days") or 0)
    except (TypeError, ValueError):
        age = 0
    try:
        score = float(row.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    liquidity = row.get("execution_pool_liquidity_usd") or row.get("liquidity_usd")
    price = row.get("price_usd")
    source_lanes = list(row.get("source_lanes") or [])
    positive = list(row.get("evidence_positive_lanes") or [])
    verified = list(row.get("evidence_verified_lanes") or [])
    envelope = str(row.get("evidence_envelope_status") or "n/a")

    title = "🔥 HIGH-CONVICTION REAL ALERT" if tier == "HIGH_CONVICTION" else "🚨 REAL ALERT"
    lines = [
        f"{title} — WALLET500",
        "🆕 NEW REAL ALERT",
        f"📅 תאריך ושעת שליחת ההתראה (ישראל): {sent_israel}",
        f"🕒 T0 אות מקורי (ישראל): {t0_israel}",
        f"🧾 Alert ID: {event_id}",
        "⚠️ MANUAL DECISION ONLY — NO AUTOMATIC TRADE",
        f"Token: {symbol}",
        f"Chain: {chain}",
        f"Contract: {token}",
        f"Pair: {pair}",
        f"DEX: {dex}",
        "Exact identity: VERIFIED ✅",
        "Exact pair: VERIFIED ✅",
        f"Market age: ≥{age}d ✅",
        f"Execution liquidity: {_fmt_money(liquidity)} ✅ min $50K",
        f"Price at alert snapshot: {_fmt_money(price)}",
        f"Research/Revival score: {score:.2f}/100",
        f"Evidence envelope: {envelope}",
        "Canonical REAL ALERT truth gates: PASS ✅",
    ]
    if source_lanes:
        lines.append(f"Decision lanes: {', '.join(map(str, source_lanes))}")
    if positive:
        lines.append(f"Positive evidence: {', '.join(map(str, positive))}")
    if verified:
        lines.append(f"Verified evidence: {', '.join(map(str, verified))}")
    lines.append("Verified Intelligence. The Pure Truth.")
    if dex_url:
        lines.append(f"🔗 OPEN DEX: {dex_url}")
    return "\n".join(lines)


def run() -> dict:
    out = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
    real_source_name = os.getenv("WALLET500_REAL_ALERT_INPUT", "real-alerts.json")
    state_path = out / "telegram-alert-state.json"
    report_path = out / "telegram-alert-report.json"
    payload = _load(out / real_source_name, {})
    rows = list(payload.get("alerts") or []) if isinstance(payload, dict) else []
    canonical = [row for row in rows if _canonical_real_alert(row)]

    state = _load(state_path, {})
    if not isinstance(state, dict):
        state = {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        existing = _load(report_path, {})
        print(json.dumps({
            "status": "SKIPPED_UNCONFIGURED_NO_STATE_WRITE",
            "canonical_real_alerts": len(canonical),
        }, indent=2))
        return existing if isinstance(existing, dict) else {}

    now = _now()
    now_israel = _fmt_israel_time(now)
    active_now: set[str] = set()
    eligible = []
    delivered = []
    errors = []

    for row in canonical:
        key = _pair_key(row)
        active_now.add(key)
        tier = _tier(row)
        eligible.append({
            "key": key,
            "symbol": row.get("symbol"),
            "tier": tier,
            "pair_address": row.get("pair_address"),
            "dex_url": row.get("dex_url"),
            "first_alert_at": row.get("first_alert_at"),
            "source_lanes": row.get("source_lanes") or [],
        })
        previous = sent.get(key) if isinstance(sent.get(key), dict) else {}
        if previous.get("actionable") is True:
            continue

        event_id = _alert_event_id(key, now)
        try:
            telegram_message_id, attempts = _send(
                bot_token,
                chat_id,
                _message(row, tier, now, event_id),
            )
            info = {
                "fingerprint": f"CANONICAL_REAL_ALERT:{tier}",
                "alert_event_id": event_id,
                "telegram_message_id": telegram_message_id,
                "delivery_attempts": attempts,
                "tier": tier,
                "symbol": row.get("symbol"),
                "pair_address": row.get("pair_address"),
                "actionable": True,
                "sent_at": now,
                "sent_at_israel": now_israel,
                "dex_url": row.get("dex_url"),
                "source": "CANONICAL_REAL_ALERT_FEED",
            }
            sent[key] = info
            delivered.append({"key": key, **info})
        except Exception as exc:
            errors.append({
                "key": key,
                "symbol": row.get("symbol"),
                "alert_event_id": event_id,
                "error": f"{type(exc).__name__}: {exc}"[:300],
            })

    # When a canonical REAL ALERT leaves the active feed, re-arm it. A later
    # re-entry is a genuinely new transition and may be delivered again.
    for key, info in list(sent.items()):
        if not isinstance(info, dict):
            continue
        if info.get("actionable") is True and key not in active_now:
            info["actionable"] = False
            info["cleared_at"] = now
            sent[key] = info

    if len(sent) > 5000:
        sent = dict(sorted(
            sent.items(),
            key=lambda kv: str((kv[1] or {}).get("sent_at") or (kv[1] or {}).get("baseline_at") or ""),
            reverse=True,
        )[:5000])

    report = {
        "version": 11,
        "updated_at": now,
        "updated_at_israel": now_israel,
        "configured": True,
        "source": "CANONICAL_REAL_ALERT_FEED",
        "real_alert_count": len(rows),
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "eligible": eligible,
        "delivered": delivered,
        "errors": errors,
        "policy": {
            "transition_rule": "send once when an exact-pair row enters canonical actionable REAL_ALERT; re-arm after it leaves",
            "canonical_source": real_source_name,
            "no_historical_backfill": "pre-existing alerts are seeded in telegram-alert-state.json as baseline actionable rows",
            "requires": [
                "status=REAL_ALERT",
                "actionable_research_alert=true",
                "exact_identity_verified=true",
                "exact_pair_verified=true",
                "market_age_verified=true",
                "market_age_days>=180",
                "execution_pool_liquidity_usd>=50000",
                "blockers=[]",
            ],
            "manual_execution": "review alert only; no automatic trade",
            "delivery_retries": "up to 3 attempts on transient Telegram/network failures",
            "timestamp": "explicit Asia/Jerusalem send time plus original T0",
        },
    }
    _write(state_path, {"updated_at": now, "updated_at_israel": now_israel, "sent": sent})
    _write(report_path, report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
