"""Immediate Telegram alert for official Moonshot future-listing announcements.

This is an intelligence-only fast lane. It reuses the canonical Moonshot collector,
requires an exact Solana contract/mint from the official Moonshot source, and sends
Telegram immediately after source detection without waiting for Wallet500 REAL_ALERT.

It deliberately writes to the same alerted state used by the legacy future-listing
watcher so a later canonical REAL_ALERT does not duplicate the Moonshot announcement
message. Trading/production gates remain unchanged and are never bypassed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import moonshot_future_listing_watch as fw

MODE = "MOONSHOT_INSTANT_CONTRACT_TELEGRAM_V1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _message(event: dict[str, Any]) -> str:
    token = str(event.get("token") or "").strip()
    symbol = str(event.get("symbol") or "?").strip() or "?"
    lines = [
        "🚨🔥 MOONSHOT OFFICIAL ANNOUNCEMENT",
        f"{symbol} | SOLANA | catalyst {fw.PRIORITY_SCORE}/100",
        "📣 Official Moonshot future-listing announcement detected",
        "📋 CONTRACT / CA:",
        token,
        "⚡ EARLY INTELLIGENCE — sent before Wallet500 buy/REAL_ALERT gates",
        "⚠️ NOT A BUY SIGNAL — MANUAL DECISION ONLY",
    ]
    source_url = str(event.get("source_url") or "").strip()
    if source_url:
        lines.append(f"🔗 Moonshot source: {source_url}")
    published_at = str(event.get("published_at") or event.get("first_seen_at") or "").strip()
    if published_at:
        lines.append(f"🕒 Published: {published_at}")
    return "\n".join(lines)


def _eligible(event: object) -> bool:
    if not isinstance(event, dict):
        return False
    return bool(
        str(event.get("event_type") or "") == "MOONSHOT_FUTURE_LISTING"
        and str(event.get("source_owner") or "").lower() == "moonshot"
        and str(event.get("chain") or "").lower() == "solana"
        and str(event.get("token") or "").strip()
        and str(event.get("source_url") or "").strip()
    )


def run(reference: datetime | None = None) -> dict[str, Any]:
    reference = reference or _now()
    latest = fw._load(fw.LATEST_PATH, {})
    events = latest.get("events") if isinstance(latest, dict) and isinstance(latest.get("events"), list) else []

    state = fw._load(fw.STATE_PATH, {"version": 1, "alerted": {}})
    if not isinstance(state, dict):
        state = {"version": 1, "alerted": {}}
    alerted = state.get("alerted") if isinstance(state.get("alerted"), dict) else {}

    attempts: list[dict[str, Any]] = []
    for event in events:
        if not _eligible(event):
            continue
        key = str(event.get("event_id") or fw._event_key(str(event.get("token"))))
        if not key or key in alerted:
            continue

        ok, status = fw._telegram_send(_message(event))
        attempts.append({
            "event_id": key,
            "token": event.get("token"),
            "ok": ok,
            "status": status,
            "wallet500_real_alert_pass": bool((event.get("wallet500_gate") or {}).get("pass")),
        })
        if ok:
            alerted[key] = {
                "sent_at": fw._iso(reference),
                "token": str(event.get("token")),
                "symbol": event.get("symbol"),
                "source_url": event.get("source_url"),
                "alert_type": "MOONSHOT_OFFICIAL_ANNOUNCEMENT_EXACT_CONTRACT",
                "wallet500_gate_required": False,
                "automatic_buy": False,
            }

    fw._write(fw.STATE_PATH, {
        "version": max(1, int(state.get("version") or 1)),
        "updated_at": fw._iso(reference),
        "alerted": alerted,
    })

    result = {
        "version": 1,
        "mode": MODE,
        "updated_at": fw._iso(reference),
        "events_seen": len(events),
        "eligible_exact_contract_events": sum(1 for event in events if _eligible(event)),
        "telegram_attempts": len(attempts),
        "telegram_delivered": sum(1 for row in attempts if row.get("ok")),
        "attempts": attempts,
        "policy": {
            "official_moonshot_exact_contract_required": True,
            "wallet500_real_alert_required_for_this_telegram": False,
            "automatic_buy": False,
            "production_trade_impact": "NONE",
            "dedupe_state": str(fw.STATE_PATH),
        },
    }
    print("MOONSHOT INSTANT ALERT", json.dumps(result, separators=(",", ":")))
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
