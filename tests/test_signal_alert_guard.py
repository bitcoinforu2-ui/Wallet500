from wallet500.signal_alert_guard import apply


def real_payload():
    return {
        "counts": {"real_alerts": 1, "verified_watch_not_real": 0},
        "truth_contract": {},
        "alerts": [{
            "status": "REAL_ALERT",
            "actionable_research_alert": True,
            "chain": "solana",
            "token_address": "MINT",
            "pair_address": "PAIR",
            "symbol": "OLD",
            "blockers": [],
        }],
        "verified_watch": [],
    }


def signal(safe=True, validated=False):
    return {
        "mode": "PROSPECTIVE_SIGNAL_DNA_SELF_LEARNING_SHADOW_V1",
        "data_health": {"production_safe": safe, "status": "HEALTHY" if safe else "DATA_DEGRADED_FAIL_CLOSED"},
        "self_learning_model": {"status": "VALIDATED_FOR_RANKING_ONLY" if validated else "COLLECTING_SAMPLE", "validated": validated, "ranking_effect": validated},
        "winner_loser_dna": {"status": "READY"},
        "missed_winner_lab": {"false_negative_winners": 4},
        "candidates": [{
            "key": "solana:MINT:PAIR",
            "chain": "solana",
            "token_address": "MINT",
            "pair_address": "PAIR",
            "signal_dna": {"features": {"holder_acceleration": 0.7}},
            "wallet_intent": {"label": "CLUSTER_ACCUMULATION"},
            "revival_phase": {"phase": "WAKING"},
            "expected_value": {"expected_return_scenario_pct": 42.0},
            "observed_at": "2026-09-05T18:00:00+00:00",
        }],
    }


def test_healthy_signal_intelligence_enriches_without_changing_gate():
    out = apply(real_payload(), signal(True))
    assert out["counts"]["real_alerts"] == 1
    row = out["alerts"][0]
    assert row["status"] == "REAL_ALERT"
    assert row["revival_phase"]["phase"] == "WAKING"
    assert row["wallet_intent"]["label"] == "CLUSTER_ACCUMULATION"
    assert out["truth_contract"]["self_learning_can_rank_but_never_auto_promote"] is True


def test_degraded_required_data_demotes_every_real_alert_fail_closed():
    out = apply(real_payload(), signal(False))
    assert out["counts"]["real_alerts"] == 0
    assert out["counts"]["data_degraded_demotions"] == 1
    row = out["verified_watch"][0]
    assert row["status"] == "DATA_DEGRADED_NOT_REAL_ALERT"
    assert row["actionable_research_alert"] is False
    assert "DATA_DEGRADED_FAIL_CLOSED" in row["blockers"]
