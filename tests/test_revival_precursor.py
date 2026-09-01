from wallet500.revival_precursor import evaluate, score_derivatives, score_social, score_whale


def coin():
    return {
        "network": "solana",
        "token_address": "Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk",
        "symbol": "USELESS",
        "name": "Useless Coin",
        "id": "the-useless-coin",
        "dex_pair_address": "Q2sPHPdUWFMg7M7wwrQKLrn619cAucfRsmhVJffodSp",
        "price_usd": 0.07,
        "drawdown_from_ath_pct": 84,
        "change_24h_pct": 7,
        "change_7d_pct": 18,
        "change_30d_pct": 9,
        "relative_strength_24h_vs_universe_pp": 9,
        "relative_strength_7d_vs_universe_pp": 14,
        "dex_pair_liquidity_usd": 2_500_000,
        "dex_pair_volume_24h_usd": 3_000_000,
        "revival_score_verified": 82,
        "revival_score_components": {
            "same_pair_as_previous": True,
            "liquidity_change_pct": 3.5,
            "pair_volume_change_pct": 45,
        },
    }


def waking():
    return {
        "confirmation_status": "WAKING_STRONG_RESEARCH",
        "channels": {
            "holders": {
                "verified": True,
                "score": 80,
                "signals": ["HOLDER_GROWTH_GE_1PCT"],
            },
            "wallets": {
                "verified": True,
                "score": 75,
                "signals": ["UNIQUE_WALLET_24H_CHANGE_+35.00PCT"],
            },
            "social": {
                "verified": True,
                "score": 70,
                "signals": ["SOCIAL_COUNT_VS_PREVIOUS_2.40X"],
                "metrics": {"sources": 3, "authors": 8, "mentions": 22},
            },
        },
    }


def whale():
    return {
        "verified": True,
        "exact_mint_verified": True,
        "whale_netflow_usd_24h": 250_000,
        "whale_netflow_usd_7d": 900_000,
        "smart_wallet_accumulator_count": 6,
        "smart_wallet_netflow_usd_24h": 110_000,
    }


def derivatives():
    return {
        "verified": True,
        "canonical_token_mapping_verified": True,
        "open_interest_change_24h_pct": 35,
        "open_interest_usd": 8_000_000,
        "funding_rate_pct": 0.02,
        "derivatives_exchange_count": 4,
        "spot_cex_count": 8,
    }


def test_full_independent_evidence_can_be_high_conviction_precursor():
    row = evaluate(coin(), waking(), whale(), derivatives())
    assert row["status"] in {"HIGH_CONVICTION_PRECURSOR", "PRE_BREAKOUT_CANDIDATE"}
    assert row["evidence_coverage_pct"] == 100.0
    assert "whale_smart_money" in row["strong_families"]
    assert "derivatives_cex" in row["strong_families"]


def test_missing_whale_and_derivatives_never_score_as_true():
    row = evaluate(coin(), waking(), None, None)
    assert row["families"]["whale_smart_money"]["score"] is None
    assert row["families"]["derivatives_cex"]["score"] is None
    assert "WHALE_SMART_MONEY_EXACT_MINT" in row["missing_evidence"]
    assert "DERIVATIVES_CANONICAL_MAPPING" in row["missing_evidence"]
    assert row["evidence_coverage_pct"] < 100


def test_symbol_only_derivatives_cannot_score():
    score, signals, missing = score_derivatives({
        "verified": True,
        "canonical_token_mapping_verified": False,
        "open_interest_change_24h_pct": 200,
    })
    assert score is None
    assert signals == []
    assert missing == ["DERIVATIVES_CANONICAL_MAPPING"]


def test_whale_flow_requires_exact_mint_verification():
    score, signals, missing = score_whale({
        "verified": True,
        "exact_mint_verified": False,
        "whale_netflow_usd_24h": 10_000_000,
    })
    assert score is None
    assert signals == []
    assert missing == ["WHALE_SMART_MONEY_EXACT_MINT"]


def test_social_single_source_hype_is_capped():
    score, signals, missing = score_social({
        "social": {
            "verified": True,
            "score": 95,
            "metrics": {"sources": 1, "authors": 2},
            "signals": ["SOCIAL_COUNT_VS_PREVIOUS_5.00X"],
        }
    })
    assert score == 35.0
    assert "SOCIAL_SINGLE_SOURCE_OR_LOW_AUTHOR_DIVERSITY" in signals
    assert missing == []


def test_late_move_is_do_not_chase_even_with_strong_evidence():
    late = coin()
    late["change_24h_pct"] = 43
    row = evaluate(late, waking(), whale(), derivatives())
    assert row["status"] == "LATE_MOVE_DO_NOT_CHASE"
