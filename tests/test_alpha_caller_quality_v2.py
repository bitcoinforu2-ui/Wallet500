from datetime import datetime, timezone

from scripts import alpha_caller_reputation as reputation
from scripts import unified_candidate_bridge as bridge


NOW = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
SOL = "11111111111111111111111111111111"


def candidate(source, caller, called_at, *, status="REJECTED", reason="NO_CHAIN_VERIFIED_LIVE_LIQUID_MARKET"):
    return {
        "source": source,
        "caller": caller,
        "origin_caller": caller,
        "network": "solana",
        "contract": SOL,
        "pair": "pair-1",
        "called_at": called_at,
        "observed_at": called_at,
        "status": status,
        "signal_role": "candidate_discovery",
        "reasons": [reason],
    }


def test_reliability_keeps_previously_verified_call_even_if_market_later_dies():
    row = candidate("A", "Caller A", "2026-09-19T20:00:00+00:00")
    verified = [{
        "source": "A",
        "caller": "Caller A",
        "contract": SOL,
        "called_at": "2026-09-19T20:00:00+00:00",
    }]
    cards = reputation.intake_reliability([row], verified, current_dt=NOW)
    card = cards[("a", "caller a")]
    assert card["ever_verified"] == 1
    assert card["mature_unverified"] == 0
    assert card["ever_verified_rate"] == 1.0


def test_reliability_counts_mature_never_verified_call_as_miss():
    row = candidate("Spam", "Caller Spam", "2026-09-19T20:00:00+00:00")
    cards = reputation.intake_reliability([row], [], current_dt=NOW)
    card = cards[("spam", "caller spam")]
    assert card["ever_verified"] == 0
    assert card["mature_unverified"] == 1
    assert card["ever_verified_rate"] == 0.0
    assert card["top_rejection_reasons"][0]["reason"] == "NO_CHAIN_VERIFIED_LIVE_LIQUID_MARKET"


def test_recent_unverified_call_waits_for_maturity_before_penalty():
    row = candidate("A", "Caller A", "2026-09-19T23:45:00+00:00")
    cards = reputation.intake_reliability([row], [], current_dt=NOW)
    card = cards[("a", "caller a")]
    assert card["pending_unverified"] == 1
    assert card["mature_unverified"] == 0
    assert card["mature_evaluable_calls"] == 0


def alpha_row(caller, minute, fingerprint, *, source="Direct", source_class="direct_caller"):
    return {
        "status": "GATED_RESEARCH_CANDIDATE",
        "signal_role": "candidate_discovery",
        "source": source,
        "source_class": source_class,
        "caller": caller,
        "origin_caller": caller,
        "network": "solana",
        "contract": SOL,
        "pair": "pair-1",
        "called_at": f"2026-09-19T23:{minute:02d}:00+00:00",
        "source_content_fingerprint": fingerprint,
    }


def test_same_origin_direct_and_aggregator_count_once():
    rows = [
        alpha_row("Degen Seals", 30, "fp-direct", source="Degen Seals"),
        alpha_row("Degen Seals", 31, "fp-aggregator", source="Call Analyser SOL", source_class="caller_aggregator"),
    ]
    metrics = bridge.alpha_convergence_metrics(rows, current=NOW)[f"solana:{SOL}"]
    assert metrics["alpha_independent_callers_30m"] == 1
    assert metrics["alpha_convergence_tier"] == "SINGLE_SOURCE"


def test_exact_copied_message_from_different_handles_is_not_independent():
    rows = [
        alpha_row("Caller A", 30, "same-post"),
        alpha_row("Caller B", 32, "same-post"),
    ]
    metrics = bridge.alpha_convergence_metrics(rows, current=NOW)[f"solana:{SOL}"]
    assert metrics["alpha_independent_callers_30m"] == 1


def test_two_and_three_distinct_callers_create_convergence():
    two = [
        alpha_row("Caller A", 30, "a"),
        alpha_row("Caller B", 38, "b"),
    ]
    metrics = bridge.alpha_convergence_metrics(two, current=NOW)[f"solana:{SOL}"]
    assert metrics["alpha_first_caller"] == "Caller A"
    assert metrics["alpha_independent_callers_15m"] == 2
    assert metrics["alpha_convergence_tier"] == "DOUBLE_SOURCE_CONVERGENCE"

    three = two + [alpha_row("Caller C", 45, "c")]
    metrics = bridge.alpha_convergence_metrics(three, current=NOW)[f"solana:{SOL}"]
    assert metrics["alpha_independent_callers_30m"] == 3
    assert metrics["alpha_convergence_tier"] == "MULTI_SOURCE_CONVERGENCE"


def test_generic_aggregator_fallback_does_not_count_as_caller():
    rows = [
        alpha_row("Call Analyser", 30, "a", source="Call Analyser", source_class="caller_aggregator"),
        alpha_row("Caller B", 35, "b"),
    ]
    metrics = bridge.alpha_convergence_metrics(rows, current=NOW)[f"solana:{SOL}"]
    assert metrics["alpha_independent_callers_30m"] == 1
    assert metrics["alpha_first_caller"] == "Caller B"
