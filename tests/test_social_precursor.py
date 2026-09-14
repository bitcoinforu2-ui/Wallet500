from wallet500.accuracy_contracts import ALERT_SCORE_THRESHOLD
from wallet500.production_risk_gate import evaluate
from wallet500.social_precursor import (
    assess_social_precursors,
    normalized_social_velocity,
    parse_coinmarketcal_event,
    provider_configuration,
)

NOW = "2026-09-14T12:00:00Z"


def _evidence(**overrides):
    row = {
        "provider": "lunarcrush",
        "external_id": "post-1",
        "feature": "mention_velocity",
        "chain": "bsc",
        "contract": "0xABC",
        "identity_status": "EXACT",
        "published_at": "2026-09-14T11:45:00Z",
        "fetched_at": "2026-09-14T11:46:00Z",
        "strength": 0.9,
        "confidence": 0.8,
    }
    row.update(overrides)
    return row


def test_ticker_only_or_unresolved_identity_never_scores():
    candidate = {"chain": "bsc", "token": "0xABC"}
    unresolved = _evidence(
        contract=None,
        identity_status="TICKER_ONLY",
        ticker="ABC",
    )
    result = assess_social_precursors(candidate, [unresolved], now=NOW)
    assert result["detected"] is False
    assert result["shadow_score"] == 0.0
    assert result["accepted_exact_count"] == 0
    assert result["rejected"]["IDENTITY_UNRESOLVED_OR_AMBIGUOUS"] == 1


def test_exact_identity_can_rank_shadow_but_never_promote_or_act():
    candidate = {"chain": "bsc", "token": "0xabc"}
    result = assess_social_precursors(candidate, [_evidence()], now=NOW)
    assert result["detected"] is True
    assert result["shadow_score"] > 0
    assert result["ranking_only"] is True
    assert result["research_shadow"] is True
    assert result["research_only"] is True
    assert result["actionable"] is False
    assert result["real_alert_eligible"] is False
    assert result["automatic_buy"] is False
    assert result["auto_promote"] is False
    assert result["production_score_effect"] == 0.0


def test_future_evidence_is_rejected_to_prevent_time_leakage():
    candidate = {"chain": "bsc", "token": "0xabc"}
    result = assess_social_precursors(
        candidate,
        [_evidence(published_at="2026-09-14T12:01:00Z")],
        now=NOW,
    )
    assert result["detected"] is False
    assert result["rejected"]["FUTURE_TIMESTAMP"] == 1


def test_duplicates_are_counted_once():
    candidate = {"chain": "bsc", "token": "0xabc"}
    row = _evidence()
    result = assess_social_precursors(candidate, [row, dict(row)], now=NOW)
    assert result["accepted_exact_count"] == 1
    assert result["duplicate_count"] == 1


def test_stale_social_evidence_is_neutral():
    candidate = {"chain": "bsc", "token": "0xabc"}
    result = assess_social_precursors(
        candidate,
        [_evidence(published_at="2026-09-14T04:00:00Z")],
        now=NOW,
    )
    assert result["detected"] is False
    assert result["stale_count"] == 1
    assert result["shadow_score"] == 0.0


def test_social_velocity_is_normalized_by_elapsed_time():
    fast = normalized_social_velocity(
        [
            {"observed_at": "2026-09-14T11:40:00Z", "value": 100},
            {"observed_at": "2026-09-14T11:50:00Z", "value": 200},
        ],
        now=NOW,
    )
    slow = normalized_social_velocity(
        [
            {"observed_at": "2026-09-14T11:20:00Z", "value": 100},
            {"observed_at": "2026-09-14T11:40:00Z", "value": 200},
        ],
        now=NOW,
    )
    assert fast["valid"] is True
    assert slow["valid"] is True
    assert fast["rate_per_min"] == 10.0
    assert slow["rate_per_min"] == 5.0


def test_optional_provider_without_key_is_neutral_not_positive_evidence():
    status = provider_configuration("lunarcrush", environ={})
    assert status["supported"] is True
    assert status["configured"] is False
    assert status["missing_credentials_is_positive_evidence"] is False
    assert status["production_effect"] is False


def test_estimated_coinmarketcal_date_is_not_promoted_to_exact_event_time():
    parsed = parse_coinmarketcal_event(
        {
            "id": 77,
            "date": "2026-09-16T10:00:00Z",
            "displayedDate": "Q3 2026",
            "isEstimated": True,
            "strength": 0.9,
        },
        fetched_at="2026-09-14T11:50:00Z",
        chain="bsc",
        contract="0xABC",
    )
    assert parsed["event_time_is_exact"] is False
    assert parsed["event_at"] is None
    assert parsed["estimated_window_deadline"] == "2026-09-16T10:00:00Z"
    result = assess_social_precursors(
        {"chain": "bsc", "token": "0xabc"}, [parsed], now=NOW
    )
    assert result["detected"] is False
    assert result["rejected"]["ESTIMATED_CATALYST_NOT_EXACT_TIMING"] == 1


def test_real_alert_threshold_remains_85():
    assert ALERT_SCORE_THRESHOLD == 85.0


def test_social_shadow_cannot_change_production_gate_decision():
    base = {
        "chain": "bsc",
        "token": "0xabc",
        "liquidity_usd": 90000,
        "lp_verified": True,
        "social_as_of": NOW,
    }
    without_social = evaluate(dict(base), {})
    with_social = evaluate({**base, "social_evidence": [_evidence()]}, {})
    for key in (
        "production_risk_gate",
        "production_risk_blocked",
        "production_risk_critical",
        "production_risk_reasons",
    ):
        assert with_social[key] == without_social[key]
    shadow = with_social["social_precursor_shadow"]
    assert shadow["detected"] is True
    assert shadow["production_score_effect"] == 0.0
    assert shadow["real_alert_eligible"] is False
