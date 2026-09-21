from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


LEDGER_VERSION = 1
TERMINAL_DELIVERED = "DELIVERED"
FAIL_CLOSED_STATES = {"RESERVED", "DELIVERY_UNKNOWN"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_event_id(alert_type: str, stream_key: str, source_token: str) -> str:
    material = "|".join([
        str(alert_type or "").strip().upper(),
        str(stream_key or "").strip(),
        str(source_token or "").strip(),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


class SharedTelegramDeliveryLedger:
    """Durable at-most-once Telegram delivery ledger.

    There is no distributed transaction spanning GitHub and Telegram. The safe
    contract is therefore fail-closed:
      1. durably reserve an event before any network delivery;
      2. send exactly once (no transport retry in this layer);
      3. durably persist the Telegram receipt immediately after success.

    A crash after reservation leaves RESERVED on main. A later run refuses to
    resend that event automatically because Telegram may already have accepted
    it even if the receipt was lost.
    """

    def __init__(
        self,
        path: Path,
        persist_func: Callable[[Path, str], None],
        *,
        clock: Callable[[], str] = now_iso,
    ) -> None:
        self.path = Path(path)
        self.persist_func = persist_func
        self.clock = clock
        self.doc = self._load()

    def _load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("version", LEDGER_VERSION)
        payload.setdefault("events", {})
        payload.setdefault("streams", {})
        if not isinstance(payload.get("events"), dict):
            payload["events"] = {}
        if not isinstance(payload.get("streams"), dict):
            payload["streams"] = {}
        return payload

    def _write_and_persist(self, reason: str) -> None:
        self.doc["version"] = LEDGER_VERSION
        self.doc["updated_at"] = self.clock()
        self.path.write_text(
            json.dumps(self.doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.persist_func(self.path, reason)

    def deliver(
        self,
        *,
        alert_type: str,
        stream_key: str,
        source_token: str,
        build_text: Callable[[str], str],
        send_once: Callable[[str], tuple[int | None, int]],
        metadata: dict | None = None,
    ) -> dict:
        event_id = stable_event_id(alert_type, stream_key, source_token)
        events = self.doc["events"]
        existing = events.get(event_id) if isinstance(events.get(event_id), dict) else None

        if existing:
            status = str(existing.get("status") or "").upper()
            if status == TERMINAL_DELIVERED:
                return {
                    "status": "ALREADY_DELIVERED",
                    "event_id": event_id,
                    "telegram_message_id": existing.get("telegram_message_id"),
                    "delivery_attempts": existing.get("delivery_attempts"),
                }
            # Any non-terminal pre-existing event is ambiguous. Never resend.
            return {
                "status": "FAIL_CLOSED_EXISTING_RESERVATION",
                "event_id": event_id,
                "existing_status": status or "UNKNOWN",
            }

        reserved_at = self.clock()
        record = {
            "event_id": event_id,
            "alert_type": str(alert_type or "").upper(),
            "stream_key": stream_key,
            "source_token": source_token,
            "status": "RESERVED",
            "reserved_at": reserved_at,
            "metadata": dict(metadata or {}),
        }
        events[event_id] = record
        self.doc["streams"][stream_key] = {
            "latest_event_id": event_id,
            "latest_status": "RESERVED",
            "updated_at": reserved_at,
        }

        # Reservation must be durable on main before Telegram is touched.
        self._write_and_persist(f"reserve:{event_id}")

        try:
            text = build_text(event_id)
            telegram_message_id, attempts = send_once(text)
        except Exception as exc:
            record["status"] = "DELIVERY_UNKNOWN"
            record["delivery_error"] = f"{type(exc).__name__}: {exc}"[:400]
            record["delivery_failed_at"] = self.clock()
            self.doc["streams"][stream_key].update({
                "latest_status": "DELIVERY_UNKNOWN",
                "updated_at": record["delivery_failed_at"],
            })
            # Best effort to persist UNKNOWN. If this write itself fails, the
            # already-durable RESERVED record still prevents an automatic resend.
            try:
                self._write_and_persist(f"unknown:{event_id}")
            finally:
                return {
                    "status": "DELIVERY_UNKNOWN",
                    "event_id": event_id,
                    "error": record["delivery_error"],
                }

        delivered_at = self.clock()
        record.update({
            "status": TERMINAL_DELIVERED,
            "delivered_at": delivered_at,
            "telegram_message_id": telegram_message_id,
            "delivery_attempts": attempts,
        })
        self.doc["streams"][stream_key].update({
            "latest_status": TERMINAL_DELIVERED,
            "updated_at": delivered_at,
        })

        # Persist the dedupe/receipt immediately after successful delivery.
        # If this persistence fails, remote main remains RESERVED and later runs
        # fail closed instead of risking a duplicate Telegram message.
        self._write_and_persist(f"delivered:{event_id}")
        return {
            "status": TERMINAL_DELIVERED,
            "event_id": event_id,
            "telegram_message_id": telegram_message_id,
            "delivery_attempts": attempts,
        }
