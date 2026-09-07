import json
from pathlib import Path

from wallet500.binance_event_intelligence import build_profile, enrich_event, format_binance_lines


def event(**extra):
    row = {
        "source_owner": "binance",
        "source_id": "BINANCE_TELEGRAM",
        "event_type": "SPOT_LISTING_EXPECTED",
        "symbol": "ABC",
        "chain": "bsc",
        "contract": "0x1111111111111111111111111111111111111111",
        "pair_address": "0x2222222222222222222222222222222222222222",
        "excerpt": "Binance will list ABC on spot",
    }
    row.update(extra)
    return row


def test_binance_alert_gets_fire_priority(tmp_path: Path):
    p = build_profile(event(), tmp_path)
    assert p["applicable"] is True
    assert p["priority"] == "FIRE_PRIORITY"
    assert p["production_effect"] is False
    assert p["automatic_buy"] is False
    assert 0 <= p["relationship_score"] <= 100
    assert any("🔥" in x for x in format_binance_lines({"binance_intelligence": p}))


def test_history_requires_exact_chain_token_and_pair_when_known(tmp_path: Path):
    ledger = {
        "events": {
            "good": {"first_seen_at": "t0", "last_seen_at": "t1", "event": event(event_type="LAUNCHPOOL_ALPHA_AIRDROP", excerpt="Binance Alpha ABC")},
            "wrong_pair": {"event": event(pair_address="0x9999999999999999999999999999999999999999")},
            "wrong_token": {"event": event(contract="0x3333333333333333333333333333333333333333")},
        }
    }
    (tmp_path / "catalyst-wire-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    p = build_profile(event(), tmp_path)
    assert p["historical_official_events"] == 1
    assert p["truth_contract"]["symbol_only_history_never_scores"] is True


def test_multistage_journey_scores_above_first_event(tmp_path: Path):
    first = build_profile(event(), tmp_path)
    ledger = {"events": {"alpha": {"first_seen_at": "t0", "last_seen_at": "t1", "event": event(event_type="LAUNCHPOOL_ALPHA_AIRDROP", excerpt="Binance Alpha and Launchpool for ABC")}}}
    (tmp_path / "catalyst-wire-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    later = build_profile(event(), tmp_path)
    assert later["relationship_score"] > first["relationship_score"]
    assert later["relationship_class"] in {"MULTI_STAGE_BINANCE_JOURNEY", "ECOSYSTEM_INVOLVEMENT_EVIDENCE"}


def test_development_involvement_not_inferred_without_exact_evidence(tmp_path: Path):
    (tmp_path / "social-intelligence-v2.json").write_text(json.dumps({"tokens": [{"symbol": "ABC", "text": "Binance Labs invested"}]}), encoding="utf-8")
    p = build_profile(event(), tmp_path)
    assert p["ecosystem_involvement"]["status"] == "NOT_VERIFIED"


def test_explicit_exact_identity_ecosystem_evidence_is_context_only(tmp_path: Path):
    token = event()["contract"]
    (tmp_path / "social-intelligence-v2.json").write_text(json.dumps({"tokens": [{"token_address": token, "text": "Binance Labs invested in ABC and incubated the project"}]}), encoding="utf-8")
    p = build_profile(event(), tmp_path)
    assert p["ecosystem_involvement"]["status"] == "EVIDENCE_PRESENT"
    assert "BINANCE_LABS_OR_YZI" in p["ecosystem_involvement"]["tags"]
    assert p["production_effect"] is False


def test_non_binance_event_is_not_upweighted(tmp_path: Path):
    p = build_profile(event(source_owner="mexc", source_id="MEXC_SPOT_LISTINGS"), tmp_path)
    assert p == {"applicable": False, "production_effect": False}
