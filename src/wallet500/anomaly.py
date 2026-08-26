from .models import Candidate, MarketEvent


WEIGHTS = {
    "volume": 0.20,
    "buyer_growth": 0.20,
    "liquidity": 0.15,
    "accumulation": 0.20,
    "tx_acceleration": 0.15,
    "revival": 0.10,
}


def anomaly_score(metrics: dict[str, float]) -> float:
    score = sum(max(0.0, min(100.0, metrics.get(k, 0.0))) * w for k, w in WEIGHTS.items())
    return round(score, 2)


def evaluate(event: MarketEvent, threshold: float = 70.0) -> Candidate | None:
    score = anomaly_score(event.metrics)
    if score < threshold:
        return None
    reasons = [k for k in WEIGHTS if event.metrics.get(k, 0) >= 70]
    return Candidate(chain=event.chain, token=event.token, anomaly_score=score, reasons=reasons)
