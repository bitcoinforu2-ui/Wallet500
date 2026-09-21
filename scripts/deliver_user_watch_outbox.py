from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from wallet500 import telegram_alerts as alerts
from wallet500.telegram_delivery_ledger import SharedTelegramDeliveryLedger

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/user-watch-final-buy-state.json"
LEDGER = ROOT / "data/telegram-delivery-ledger.json"
REPORT = ROOT / "data/unified-watch-telegram-delivery-report.json"


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def persist_ledger(path: Path, reason: str) -> None:
    if path.resolve() != LEDGER.resolve():
        raise RuntimeError("SHARED_LEDGER_PATH_DRIFT")
    env = os.environ.copy()
    if not env.get("GITHUB_TOKEN") or not env.get("GITHUB_REPOSITORY"):
        raise RuntimeError("SHARED_LEDGER_REQUIRES_GITHUB_CAS_ENV")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/atomic_publish.py"),
            "--github-api-cas",
            "--allow-newer-overwrite",
            "--message",
            f"telegram-ledger: {reason}",
            "data/telegram-delivery-ledger.json",
        ],
        cwd=str(ROOT),
        env=env,
        check=True,
    )


def main() -> int:
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        raise SystemExit("TELEGRAM_SECRETS_NOT_CONFIGURED")

    state = load(STATE, {})
    outbox = [x for x in (state.get("delivery_outbox") or []) if isinstance(x, dict)]
    ledger = SharedTelegramDeliveryLedger(LEDGER, persist_ledger)
    delivered = []
    deduped = []
    fail_closed = []

    for event in outbox:
        event_id = str(event.get("event_id") or "").strip()
        alert_type = str(event.get("alert_type") or "").strip().upper()
        stream_key = str(event.get("stream_key") or "").strip()
        source_token = str(event.get("source_token") or event_id).strip()
        message = str(event.get("message") or "").strip()

        valid = bool(
            event_id
            and alert_type in {"UNIFIED_PRE_BUY", "UNIFIED_FINAL_BUY"}
            and stream_key
            and source_token
            and message
            and event.get("manual_decision_only") is True
            and event.get("automatic_trade") is False
        )
        if not valid:
            fail_closed.append({
                "event_id": event_id or None,
                "status": "INVALID_OUTBOX_EVENT_FAIL_CLOSED",
            })
            continue

        result = ledger.deliver(
            alert_type=alert_type,
            stream_key=stream_key,
            source_token=source_token,
            metadata={
                "source": "UNIFIED_WATCH_DURABLE_OUTBOX",
                "outbox_event_id": event_id,
                "identity_key": event.get("identity_key"),
                "symbol": event.get("symbol"),
                "episode": event.get("episode"),
            },
            build_text=lambda stable_id, msg=message: (
                msg if "Alert ID:" in msg else msg + f"\nAlert ID: {stable_id}"
            ),
            send_once=lambda text: alerts._send(bot, chat, text, max_attempts=1),
        )
        status = str(result.get("status") or "").upper()
        if status == "DELIVERED":
            delivered.append(result)
        elif status == "ALREADY_DELIVERED":
            deduped.append(result)
        else:
            fail_closed.append(result)

    report = {
        "version": 1,
        "source_state_updated_at": state.get("updated_at"),
        "outbox_count": len(outbox),
        "delivered_count": len(delivered),
        "deduped_count": len(deduped),
        "fail_closed_count": len(fail_closed),
        "delivered": delivered,
        "deduped": deduped,
        "fail_closed": fail_closed,
        "truth_contract": {
            "single_shared_delivery_ledger": True,
            "durable_reservation_before_send": True,
            "delivery_receipt_persisted_immediately_after_send": True,
            "ambiguous_reservation_never_auto_retried": True,
            "transport_send_attempts_per_reserved_event": 1,
            "automatic_trade": False,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if fail_closed else 0


if __name__ == "__main__":
    raise SystemExit(main())
