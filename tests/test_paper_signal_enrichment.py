from wallet500.paper_signal_enrichment import enrich_positions


def test_immutable_t0_signal_dna_is_preferred_for_paper_position():
    positions = [{"key": "solana:MINT:PAIR", "cost_usd": 10.0}]
    records = [{
        "key": "solana:MINT:PAIR",
        "t0_at": "2026-09-05T18:00:00+00:00",
        "immutable_t0": True,
        "t0_signal_dna": {"features": {"holder_acceleration": 0.8}},
        "t0_revival_phase": {"phase": "WAKING"},
        "t0_wallet_intent": {"label": "CLUSTER_ACCUMULATION"},
        "t0_expected_value": {"expected_return_scenario_pct": 44.0},
    }]
    candidates = [{
        "key": "solana:MINT:PAIR",
        "signal_dna": {"features": {"holder_acceleration": 0.1}},
    }]
    out = enrich_positions(positions, records, candidates)
    row = out[0]
    assert row["entry_signal_dna"] == records[0]["t0_signal_dna"]
    assert row["entry_revival_phase"]["phase"] == "WAKING"
    assert row["entry_wallet_intent"]["label"] == "CLUSTER_ACCUMULATION"
    assert row["signal_dna_immutable_t0"] is True


def test_current_candidate_is_only_fallback_when_no_t0_record_exists():
    positions = [{"key": "solana:MINT:PAIR"}]
    candidates = [{
        "key": "solana:MINT:PAIR",
        "observed_at": "2026-09-05T18:00:00+00:00",
        "signal_dna": {"features": {"holder_acceleration": 0.4}},
        "revival_phase": {"phase": "STIRRING"},
        "wallet_intent": {"label": "PROBE_BUY"},
        "expected_value": {"expected_return_scenario_pct": 12.0},
    }]
    out = enrich_positions(positions, [], candidates)
    assert out[0]["entry_signal_dna"] == candidates[0]["signal_dna"]
    assert out[0]["signal_dna_immutable_t0"] is False
