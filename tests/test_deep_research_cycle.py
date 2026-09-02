from wallet500.deep_research_cycle import _research_state, _select_targets


CA1 = "ULwSJmmpxmnRfpu6BjnK6rprKXqD5jXUmPpS1FxHXFy"
PAIR1 = "CJcu7ciRHBHu4BDnpLgAUm1A6iSp9RuhJMG36rjjrxnd"
CA2 = "H2c31USxu35MDkBrGph8pUDUnmzo2e4Rf4hnvL2Upump"
PAIR2 = "Y8YyWu9gyCYSomE99JkDvsfR4eHNEeQpWtR8quGpBwX"


def test_select_targets_requires_exact_mint_and_pair_and_respects_budget():
    payload = {
        "queue": [
            {"token_address": CA1, "pair_address": PAIR1, "risk_score": 0, "hybrid_score_verified_normalized": 80},
            {"token_address": CA2, "pair_address": PAIR2, "risk_score": 5, "hybrid_score_verified_normalized": 70},
            {"token_address": "bad", "pair_address": PAIR2, "risk_score": 0, "hybrid_score_verified_normalized": 99},
            {"token_address": CA1, "pair_address": PAIR1, "risk_score": 0, "hybrid_score_verified_normalized": 90},
        ]
    }
    rows = _select_targets(payload, 1)
    assert len(rows) == 1
    assert rows[0]["token_address"] == CA1


def test_organic_plus_positive_catalyst_is_convergence():
    state, reasons, score = _research_state(
        market={"liquidity_usd": 120000, "volume_24h_usd": 50000},
        previous={"market": {"liquidity_usd": 100000, "volume_24h_usd": 30000}},
        organic={"status": "STRONG_ORGANIC_ACCELERATION"},
        catalysts={"positive": ["partnership"], "negative": []},
        risk_score=0,
    )
    assert state == "CATALYST_ORGANIC_CONVERGENCE"
    assert "STRONG_ORGANIC_SOCIAL_ACCELERATION" in reasons
    assert score > 50


def test_liquidity_collapse_becomes_risk_divergence_even_with_attention():
    state, reasons, score = _research_state(
        market={"liquidity_usd": 50000, "volume_24h_usd": 80000},
        previous={"market": {"liquidity_usd": 100000, "volume_24h_usd": 40000}},
        organic={"status": "STRONG_ORGANIC_ACCELERATION"},
        catalysts={"positive": ["listing"], "negative": []},
        risk_score=0,
    )
    assert state == "RISK_DIVERGENCE"
    assert any(x.startswith("LIQUIDITY_DETERIORATION") for x in reasons)


def test_raw_mentions_alone_are_not_a_deep_research_positive_signal():
    state, reasons, score = _research_state(
        market={"liquidity_usd": 100000, "volume_24h_usd": 20000},
        previous={"market": {"liquidity_usd": 100000, "volume_24h_usd": 20000}},
        organic={"status": "NO_ORGANIC_SIGNAL", "last_24h": {"raw_mentions": 1000}},
        catalysts={"positive": [], "negative": []},
        risk_score=0,
    )
    assert state == "NO_NEW_CONTEXT"
    assert score == 50
    assert reasons == ["NO_MATERIAL_CONTEXT_CHANGE"]
