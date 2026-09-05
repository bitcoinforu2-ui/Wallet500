from __future__ import annotations

import json

from . import revival_holder_tracker as base
from . import holder_truth_provider as provider
from .holder_truth_provider import SOURCE, fetch_holder_truth

MODE = "RESEARCH_ONLY_REVIVAL_HOLDER_TRACKER_V4"


def _provider_note() -> list[str]:
    return [
        "CoinMarketCap and Solscan are equal trusted primary holder-data peers for the exact Solana mint",
        "When both primary peers are available their holder counts are cross-validated; divergence above 20% is quarantined unless exact-mint RPC adjudicates",
        "When both peers agree within tolerance the lower count is used conservatively while both raw provider counts are preserved",
        "CoinMarketCap wallet tags/activity are persisted as independent intelligence and never silently converted into Smart Money truth",
        "Public Solana RPC is an adjudicator/fallback, not a silent replacement for a disagreeing primary provider",
        "A provider/semantics change resets the trusted baseline; RugCheck totals are never used as the growth baseline",
        "Absolute jump above 25% versus the last trusted snapshot is quarantined pending a second trusted observation",
    ]


def _attach_provider_intelligence(row: dict) -> None:
    mint = str(row.get("token_address") or "")
    result = provider.LAST_RESULTS.get(mint) or {}
    if not result:
        return
    row["provider_actual"] = result.get("provider_actual")
    row["provider_counts"] = result.get("provider_counts") or {}
    row["provider_difference_pct"] = result.get("provider_difference_pct")
    row["cross_validation_status"] = result.get("cross_validation_status")
    cmc = result.get("cmc_wallet_intelligence") or {}
    row["cmc_wallet_intelligence"] = {
        "status": cmc.get("status"),
        "wallet_list_verified": cmc.get("wallet_list_verified") is True,
        "wallet_sample_count": int(cmc.get("wallet_sample_count") or 0),
        "tag_counts": cmc.get("tag_counts") or {},
        "wallets": list(cmc.get("wallets") or []),
        "auth_mode": cmc.get("auth_mode"),
    }


def _rewrite_verified_rows(payload: dict) -> None:
    for row in payload.get("coins") or []:
        if not isinstance(row, dict):
            continue
        if row.get("source") == SOURCE:
            row["source_limitations"] = _provider_note()
            row["baseline_relation"] = "FIRST_TRUSTED_EQUAL_PEER_OR_ADJUDICATED_OBSERVATION_FORWARD_ONLY"
        _attach_provider_intelligence(row)


def _rewrite_state(state: dict) -> None:
    state["trusted_holder_source"] = SOURCE
    state["provider_strategy"] = "CMC_AND_SOLSCAN_EQUAL_PRIMARY_PEERS_WITH_RPC_ADJUDICATOR"
    state["provider_cross_validation_tolerance_pct"] = provider.DUAL_PROVIDER_TOLERANCE_PCT
    for row in (state.get("coins") or {}).values():
        if not isinstance(row, dict):
            continue
        if row.get("source") == SOURCE:
            row["source_limitations"] = _provider_note()
            row["baseline_relation"] = "FIRST_TRUSTED_EQUAL_PEER_OR_ADJUDICATED_OBSERVATION_FORWARD_ONLY"
        _attach_provider_intelligence(row)


def build() -> dict:
    # Reuse the forward-only rotation/history engine while replacing its provider
    # with the equal-peer CMC + Solscan cross-validation layer.
    base.SOLSCAN_SOURCE = SOURCE
    base.fetch_holder_truth = fetch_holder_truth

    payload = base.build()
    payload["version"] = 5
    payload["mode"] = MODE
    payload["holder_truth_policy"] = (
        "EXACT_MINT_HOLDER_TRUTH; COINMARKETCAP_AND_SOLSCAN_EQUAL_PRIMARY_PEERS; "
        "CROSS_VALIDATE_WITHIN_20PCT; PUBLIC_SOLANA_RPC_ADJUDICATES_OR_FALLS_BACK; "
        "CMC_WALLET_INTELLIGENCE_PERSISTED_WITHOUT_IMPUTING_SMART_MONEY_TRUTH; "
        "RUGCHECK_TOTAL_QUARANTINED; >25PCT_JUMP_REQUIRES_SECOND_TRUSTED_OBSERVATION"
    )
    payload["provider"] = SOURCE
    payload["provider_strategy"] = "CMC_AND_SOLSCAN_EQUAL_PRIMARY_PEERS_WITH_RPC_ADJUDICATOR"
    payload["provider_cross_validation_tolerance_pct"] = provider.DUAL_PROVIDER_TOLERANCE_PCT
    payload["coinmarketcap_role"] = "PERMANENT_EQUAL_PRIMARY_HOLDER_AND_WALLET_INTELLIGENCE_PROVIDER"
    payload["coinmarketcap_keyless_supported"] = True
    payload["provider_configured"] = True
    payload["provider_usable_this_run"] = bool(payload.get("successful_this_run"))
    _rewrite_verified_rows(payload)
    base.write(base.LATEST, payload)

    state = base.load(base.STATE, {})
    state["version"] = 5
    state["mode"] = MODE
    _rewrite_state(state)
    base.write(base.STATE, state)
    return payload


def main() -> None:
    payload = build()
    print(json.dumps({
        "mode": payload.get("mode"),
        "provider": payload.get("provider"),
        "provider_strategy": payload.get("provider_strategy"),
        "selected_this_run": payload.get("selected_this_run"),
        "successful_this_run": payload.get("successful_this_run"),
        "provider_usable_this_run": payload.get("provider_usable_this_run"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
