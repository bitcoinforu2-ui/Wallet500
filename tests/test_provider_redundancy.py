import json
from pathlib import Path

from wallet500.provider_redundancy import run


def put(root: Path, payload: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root/"waking-confirmation-latest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_failed_provider_is_never_redundancy(tmp_path):
    put(tmp_path, {"targets":[{
        "channels":{"social":{"verified":True,"source":"OFFICIAL_TELEGRAM"},"news":{"verified":False,"source":"FAILED_X"}},
        "provider_status":[{"provider":"x","status":"HTTP_402"},{"provider":"telegram_official","status":"OK"}],
    }]})
    out=run(tmp_path)
    assert out["production_effect"] is False
    assert out["failed_provider_counts_as_positive_evidence"] is False
    assert out["families"]["social"]["state"] == "SINGLE_SOURCE"
    assert out["families"]["news"]["state"] == "NO_VERIFIED_SOURCE"
    assert "x" in out["degraded_providers"]
