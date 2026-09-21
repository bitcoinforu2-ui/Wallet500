from __future__ import annotations

import json
from pathlib import Path

import pytest

from wallet500.telegram_delivery_ledger import SharedTelegramDeliveryLedger


def _clock():
    values = iter([
        "2026-09-21T06:00:00+00:00",
        "2026-09-21T06:00:01+00:00",
        "2026-09-21T06:00:02+00:00",
        "2026-09-21T06:00:03+00:00",
        "2026-09-21T06:00:04+00:00",
        "2026-09-21T06:00:05+00:00",
    ])
    return lambda: next(values)


def test_shared_ledger_reserves_before_send_and_dedupes(tmp_path: Path):
    path = tmp_path / "ledger.json"
    snapshots = []
    send_calls = []

    def persist(p: Path, reason: str):
        snapshots.append((reason, json.loads(p.read_text(encoding="utf-8"))))

    ledger = SharedTelegramDeliveryLedger(path, persist, clock=_clock())
    result = ledger.deliver(
        alert_type="UNIFIED_FINAL_BUY",
        stream_key="UNIFIED_FINAL_BUY:bsc:token:pair",
        source_token="episode-7",
        metadata={"symbol": "TEST"},
        build_text=lambda event_id: f"BUY\nAlert ID: {event_id}",
        send_once=lambda text: (send_calls.append(text) or (12345, 1)),
    )

    assert result["status"] == "DELIVERED"
    assert len(send_calls) == 1
    assert len(snapshots) == 2
    assert snapshots[0][0].startswith("reserve:")
    assert snapshots[1][0].startswith("delivered:")
    event_id = result["event_id"]
    assert snapshots[0][1]["events"][event_id]["status"] == "RESERVED"
    assert snapshots[1][1]["events"][event_id]["status"] == "DELIVERED"

    duplicate = ledger.deliver(
        alert_type="UNIFIED_FINAL_BUY",
        stream_key="UNIFIED_FINAL_BUY:bsc:token:pair",
        source_token="episode-7",
        metadata={},
        build_text=lambda event_id: event_id,
        send_once=lambda text: (_ for _ in ()).throw(AssertionError("must not resend")),
    )
    assert duplicate["status"] == "ALREADY_DELIVERED"
    assert len(send_calls) == 1
    assert len(snapshots) == 2


def test_send_failure_becomes_delivery_unknown_and_never_retries(tmp_path: Path):
    path = tmp_path / "ledger.json"
    snapshots = []

    def persist(p: Path, reason: str):
        snapshots.append((reason, json.loads(p.read_text(encoding="utf-8"))))

    ledger = SharedTelegramDeliveryLedger(path, persist, clock=_clock())
    result = ledger.deliver(
        alert_type="REAL_ALERT",
        stream_key="bsc:token:pair",
        source_token="first-alert",
        build_text=lambda event_id: event_id,
        send_once=lambda text: (_ for _ in ()).throw(TimeoutError("ambiguous timeout")),
    )
    assert result["status"] == "DELIVERY_UNKNOWN"
    assert snapshots[0][1]["events"][result["event_id"]]["status"] == "RESERVED"
    assert snapshots[1][1]["events"][result["event_id"]]["status"] == "DELIVERY_UNKNOWN"

    second = ledger.deliver(
        alert_type="REAL_ALERT",
        stream_key="bsc:token:pair",
        source_token="first-alert",
        build_text=lambda event_id: event_id,
        send_once=lambda text: (_ for _ in ()).throw(AssertionError("must fail closed")),
    )
    assert second["status"] == "FAIL_CLOSED_EXISTING_RESERVATION"
    assert second["existing_status"] == "DELIVERY_UNKNOWN"


def test_crash_after_telegram_success_leaves_durable_reservation_fail_closed(tmp_path: Path):
    path = tmp_path / "ledger.json"
    durable = {}

    def persist(p: Path, reason: str):
        nonlocal durable
        doc = json.loads(p.read_text(encoding="utf-8"))
        if reason.startswith("delivered:"):
            raise RuntimeError("simulated GitHub CAS outage after Telegram accepted")
        durable = doc

    ledger = SharedTelegramDeliveryLedger(path, persist, clock=_clock())
    with pytest.raises(RuntimeError, match="simulated GitHub CAS outage"):
        ledger.deliver(
            alert_type="REAL_ALERT",
            stream_key="ethereum:token:pair",
            source_token="episode-a",
            build_text=lambda event_id: event_id,
            send_once=lambda text: (999, 1),
        )

    event_id = next(iter(durable["events"]))
    assert durable["events"][event_id]["status"] == "RESERVED"

    # Simulate the next runner checking out the durable main state. It must not
    # resend because Telegram may already have accepted the first attempt.
    path.write_text(json.dumps(durable), encoding="utf-8")
    next_ledger = SharedTelegramDeliveryLedger(path, lambda p, r: None, clock=_clock())
    result = next_ledger.deliver(
        alert_type="REAL_ALERT",
        stream_key="ethereum:token:pair",
        source_token="episode-a",
        build_text=lambda eid: eid,
        send_once=lambda text: (_ for _ in ()).throw(AssertionError("duplicate send")),
    )
    assert result["status"] == "FAIL_CLOSED_EXISTING_RESERVATION"
    assert result["existing_status"] == "RESERVED"
