def wallet_forensics(profile: dict) -> dict:
    txs = int(profile.get("transactions_seen", 0))
    success_rate = float(profile.get("success_rate", 0.0))
    if txs >= 80 and success_rate >= 0.98:
        tier = "HIGH_ACTIVITY_RELIABLE"
    elif txs >= 30 and success_rate >= 0.95:
        tier = "ACTIVE_RELIABLE"
    elif txs >= 10:
        tier = "OBSERVE"
    else:
        tier = "LOW_DATA"
    confidence = min(100.0, txs) * success_rate
    return {**profile, "forensics_tier": tier, "confidence": round(confidence, 2)}
