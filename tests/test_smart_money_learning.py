import json
from pathlib import Path

from wallet500.engine_learning_review import run


def put(root: Path, name: str, payload: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root/name).write_text(json.dumps(payload), encoding="utf-8")


def test_pending_history_is_observational_only(tmp_path):
    put(tmp_path, "prospective-benchmark-ledger.json", {"version":"WALLET500_PROSPECTIVE_BENCHMARK_V1","no_hindsight":True,"production_effect":False,"records":{}})
    put(tmp_path, "prospective-benchmark-latest.json", {"counts":{}})
    put(tmp_path, "waking-confirmation-latest.json", {"targets":[]})
    put(tmp_path, "revival-smart-money-registry.json", {"wallets":[
        {"wallet":"A","status":"PENDING_HISTORY","completed_exposures":8,"cross_token_count":3},
        {"wallet":"B","status":"PENDING_HISTORY","completed_exposures":2,"cross_token_count":1},
        {"wallet":"C","status":"QUALIFIED","completed_exposures":9,"cross_token_count":4},
    ]})
    out=run(tmp_path,"2026-09-11T12:00:00+00:00")
    sm=out["smart_money_quality"]
    assert sm["pending_history"] == 2
    assert sm["qualification_queue"][0]["wallet"] == "A"
    assert sm["qualification_queue"][0]["promotion_forbidden"] is True
    assert sm["qualification_queue_mode"] == "RESEARCH_ONLY_EXISTING_EVIDENCE_PRIORITY"
