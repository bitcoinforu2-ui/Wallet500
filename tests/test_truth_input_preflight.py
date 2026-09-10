from pathlib import Path

import pytest

from wallet500.truth_input_preflight import check


def test_preflight_rejects_missing_or_corrupt_inputs(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    good.write_text('{"ok":true}', encoding="utf-8")
    bad.write_text('{bad', encoding="utf-8")
    with pytest.raises(RuntimeError):
        check((str(good), str(bad), str(tmp_path / "missing.json")))
    health = (tmp_path / "data" / "truth-input-health.json")
    assert health.exists()


def test_preflight_passes_valid_json(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text('{}', encoding="utf-8")
    b.write_text('[]', encoding="utf-8")
    out = check((str(a), str(b)))
    assert out["status"] == "PASS"
