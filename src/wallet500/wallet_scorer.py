from __future__ import annotations


def score_wallet(profile: dict, discovery: dict | None = None) -> dict:
    discovery = discovery or {}
    tx = int(profile.get("transactions_seen", 0))
    success = float(profile.get("success_rate", 0.0))
    balance = float(profile.get("balance_sol", 0.0))
    source_hits = int(discovery.get("hits", 0))
    token_count = int(discovery.get("token_count", 0))

    activity = min(35.0, tx / 100.0 * 35.0)
    reliability = min(25.0, max(0.0, success) * 25.0)
    discovery_score = min(25.0, source_hits * 2.5 + token_count * 3.0)
    capital = min(15.0, balance / 100.0 * 15.0)
    score = round(activity + reliability + discovery_score + capital, 2)

    tier = "ELITE" if score >= 85 else "STRONG" if score >= 70 else "WATCH" if score >= 50 else "LOW"
    return {**profile, "wallet_score": score, "tier": tier, "subscores": {"activity": round(activity, 2), "reliability": round(reliability, 2), "discovery": round(discovery_score, 2), "capital": round(capital, 2)}}


def rank_wallets(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda x: (x.get("wallet_score", 0), x.get("transactions_seen", 0)), reverse=True)
