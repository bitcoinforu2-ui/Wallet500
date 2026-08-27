from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone


def build_evidence_snapshot(candidate: dict, holder_intel: dict | None = None, wallet_intel: dict | None = None, observed_at: str | None = None) -> dict:
    """Build a frozen, append-only evidence record for one discovery observation.

    This function never manufactures missing evidence. Missing holder/wallet layers
    are recorded explicitly as unavailable.
    """
    c=deepcopy(candidate or {})
    ts=observed_at or datetime.now(timezone.utc).isoformat()
    holder=deepcopy(holder_intel) if isinstance(holder_intel,dict) else {
        "status":"NO_VERIFIED_HOLDER_DATA","trust_score":None,"risk_flags":["HOLDER_DATA_UNAVAILABLE"]
    }
    wallet=deepcopy(wallet_intel) if isinstance(wallet_intel,dict) else {
        "status":"NO_VERIFIED_WALLET_DATA"
    }
    return {
        "schema_version":1,
        "evidence_policy":"IMMUTABLE_DISCOVERY_EVIDENCE_NO_HINDSIGHT",
        "observed_at":ts,
        "identity":{
            "chain":c.get("chain"),
            "token":c.get("token") or c.get("mint"),
            "pair_address":c.get("pair_address"),
            "dex":c.get("dex"),
        },
        "market":{
            "price_usd":c.get("price_usd"),
            "liquidity_usd":c.get("liquidity_usd"),
            "market_cap":c.get("market_cap"),
            "fdv":c.get("fdv"),
            "volume_m5":c.get("volume_m5"),
            "volume_h1":c.get("volume_h1"),
            "volume_h24":c.get("volume_h24"),
            "buys_h1":c.get("buys_h1"),
            "sells_h1":c.get("sells_h1"),
            "price_change_m5":c.get("price_change_m5"),
            "price_change_h1":c.get("price_change_h1"),
            "pair_created_at":c.get("pair_created_at"),
        },
        "signals":{
            "anomaly_score":c.get("anomaly_score"),
            "qualification":c.get("qualification"),
            "qualification_reasons":deepcopy(c.get("qualification_reasons") or []),
            "pump_dump_risk_score":c.get("pump_dump_risk_score"),
            "pump_dump_risk_level":c.get("pump_dump_risk_level"),
        },
        "holder_intelligence":holder,
        "wallet_intelligence":wallet,
    }
