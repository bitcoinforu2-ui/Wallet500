import json
from pathlib import Path

import pytest

from wallet500 import cryptoyeezus_copy
from wallet500.cryptoyeezus_live_guard import main as live_guard_main


def test_cryptoyeezus_config_is_paper_only(monkeypatch):
    config = json.loads(Path("experiments/cryptoyeezus-copy-v1.json").read_text(encoding="utf-8"))
    assert config["allow_live_execution"] is False
    monkeypatch.setenv("COPY_LIVE_ENABLED", "true")
    assert cryptoyeezus_copy._live_enabled(config) is False


def test_live_guard_always_refuses_execution():
    with pytest.raises(SystemExit, match="paper/shadow-only"):
        live_guard_main()
