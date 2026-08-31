from wallet500.hybrid_research_context import enrich_payload

TOKEN = "11111111111111111111111111111111"
PAIR = "22222222222222222222222222222222"


def channel(score=0, available=True, deviation=None):
    out = {"available": available, "score": score}
    if deviation is not None:
        out["deviation"] = deviation
    return out


def hybrid_profile(market=70, liquidity=75, holders=0, wallets=0, risk=10):
    return {
        "mode": "RESEARCH_ONLY_HYBRID_TOKEN_PROFILE_V1",
        "contract": "HYBRID_TOKEN_PROFILE_V1",
        "network": "solana",
        "profiles": [
            {
                "token_address": TOKEN,
                "symbol": "TEST",
                "name": "Test Token",
                "observed_at": "2026-01-01T01:00:00+00:00",
                "baseline_ready": True,
                "status": "ABNORMAL_ACTIVITY",
                "hybrid_score_verified_normalized": 80,
                "risk_score": risk,
                "identity": {"exact_pair_verified": True, "dex_pair_address": PAIR},
                "channels": {
                    "market": channel(market),
                    "liquidity_pair": channel(
                        liquidity,
                        deviation={
                            "liquidity": {"change_from_previous_pct": 3.5},
                            "pair_volume_24h": {"ratio_to_baseline": 1.8},
                        },
                    ),
                    "holders": channel(holders, available=holders > 0),
                    "wallets": channel(wallets, available=wallets > 0),
                    "social": channel(0, available=False),
                    "news": channel(0, available=False),
                },
            }
        ],
    }


def liq_learning(signal="LIQ_LEADS"):
    return {
        "mode": "RESEARCH_ONLY_REVIVAL_LIQUIDITY_LEARNING_V1",
        "current_signals": [
            {
                "token_address": TOKEN,
                "research_signal": signal,
                "baseline_at": "2026-01-01T00:30:00+00:00",
                "liquidity_change_30m_pct": 5.2,
                "price_change_30m_pct": 1.1,
                "market_cap_change_30m_pct": 1.1,
                "liq_mcap_pct": 4.2,
                "liq_mcap_ratio_change_30m_pct": 4.0,
            }
        ],
    }


def historical():
    return {
        "mode": "RESEARCH_ONLY_REVIVAL_HISTORICAL_DNA_V1",
        "network": "solana",
        "counts": {"research_ready_archetypes": 1},
        "archetypes": {
            "LIQ_LEADS": {
                "status": "RESEARCH_READY",
                "events_detected": 50,
                "horizons": {
                    "180m": {
                        "status": "RESEARCH_READY",
                        "sample_n": 40,
                        "unique_tokens": 20,
                        "median_return_pct": 8.0,
                        "hit_10pct_rate": 45.0,
                        "hit_25pct_rate": 20.0,
                        "hit_50pct_rate": 7.5,
                    }
                },
            }
        },
    }


def test_two_independent_signal_families_queue_catalyst_scan():
    enriched, summary, queue, ledger = enrich_payload(
        hybrid_profile(), liq_learning(), historical(), {}, {}, {}, "2026-01-01T01:01:00+00:00"
    )
    ctx = enriched["profiles"][0]["research_context"]
    assert ctx["catalyst_scan"]["requested"] is True
    assert set(ctx["catalyst_scan"]["trigger_families"]) == {"MARKET", "LIQUIDITY_FLOW"}
    assert queue["queue_count"] == 1
    assert ledger["events_count"] == 1
    assert summary["production_impact"] == "NONE"


def test_correlated_liquidity_signals_count_as_one_family():
    h = hybrid_profile(market=20, liquidity=80)
    enriched, _, queue, _ = enrich_payload(h, liq_learning(), historical(), {}, {}, {}, "2026-01-01T01:01:00+00:00")
    ctx = enriched["profiles"][0]["research_context"]
    assert ctx["independent_signal_families"] == ["LIQUIDITY_FLOW"]
    assert ctx["catalyst_scan"]["requested"] is False
    assert queue["queue_count"] == 0


def test_historical_match_exposes_sample_and_never_changes_hybrid_score():
    h = hybrid_profile()
    before = h["profiles"][0]["hybrid_score_verified_normalized"]
    enriched, _, _, _ = enrich_payload(h, liq_learning(), historical(), {}, {}, {}, "2026-01-01T01:01:00+00:00")
    p = enriched["profiles"][0]
    match = p["research_context"]["historical_matches"][0]
    assert match["archetype"] == "LIQ_LEADS"
    assert match["horizons"]["180m"]["sample_n"] == 40
    assert p["hybrid_score_verified_normalized"] == before


def test_legacy_winner_dna_is_blocked_when_balanced_solana_study_missing():
    legacy = {"winner_n": 100, "control_n": 2}
    enriched, _, _, _ = enrich_payload(hybrid_profile(), liq_learning(), historical(), legacy, {}, {}, "2026-01-01T01:01:00+00:00")
    gate = enriched["profiles"][0]["research_context"]["winner_dna_gate"]
    assert gate["usable_for_context"] is False
    assert gate["status"] == "BLOCKED_LEGACY_UNBALANCED_SAMPLE"
