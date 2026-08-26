from wallet500.anomaly import anomaly_score, evaluate
from wallet500.models import MarketEvent


def test_high_anomaly_enters_watchlist():
    metrics = {"volume": 90, "buyer_growth": 90, "liquidity": 80, "accumulation": 90, "tx_acceleration": 85, "revival": 70}
    event = MarketEvent(chain="solana", token="TEST", event_type="scan", score=0, metrics=metrics)
    candidate = evaluate(event)
    assert candidate is not None
    assert candidate.anomaly_score >= 70


def test_score_is_bounded():
    assert 0 <= anomaly_score({"volume": 999}) <= 100
