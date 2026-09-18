from __future__ import annotations

import subprocess
from pathlib import Path

import scripts.serialized_publish_staged as staged


WORKFLOWS = Path(".github/workflows")


def test_no_workflow_directly_pushes_head_to_main():
    offenders = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "git push origin HEAD:main" in text or "git push -q origin HEAD:main" in text:
            offenders.append(path.name)
    assert offenders == [], f"direct main publishers bypass serialized/atomic CAS: {offenders}"


def test_critical_publishers_use_serialized_lane():
    required = {
        "unified-watch-engine.yml",
        "cyberleek-wallet-flow.yml",
        "wallet-accumulation-prospective.yml",
        "revival-wallet-coverage-probe.yml",
        "live-scan.yml",
        "paper-truth.yml",
    }
    for name in required:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert (
            "serialized_publish.py" in text
            or "serialized_publish_staged.py" in text
        ), name


def test_staged_path_reader_filters_transient_artifacts(monkeypatch):
    payload = (
        b"data/state.json\0"
        b"src/wallet500.egg-info/PKG-INFO\0"
        b"tests/__pycache__/x.pyc\0"
        b"data/state.json\0"
    )

    class Result:
        returncode = 0
        stdout = payload
        stderr = b""

    monkeypatch.setattr(staged, "git", lambda *args: Result())
    assert staged.staged_paths() == ["data/state.json"]


def test_staged_path_reader_fails_closed_on_git_error(monkeypatch):
    class Result:
        returncode = 1
        stdout = b""
        stderr = b"boom"

    monkeypatch.setattr(staged, "git", lambda *args: Result())
    try:
        staged.staged_paths()
    except RuntimeError as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("expected staged path discovery to fail closed")
