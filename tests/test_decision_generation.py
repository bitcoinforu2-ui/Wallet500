import json
from datetime import datetime, timedelta, timezone

import pytest

from wallet500 import decision_generation as generation

NOW = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    for name in generation.CANONICAL_FILES:
        payload = [] if name.endswith("active-qualified-candidates.json") else {"generated_at": NOW.isoformat()}
        (tmp_path / name).write_text(json.dumps(payload))
    return tmp_path


def test_current_empty_candidate_snapshot_is_ready(snapshot):
    payload = generation.build(now=NOW)
    assert payload["status"] == "COHERENT_READY"
    assert all(row["status"] == "CURRENT" for row in payload["source_freshness"].values())


@pytest.mark.parametrize("stamp,reason", [
    ((NOW - timedelta(days=4)).isoformat(), "SOURCE_STALE"),
    ((NOW + timedelta(minutes=6)).isoformat(), "SOURCE_TIMESTAMP_IN_FUTURE"),
    (None, "SOURCE_TIMESTAMP_INVALID"),
    ("not-a-date", "SOURCE_TIMESTAMP_INVALID"),
    ("2026-10-03T15:00:00", "SOURCE_TIMESTAMP_INVALID"),
])
def test_fresh_manifest_cannot_relabel_bad_revival_timestamp(snapshot, stamp, reason):
    name = "data/revival-1000-latest.json"
    (snapshot / name).write_text(json.dumps({"generated_at": stamp}))
    with pytest.raises(RuntimeError, match="DECISION_GENERATION_INCOMPLETE_FAIL_CLOSED"):
        generation.build(now=NOW)
    payload = json.loads((snapshot / generation.OUT).read_text())
    assert payload["status"] == "INCOMPLETE_FAIL_CLOSED"
    assert payload["created_at"] == NOW.isoformat()
    assert payload["unhealthy_sources"][0]["path"] == name
    assert payload["unhealthy_sources"][0]["state"] == reason


def test_old_advisory_data_does_not_block_current_canonical_generation(snapshot):
    for name in generation.ADVISORY_FILES:
        (snapshot / name).write_text(json.dumps({"generated_at": "2020-01-01T00:00:00Z"}))
    assert generation.build(now=NOW)["status"] == "COHERENT_READY"


@pytest.mark.parametrize("payload", [None, [], "wrong"])
def test_timestamped_source_must_be_an_object(snapshot, payload):
    (snapshot / "data/real-alerts.json").write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match="DECISION_GENERATION_INCOMPLETE_FAIL_CLOSED"):
        generation.build(now=NOW)
