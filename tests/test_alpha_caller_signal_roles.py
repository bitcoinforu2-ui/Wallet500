import json
from pathlib import Path

from scripts import alpha_caller_intake as intake


ROOT = Path(__file__).resolve().parents[1]


def test_botify_discovery_seed_is_score_neutral():
    semantics = intake.signal_role_semantics("candidate_discovery_no_score")
    assert semantics["status"] == "GATED_RESEARCH_CANDIDATE"
    assert semantics["event_kind"] == "alpha_source_candidate_seed"
    assert semantics["direction"] == 0
    assert semantics["strength_credit"] is False
    assert semantics["reason"] == "DISCOVERY_SEED_ONLY_NO_SCORE_CREDIT"


def test_normal_candidate_discovery_keeps_existing_positive_semantics():
    semantics = intake.signal_role_semantics("candidate_discovery")
    assert semantics["status"] == "GATED_RESEARCH_CANDIDATE"
    assert semantics["event_kind"] == "verified_alpha_caller_call"
    assert semantics["direction"] == 1
    assert semantics["strength_credit"] is True


def test_confirmation_only_keeps_existing_neutral_direction():
    semantics = intake.signal_role_semantics("confirmation_only")
    assert semantics["status"] == "GATED_CONFIRMATION_ONLY"
    assert semantics["direction"] == 0
    assert semantics["strength_credit"] is True


def test_botify_source_config_uses_score_neutral_role():
    doc = json.loads((ROOT / "data/alpha-caller-sources.json").read_text())
    source = next(x for x in doc["sources"] if x["id"] == "botify_botzo_launches")
    assert source["signal_role"] == "candidate_discovery_no_score"
    assert source["retain_unselected_backlog"] is True
    assert source["selection_order"] == "head"
