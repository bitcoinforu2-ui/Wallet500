from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone


def _embedded_holder(c: dict) -> dict:
    explicit=c.get("holder_intelligence")
    if isinstance(explicit,dict):
        return deepcopy(explicit)
    verified=c.get("liquidity_drain_holder_cluster_verified")
    return {
        "status":"VERIFIED" if verified is True else "NO_VERIFIED_HOLDER_DATA",
        "verified": verified is True,
        "trust_score":c.get("holder_cluster_trust_score"),
        "insider_linked_supply_pct":c.get("liquidity_drain_insider_linked_supply_pct"),
        "top10_supply_pct":c.get("liquidity_drain_top10_supply_pct"),
        "risk_flags":deepcopy(c.get("liquidity_drain_signals") or (["HOLDER_DATA_UNAVAILABLE"] if verified is not True else [])),
    }


def _embedded_wallet(c: dict) -> dict:
    explicit=c.get("wallet_intelligence")
    if isinstance(explicit,dict):
        return deepcopy(explicit)
    return {
        "status":c.get("wallet_forensics_status") or "NO_VERIFIED_WALLET_DATA",
        "verified_wallet_count":c.get("verified_wallet_count"),
    }


def _security(c: dict) -> dict:
    explicit=c.get("security") or c.get("lp_security") or c.get("security_intelligence")
    if isinstance(explicit,dict):
        return deepcopy(explicit)
    lp=c.get("lp_removal_protection_verified")
    return {
        "status":"VERIFIED" if lp is True else "LP_REMOVAL_PROTECTION_NOT_VERIFIED",
        "verified":lp is True,
        "lp_removal_protection_verified":lp is True,
        "production_risk_gate":c.get("production_risk_gate"),
        "production_risk_blocked":c.get("production_risk_blocked"),
        "risk_reasons":deepcopy(c.get("production_risk_reasons") or []),
    }


def _execution(c: dict) -> dict:
    explicit=c.get("execution") or c.get("exact_pair_execution")
    if isinstance(explicit,dict):
        return deepcopy(explicit)
    verified=(c.get("entry_quote_verified") is True or c.get("exact_pair_quote_verified") is True)
    return {
        "status":c.get("quote_status") or ("VERIFIED" if verified else "NO_VERIFIED_EXACT_PAIR_ENTRY_QUOTE"),
        "entry_quote_verified":verified,
        "exact_pair_quote_verified":verified,
        "quote_source":c.get("quote_source"),
        "quoted_at":c.get("quoted_at"),
    }


def build_evidence_snapshot(candidate: dict, holder_intel: dict | None = None, wallet_intel: dict | None = None, observed_at: str | None = None) -> dict:
    """Build a frozen append-only evidence record from data available at discovery only."""
    c=deepcopy(candidate or {})
    ts=observed_at or c.get("observed_at") or c.get("qualified_at") or datetime.now(timezone.utc).isoformat()
    holder=deepcopy(holder_intel) if isinstance(holder_intel,dict) else _embedded_holder(c)
    wallet=deepcopy(wallet_intel) if isinstance(wallet_intel,dict) else _embedded_wallet(c)
    return {
        "schema_version":2,
        "evidence_policy":"IMMUTABLE_DISCOVERY_EVIDENCE_NO_HINDSIGHT",
        "observed_at":ts,
        "captured_at":datetime.now(timezone.utc).isoformat(),
        "identity":{
            "chain":c.get("chain"),
            "token":c.get("token") or c.get("mint"),
            "pair_address":c.get("pair_address"),
            "locked_pair_address":c.get("locked_pair_address") or c.get("pair_address"),
            "pair_identity_locked":bool(c.get("pair_identity_locked", bool(c.get("pair_address")))),
            "dex":c.get("dex"),
        },
        "market":{
            "price_usd":c.get("price_usd"),
            "liquidity_usd":c.get("liquidity_usd"),
            "liquidity_base":c.get("liquidity_base"),
            "liquidity_quote":c.get("liquidity_quote"),
            "liquidity_composition_present":c.get("liquidity_composition_present"),
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
            "live_survival_gate":c.get("live_survival_gate"),
            "fresh_solana_gate":c.get("fresh_solana_gate"),
        },
        "holder_intelligence":holder,
        "wallet_intelligence":wallet,
        "security":_security(c),
        "execution":_execution(c),
    }
