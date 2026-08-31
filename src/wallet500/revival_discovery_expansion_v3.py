from __future__ import annotations

import json

from wallet500.revival_absorption_signal import compute_absorption_proxy
from wallet500.revival_discovery_expansion import (
    LATEST,
    MIN_AGE_DAYS,
    discovery_asset_allowed,
    fetch_pairs_for_tokens,
    load_known_solana_tokens,
    n,
    pair_age_days,
    to_candidate,
)

MODE = "RESEARCH_ONLY_REVIVAL_SOLANA_EXPANDED_V6"
CANDIDATE_TYPE = "SELL_COUNT_ABSORPTION_CANDIDATE_PROXY"


def structural_candidate(flow: dict) -> bool:
    c = flow.get("criteria") or {}
    return all([
        c.get("sell_count_gt_buy_count") is True,
        c.get("sell_buy_count_ratio_le_2") is True,
        c.get("liquidity_ge_50k") is True,
        c.get("volume_24h_ge_10k") is True,
        c.get("txns_24h_ge_40") is True,
        c.get("volume_to_liquidity_ge_5pct") is True,
    ])


def main() -> None:
    if not LATEST.exists():
        raise SystemExit("REVIVAL_EXPANSION_LATEST_MISSING")
    payload = json.loads(LATEST.read_text())
    coins = payload.get("coins") or []
    base_count = len(coins)
    existing = {str(x.get("token_address") or "") for x in coins}
    known = load_known_solana_tokens()
    scan_tokens = [t for t in known if t not in existing]
    pair_map, failures = fetch_pairs_for_tokens(scan_tokens)

    added = []
    strict_added = 0
    candidate_added = 0
    rejected_age = 0
    rejected_asset = 0

    for token in scan_tokens:
        pair = pair_map.get(token)
        if not pair:
            continue
        age = pair_age_days(pair)
        if age is None or age < MIN_AGE_DAYS:
            rejected_age += 1
            continue
        if not discovery_asset_allowed(token, pair):
            rejected_asset += 1
            continue

        flow = compute_absorption_proxy(
            {"change_24h_pct": n((pair.get("priceChange") or {}).get("h24"))},
            pair,
        )
        is_strict = flow.get("signal") is True
        is_candidate = structural_candidate(flow)
        if not (is_strict or is_candidate):
            continue

        row = to_candidate(token, pair, flow, base_count + len(added) + 1)
        row["absorption_candidate_proxy"] = True
        row["absorption_candidate_type"] = CANDIDATE_TYPE
        row["absorption_candidate_missing_strict_conditions"] = [
            key for key, value in (flow.get("criteria") or {}).items() if value is not True
        ]
        if is_strict:
            strict_added += 1
        else:
            candidate_added += 1
            row["watch_status"] = "ABSORPTION_CANDIDATE_DISCOVERY_EXPANSION"
            row["watch_triggers"] = [CANDIDATE_TYPE, "DISCOVERY_STATE_EXPANSION"]
            row["revival_score_reasons"] = ["DISCOVERY_EXPANSION_PRE_MOVE_ABSORPTION_CANDIDATE"]
        added.append(row)

    coins.extend(added)
    payload["coins"] = coins
    payload["mode"] = MODE
    payload["candidate_cap"] = None
    payload["universe_definition"] = (
        "COINGECKO SOLANA-ONLY BASE PLUS ALL CURRENT STRICT OR PRE-MOVE ABSORPTION-CANDIDATE TOKENS FROM THE PERSISTED SOLANA REVIVAL DISCOVERY STATE; NO FIXED TOTAL CANDIDATE CAP"
    )
    payload["discovery_expansion_contract"] = {
        "version": "REVIVAL_DISCOVERY_ABSORPTION_EXPANSION_V2",
        "research_only": True,
        "production_portfolio_impact": "NONE",
        "known_solana_tokens": len(known),
        "tokens_scanned_outside_base": len(scan_tokens),
        "minimum_pair_age_days": MIN_AGE_DAYS,
        "strict_signal": "ALL SELL-COUNT ABSORPTION PROXY CRITERIA INCLUDING POSITIVE_24H_PRICE",
        "candidate_signal": "SAME STRUCTURAL CRITERIA EXCEPT POSITIVE_24H_PRICE IS NOT REQUIRED",
        "candidate_purpose": "PRE_MOVE_OBSERVATION_ONLY",
        "cross_platform_status": "UNKNOWN_FOR_DISCOVERY_EXPANSION; PRE_ALPHA_FORBIDDEN",
        "fixed_candidate_cap": None,
    }

    counts = payload.setdefault("counts", {})
    counts["base_sol_only_universe"] = base_count
    counts["discovery_state_solana_known"] = len(known)
    counts["discovery_state_outside_base_scanned"] = len(scan_tokens)
    counts["absorption_discovery_strict_added"] = strict_added
    counts["absorption_discovery_candidate_added"] = candidate_added
    counts["absorption_discovery_expansion_added"] = len(added)
    counts["discovery_expansion_rejected_age"] = rejected_age
    counts["discovery_expansion_rejected_asset"] = rejected_asset
    counts["universe"] = len(coins)
    counts["dex_verified_pairs"] = sum(1 for x in coins if x.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR")
    counts["absorption_proxy_watch"] = sum(1 for x in coins if (x.get("order_flow_absorption") or {}).get("signal") is True)
    counts["absorption_candidate_proxy_watch"] = sum(1 for x in coins if x.get("absorption_candidate_proxy") is True)
    counts["absorption_proxy_outside_core"] = sum(
        1 for x in coins
        if (x.get("order_flow_absorption") or {}).get("signal") is True
        and x.get("watch_status") in {"ABSORPTION_WATCH", "ABSORPTION_WATCH_DISCOVERY_EXPANSION"}
    )

    payload["source"] = str(payload.get("source") or "") + "+revival_discovery_state_pre_move_absorption_candidates"
    if failures:
        payload.setdefault("failures", []).append({
            "failure_code": "DISCOVERY_EXPANSION_PARTIAL_DEX_BATCH_FAILURE",
            "severity": "NON_BLOCKING_RESEARCH_LAYER",
            "blocks_production": False,
            "batches": failures,
        })
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({
        "known_solana": len(known),
        "outside_base_scanned": len(scan_tokens),
        "strict_added": strict_added,
        "pre_move_candidates_added": candidate_added,
        "combined_universe": len(coins),
        "batch_failures": len(failures),
    }))


if __name__ == "__main__":
    main()
