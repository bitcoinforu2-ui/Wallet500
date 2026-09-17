import json

import pytest

from wallet500.safe_json import atomic_write_json, load_json_fail_closed


def test_missing_json_state_uses_independent_default(tmp_path):
    default = {"sent": {}}
    loaded = load_json_fail_closed(tmp_path / "missing.json", default)
    assert loaded == default
    assert loaded is not default


def test_existing_corrupt_json_fails_closed_instead_of_rearming_state(tmp_path):
    path = tmp_path / "telegram-alert-state.json"
    path.write_text('{"sent": ', encoding="utf-8")
    with pytest.raises(RuntimeError, match="STATE_DATA_CORRUPT"):
        load_json_fail_closed(path, {})


def test_atomic_json_write_replaces_complete_document_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "telegram-alert-state.json"
    path.write_text(json.dumps({"sent": {"old": True}}), encoding="utf-8")
    payload = {"sent": {"new": {"actionable": True}}, "version": 1}
    atomic_write_json(path, payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []
