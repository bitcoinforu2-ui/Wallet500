from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "production_intelligence_gate.py"
SPEC = importlib.util.spec_from_file_location("production_intelligence_gate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
apply_gate = MODULE.apply_gate


NOW = datetime(2026, 9, 16, 21, 30, tzinfo=timezone.utc)


def policy():
    return {
        "version": 3,
        "production_gate": {
            "enabled": True,
            "fail_closed": True,
            "minimum_score": 55,
            "minimum_independent_positive_families": 4,
            "minimum_evidence_count": 4,
            "maximum_snapshot_age_seconds": 2700,
            "maximum_token_age_seconds": 2700,
            "allowed_labels": ["CONFLUENCE", "STRONG_CONFLUENCE", "EXCEPTIONAL_CONFLUENCE"],
            "hard_risks_must_be_empty": True,
            "missing_or_stale_status": "WAITING_FOR_INTELLIGENCE",
        },
    }


def alert(contract="0xabc", pair="0xdef"):
    return {
        "status": "REAL_ALERT",
        "radar_tier": "REAL_ALERT",
        "actionable_research_alert": True,
        "automatic_buy": False,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "symbol": "LSK",
        "chain": "ethereum",
        "token_address": contract,
        "pair_address": pair,
        "source_lanes": ["CEX_SPOT_BREADTH"],
        "evidence_positive_lanes": [],
        "evidence_verified_lanes": [],
        "blockers": [],
    }


def intelligence(*, contract="0xabc", pair="0xdef", generated_at=None, updated_at=None, families=4, score=68, label="CONFLUENCE", hard_risks=None):
    generated_at = generated_at or NOW.isoformat()
    updated_at = updated_at or NOW.isoformat()
    family_names = ["market_microstructure", "wallet_flow", "attention_social", "catalyst_news"][:families]
    family_scores = {
        "market_microstructure": 12.0,
        "wallet_flow": 18.0,
        "attention_social": 10.0,
        "catalyst_news": 9.0,
    }
    return {
        "version": 2,
        "generated_at": generated_at,
        "tokens": [
            {
                "symbol": "LSK",
                "network": "eth",
                "contract": contract,
                "pair": pair,
                "score": score,
                "label": label,
                "independent_positive_families": families,
                "positive_family_names": family_names,
                "family_scores": family_scores,
                "hard_risks": hard_risks or [],
                "evidence_count": 6,
                "updated_at": updated_at,
            }
        ],
    }


def payload(row=None):
    return {"alerts": [row or alert()], "pre_wave_alerts": []}


def test_exact_identity_full_intelligence_passes_and_is_exposed_to_telegram():
    gated, report = apply_gate(payload(), intelligence(), policy(), NOW)
    row = gated["alerts"][0]
    assert row["actionable_research_alert"] is True
    assert row["intelligence_gate"]["passed"] is True
    assert row["intelligence_used_in_actionable_decision"] is True
    assert row["intelligence_delivery_status"] == "FULL_INTELLIGENCE_ACTIONABLE"
    assert "INTELLIGENCE_FUSION" in row["source_lanes"]
    assert any("INTELLIGENCE_GATE PASS 68.0/100 CONFLUENCE" in value for value in row["evidence_verified_lanes"])
    assert report["actionable_before"] == 1
    assert report["actionable_after"] == 1


def test_same_ticker_wrong_contract_is_blocked_not_cross_wired():
    gated, report = apply_gate(payload(), intelligence(contract="0x999"), policy(), NOW)
    row = gated["alerts"][0]
    assert row["actionable_research_alert"] is False
    assert row["intelligence_gate"]["passed"] is False
    assert "EXACT_INTELLIGENCE_IDENTITY_MISSING" in row["intelligence_gate"]["reasons"]
    assert report["actionable_after"] == 0


def test_stale_snapshot_blocks_actionable_delivery():
    stale = (NOW - timedelta(hours=2)).isoformat()
    gated, _ = apply_gate(payload(), intelligence(generated_at=stale, updated_at=stale), policy(), NOW)
    row = gated["alerts"][0]
    assert row["actionable_research_alert"] is False
    assert "INTELLIGENCE_SNAPSHOT_MISSING_OR_STALE" in row["intelligence_gate"]["reasons"]
    assert "TOKEN_INTELLIGENCE_MISSING_OR_STALE" in row["intelligence_gate"]["reasons"]


def test_hard_risk_blocks_even_with_high_score():
    gated, _ = apply_gate(payload(), intelligence(score=90, label="EXCEPTIONAL_CONFLUENCE", hard_risks=["critical_liquidity_drain"]), policy(), NOW)
    row = gated["alerts"][0]
    assert row["actionable_research_alert"] is False
    assert "HARD_RISK_PRESENT" in row["intelligence_gate"]["reasons"]


def test_fewer_than_four_independent_families_blocks():
    gated, _ = apply_gate(payload(), intelligence(families=3), policy(), NOW)
    row = gated["alerts"][0]
    assert row["actionable_research_alert"] is False
    assert "INSUFFICIENT_INDEPENDENT_FAMILIES" in row["intelligence_gate"]["reasons"]


def test_blocked_rows_are_preserved_for_learning_and_audit():
    original = payload()
    gated, report = apply_gate(original, {}, policy(), NOW)
    assert len(gated["alerts"]) == 1
    row = gated["alerts"][0]
    assert row["pre_intelligence_actionable_research_alert"] is True
    assert row["intelligence_delivery_status"] == "WAITING_FOR_INTELLIGENCE"
    assert report["truth_contract"]["rows_are_preserved_not_deleted"] is True
