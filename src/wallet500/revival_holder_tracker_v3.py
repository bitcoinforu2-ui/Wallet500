from __future__ import annotations

import json

from . import revival_holder_tracker as base
from .holder_truth_provider import SOURCE, fetch_holder_truth

MODE = "RESEARCH_ONLY_REVIVAL_HOLDER_TRACKER_V3"


def _rewrite_verified_rows(payload: dict) -> None:
    for row in payload.get("coins") or []:
        if not isinstance(row, dict) or row.get("source") != SOURCE:
            continue
        row["source_limitations"] = [
            "Holder count is a forward-only unique positive-balance owner series for the exact mint",
            "Solscan is preferred when configured; otherwise a public Solana RPC exact-mint owner count is used",
            "A provider or semantics change resets the trusted baseline; RugCheck totals are never used as the growth baseline",
            "Absolute jump above 25% versus the last trusted snapshot is quarantined pending a second trusted observation",
        ]
        row["baseline_relation"] = "FIRST_TRUSTED_UNIQUE_OWNER_OBSERVATION_FORWARD_ONLY"


def _rewrite_state(state: dict) -> None:
    state["trusted_holder_source"] = SOURCE
    state["provider_strategy"] = "SOLSCAN_PREFERRED_PUBLIC_SOLANA_RPC_FALLBACK"
    for row in (state.get("coins") or {}).values():
        if not isinstance(row, dict) or row.get("source") != SOURCE:
            continue
        row["source_limitations"] = [
            "Holder count is a forward-only unique positive-balance owner series for the exact mint",
            "Solscan is preferred when configured; otherwise a public Solana RPC exact-mint owner count is used",
            "A provider or semantics change resets the trusted baseline; RugCheck totals are never used as the growth baseline",
            "Absolute jump above 25% versus the last trusted snapshot is quarantined pending a second trusted observation",
        ]
        row["baseline_relation"] = "FIRST_TRUSTED_UNIQUE_OWNER_OBSERVATION_FORWARD_ONLY"


def build() -> dict:
    # Reuse the battle-tested rotation/history engine, but replace its single-provider
    # holder truth source with a semantically equivalent verified provider chain.
    base.SOLSCAN_SOURCE = SOURCE
    base.fetch_holder_truth = fetch_holder_truth

    payload = base.build()
    payload["version"] = 4
    payload["mode"] = MODE
    payload["holder_truth_policy"] = (
        "UNIQUE_POSITIVE_OWNER_COUNT_EXACT_MINT; SOLSCAN_PREFERRED; "
        "PUBLIC_SOLANA_RPC_FALLBACK; RUGCHECK_TOTAL_QUARANTINED; "
        ">25PCT_JUMP_REQUIRES_SECOND_TRUSTED_OBSERVATION"
    )
    payload["provider"] = SOURCE
    payload["provider_strategy"] = "SOLSCAN_PREFERRED_PUBLIC_SOLANA_RPC_FALLBACK"
    payload["provider_configured"] = True
    payload["provider_usable_this_run"] = bool(payload.get("successful_this_run"))
    _rewrite_verified_rows(payload)
    base.write(base.LATEST, payload)

    state = base.load(base.STATE, {})
    state["version"] = 4
    state["mode"] = MODE
    _rewrite_state(state)
    base.write(base.STATE, state)
    return payload


def main() -> None:
    payload = build()
    print(json.dumps({
        "mode": payload.get("mode"),
        "provider": payload.get("provider"),
        "selected_this_run": payload.get("selected_this_run"),
        "successful_this_run": payload.get("successful_this_run"),
        "provider_usable_this_run": payload.get("provider_usable_this_run"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
