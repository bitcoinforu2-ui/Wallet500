from wallet500.revival_precursor import attach_immutable_t0, evaluate, score_derivatives, score_paid_attention, score_social, score_whale


def coin():
    return {
        "network": "solana",
        "token_address": "Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk",
        "symbol": "USELESS",
        "name": "Useless Coin",
        "id": "the-useless-coin",
        "dex_pair_address": "Q2sPHPdUWFMg7M7wwrQKLrn619cAucfRsmhVJffodSp",
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
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


def paid_events(h24=8, h6=12, boost=500, include_ad=True):
    pair = coin()["dex_pair_address"]
    token = coin()["token_address"]
    rows = [{
        "event_id": "boost-1",
        "provider": "dexscreener",
        "promotion_type": "BOOST",
        "chain": "solana",
        "token_address": token,
        "pair_address": pair,
        "pair_identity_locked": True,
        "first_seen_at": "2026-09-01T01:00:00+00:00",
        "last_seen_at": "2026-09-01T02:00:00+00:00",
        "boost_total_amount_latest": boost,
        "t0": {
            "price_change_h1_pct": 3,
            "price_change_h6_pct": h6,
            "price_change_h24_pct": h24,
            "liquidity_usd": 500_000,
        },
        "impact_by_horizon": [{"horizon_min": 360, "promoted_price_change_pct": 9999}],
    }]
    if include_ad:
        rows.append({
            "event_id": "ad-1",
            "provider": "dexscreener",
            "promotion_type": "AD",
            "chain": "solana",
            "token_address": token,
            "pair_address": pair,
            "pair_identity_locked": True,
            "first_seen_at": "2026-09-01T02:00:00+00:00",
            "last_seen_at": "2026-09-01T02:00:00+00:00",
            "t0": {
                "price_change_h1_pct": 4,
                "price_change_h6_pct": h6,
                "price_change_h24_pct": h24,
                "liquidity_usd": 500_000,
            },
        })
    return rows


def test_full_independent_evidence_can_be_high_conviction_precursor():
    row = evaluate(coin(), waking(), whale(), derivatives(), paid_events())
    assert row["status"] in {"HIGH_CONVICTION_PRECURSOR", "PRE_BREAKOUT_CANDIDATE"}
    assert row["evidence_coverage_pct"] == 100.0
    assert "whale_smart_money" in row["strong_families"]
    assert "derivatives_cex" in row["strong_families"]
    assert row["paid_attention_bonus"] > 0


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
    row = evaluate(late, waking(), whale(), derivatives(), paid_events())
    assert row["status"] == "LATE_MOVE_DO_NOT_CHASE"


def test_paid_attention_captures_boost_ad_and_prebreakout_timing():
    score, signals, missing, meta = score_paid_attention(paid_events(), coin())
    assert score >= 75
    assert "BOOST_INTENSITY_GE_500" in signals
    assert "AD_AND_BOOST_CONCURRENT" in signals
    assert "PROMOTION_PRE_BREAKOUT_WINDOW" in signals
    assert meta["boost_total_amount_max"] == 500
    assert meta["ad_and_boost_concurrent"] is True
    assert meta["timing_class"] == "PROMOTION_PRE_BREAKOUT_WINDOW"
    assert meta["post_promotion_outcomes_used_for_scoring"] is False
    assert missing == []


def test_late_paid_promotion_is_capped_and_gets_no_bonus():
    events = paid_events(h24=140, h6=95, boost=500)
    score, signals, _, meta = score_paid_attention(events, coin())
    assert score <= 35
    assert "PROMOTION_AFTER_BREAKOUT_LATE" in signals
    assert meta["timing_class"] == "PROMOTION_AFTER_BREAKOUT"
    row = evaluate(coin(), waking(), whale(), derivatives(), events)
    assert row["paid_attention_bonus"] == 0


def test_paid_attention_never_becomes_independent_confirmation():
    row = evaluate(coin(), None, None, None, paid_events())
    assert row["families"]["paid_attention"]["score"] >= 75
    assert row["status"] not in {"PRE_BREAKOUT_CANDIDATE", "HIGH_CONVICTION_PRECURSOR"}


def test_missing_paid_feed_is_explicit_not_fake_zero():
    score, signals, missing, meta = score_paid_attention(None, coin())
    assert score is None
    assert signals == []
    assert missing == ["PAID_VISIBILITY_FEED"]
    assert meta["feed_verified"] is False


def test_verified_no_paid_event_is_zero_not_missing():
    score, signals, missing, meta = score_paid_attention([], coin())
    assert score == 0.0
    assert signals == ["NO_RECENT_PAID_VISIBILITY"]
    assert missing == []
    assert meta["feed_verified"] is True


def test_unverified_pair_can_never_be_actionable():
    unresolved = coin()
    unresolved["dex_link_type"] = "NO_VERIFIED_DEX_PAIR"
    row = evaluate(unresolved, waking(), whale(), derivatives(), paid_events())
    assert row["status"] == "IDENTITY_UNVERIFIED_RESEARCH_ONLY"
    assert row["identity"]["actionable_eligible"] is False
    assert "EXACT_DEX_PAIR" in row["missing_evidence"]


def test_precursor_exposes_verified_holder_wallet_social_facts():
    row = evaluate(coin(), waking(), whale(), derivatives(), paid_events())
    evidence = row["evidence_snapshot"]
    assert evidence["holders"]["verified"] is True
    assert evidence["wallets"]["score"] == 75.0
    assert evidence["social"]["metrics"]["mentions"] == 22


def test_t0_is_immutable_when_later_observation_changes():
    state = {"version": 3, "network": "solana", "targets": {}}
    first = evaluate(coin(), waking(), whale(), derivatives(), paid_events())
    attach_immutable_t0(first, state, "2026-09-01T10:00:00+00:00")
    later_coin = coin()
    later_coin["price_usd"] = 0.14
    later = evaluate(later_coin, waking(), whale(), derivatives(), paid_events())
    attach_immutable_t0(later, state, "2026-09-01T11:00:00+00:00")
    assert later["t0"]["observed_at"] == "2026-09-01T10:00:00+00:00"
    assert later["t0"]["price_usd"] == 0.07
