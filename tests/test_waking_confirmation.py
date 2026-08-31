from wallet500.waking_confirmation import (
    confirmation_status,
    extract_birdeye_overview_metrics,
    score_holder_growth,
    score_news,
    score_social,
    score_wallet_growth,
)


def test_birdeye_overview_metric_extraction():
    payload = {
        "data": {
            "holder": 1000,
            "uniqueWallet1h": 120,
            "uniqueWallet1hChangePercent": 25,
            "uniqueWallet4h": 300,
            "uniqueWallet4hChangePercent": 12,
            "uniqueWallet24h": 900,
            "uniqueWallet24hChangePercent": 5,
        }
    }
    m = extract_birdeye_overview_metrics(payload)
    assert m["holder_count"] == 1000
    assert m["unique_wallet_1h"] == 120
    assert m["unique_wallet_change_1h_pct"] == 25


def test_holder_growth_requires_baseline():
    score, signals, change = score_holder_growth(1100, None)
    assert score == 0
    assert change is None
    assert "HOLDER_BASELINE_LEARNING" in signals

    score, signals, change = score_holder_growth(1100, 1000)
    assert score == 100
    assert change == 10.0
    assert "HOLDER_GROWTH_GE_7_5PCT" in signals


def test_wallet_growth_scores_acceleration():
    score, signals = score_wallet_growth({
        "unique_wallet_change_1h_pct": 60,
        "unique_wallet_change_4h_pct": 30,
        "unique_wallet_change_24h_pct": 12,
    })
    assert score > 50
    assert any("UNIQUE_WALLET_1H" in x for x in signals)


def test_social_and_news_are_attention_not_direction():
    social_score, social_signals = score_social([
        {"source": "reddit", "author": "a"},
        {"source": "youtube", "author": "b"},
        {"source": "reddit", "author": "c"},
    ], 1)
    assert social_score >= 50
    assert any("SOCIAL_COUNT_VS_PREVIOUS" in x for x in social_signals)

    news_score, news_signals, catalysts = score_news([
        {"author": "Outlet A", "text": "Project announces exchange listing"},
        {"author": "Outlet B", "text": "Project partnership and mainnet launch"},
    ], 1)
    assert news_score > 0
    assert "listing" in catalysts
    assert any("CATALYST_KEYWORDS" in x for x in news_signals)


def test_confirmation_needs_independent_families():
    weak = {
        "holders": {"verified": True, "score": 80},
        "wallets": {"verified": False, "score": 0},
        "social": {"verified": False, "score": 0},
        "news": {"verified": False, "score": 0},
    }
    status, score, strong = confirmation_status(weak, None)
    assert status == "WAKING_UNCONFIRMED_RESEARCH"
    assert strong == ["holders"]

    confirmed = {
        "holders": {"verified": True, "score": 80},
        "wallets": {"verified": True, "score": 80},
        "social": {"verified": True, "score": 70},
        "news": {"verified": False, "score": 0},
    }
    status, score, strong = confirmation_status(confirmed, {"risk_score": 10})
    assert status == "WAKING_STRONG_RESEARCH"
    assert score >= 45
    assert len(strong) >= 3

    status, _, _ = confirmation_status(confirmed, {"risk_score": 65})
    assert status == "WAKING_RISK_RESEARCH"
