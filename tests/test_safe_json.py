from pathlib import Path

import pytest

from wallet500.safe_json import CORRUPT, MISSING, VALID, load_json_state, require_json


def test_missing_is_not_silent_empty(tmp_path: Path):
    r = load_json_state(tmp_path / "missing.json", default={})
    assert r.state == MISSING
    assert r.valid is False


def test_corrupt_is_not_silent_empty(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{bad", encoding="utf-8")
    r = load_json_state(p, default={})
    assert r.state == CORRUPT
    with pytest.raises(RuntimeError):
        require_json(p)


def test_valid_json_is_explicit(tmp_path: Path):
    p = tmp_path / "ok.json"
    p.write_text('{"x":1}', encoding="utf-8")
    r = load_json_state(p)
    assert r.state == VALID
    assert r.value == {"x": 1}
