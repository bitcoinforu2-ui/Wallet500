import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.recover_production_handoffs import LANES, recover, stale

NOW = datetime(2026, 10, 3, 19, 0, tzinfo=timezone.utc)


def files(tmp_path, age=0):
    for _, name, _ in LANES:
        (tmp_path / name).write_text(json.dumps({"updated_at": (NOW - timedelta(seconds=age)).isoformat()}))


def fake_api(active=False):
    calls = []
    def request(repo, endpoint, body=None):
        calls.append((endpoint, body))
        return {"workflow_runs": [{"status": "queued"}] if active else []} if body is None else {}
    return request, calls


def test_successful_scan_handoff_dispatches_exact_publisher_even_with_fresh_data(tmp_path):
    files(tmp_path)
    request, calls = fake_api()
    rows = recover("owner/repo", data_dir=tmp_path, source_run_id="123", now=NOW, request=request)
    assert rows[0]["status"] == "DISPATCHED"
    assert calls[-1][1] == {"ref": "main", "inputs": {"source_run_id": "123"}}
    assert rows[1]["status"] == "CURRENT"


def test_stale_consumers_recover_even_without_a_new_primary_scan(tmp_path):
    files(tmp_path, 7200)
    request, calls = fake_api()
    rows = recover("owner/repo", data_dir=tmp_path, now=NOW, request=request)
    assert [x["status"] for x in rows] == ["DISPATCHED", "DISPATCHED"]
    assert sum(body is not None for _, body in calls) == 2


def test_active_consumers_are_never_dispatched_twice(tmp_path):
    request, calls = fake_api(active=True)
    rows = recover("owner/repo", data_dir=tmp_path, now=NOW, request=request)
    assert all(x["status"] == "ACTIVE_NO_DUPLICATE" for x in rows)
    assert all(body is None for _, body in calls)


def test_failed_inventory_does_not_mean_idle(tmp_path):
    with pytest.raises(RuntimeError, match="HANDOFF_RUN_INVENTORY_INVALID"):
        recover("owner/repo", data_dir=tmp_path, now=NOW, request=lambda *args: {})


@pytest.mark.parametrize("stamp", [None, "bad", "2026-10-03T19:00:00", "2026-10-03T19:06:00Z"])
def test_invalid_or_future_consumer_timestamp_requires_recovery(tmp_path, stamp):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"updated_at": stamp}))
    assert stale(p, 1800, NOW)


def test_api_failure_propagates_without_dispatch(tmp_path):
    def fail(*args):
        raise RuntimeError("API unavailable")
    with pytest.raises(RuntimeError, match="API unavailable"):
        recover("owner/repo", data_dir=tmp_path, now=NOW, request=fail)


def test_workflow_handoff_requires_success_and_immutable_uploaded_artifact():
    root = Path(__file__).resolve().parents[1]
    scan = (root / ".github/workflows/live-scan.yml").read_text()
    publisher = (root / ".github/workflows/verified-publisher.yml").read_text()
    watchdog = (root / ".github/workflows/live-scan-watchdog.yml").read_text()
    assert scan.index("Upload verified snapshot handoff") < scan.index("--source-run-id")
    assert 'actions: write' in scan
    assert '.conclusion == "success"' in publisher
    assert 'HANDOFF_SOURCE_NOT_SUCCESSFUL' in publisher
    assert 'Snapshot source run mismatch' in publisher
    assert 'run: python3 scripts/recover_production_handoffs.py' in watchdog
