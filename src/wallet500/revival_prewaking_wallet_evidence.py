from __future__ import annotations

import json
import os
from pathlib import Path

from . import revival_forensics_v2 as forensic
from . import revival_wallet_evidence as collector

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-prewaking-wallet-evidence-state.json"
LATEST = DATA / "revival-prewaking-wallet-evidence.json"

VERSION = "REVIVAL_PREWAKING_WALLET_EVIDENCE_V1"
MODE = "RESEARCH_ONLY_PREWAKING_EXACT_PAIR_WALLET_EVIDENCE"
MAX_TARGETS = int(os.environ.get("REVIVAL_PREWAKING_MAX_TARGETS", "6"))
MAX_SIGNATURES = int(os.environ.get("REVIVAL_PREWAKING_MAX_SIGNATURES", "60"))
KEEP_SECONDS = int(os.environ.get("REVIVAL_PREWAKING_KEEP_SECONDS", str(7 * 24 * 60 * 60)))


def _n(value: object, default: float = 0.0) -> float:
    try:
        x = float(value)
        if x != x:
            return default
        return x
    except (TypeError, ValueError):
        return default


def _targets() -> list[dict]:
    revival = collector._load(REVIVAL, {})
    if (
        revival.get("network") != "solana"
        or revival.get("no_hindsight") is not True
        or revival.get("production_portfolio_impact") != "NONE"
    ):
        raise RuntimeError("PREWAKING_WALLET_SOURCE_TRUTH_CONTRACT_INVALID")

    rows: list[tuple[tuple[float, float, float, str], dict]] = []
    for coin in revival.get("coins") or []:
        if coin.get("watch_status") != "DEEP_WATCH":
            continue
        if coin.get("market_age_verified") is not True:
            continue
        if int(_n(coin.get("market_age_min_days"), 0)) < forensic.MIN_AGE_DAYS:
            continue
        mint = forensic.token_key(coin)
        pair = forensic.exact_pair(coin)
        if not mint or not pair:
            continue
        rank = (
            _n(coin.get("revival_score_verified")),
            _n(coin.get("dex_pair_volume_24h_usd") or coin.get("volume_24h_usd")),
            _n(coin.get("dex_pair_liquidity_usd")),
            mint,
        )
        rows.append(
            (
                rank,
                {
                    "token_address": mint,
                    "symbol": coin.get("symbol"),
                    "pair_address": pair,
                    "reason": "PRE_WAKING_DEEP_WATCH",
                    "prewaking_rank_score": round(rank[0], 6),
                    "source_revival_generated_at": revival.get("generated_at"),
                },
            )
        )

    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows[:MAX_TARGETS]]


def run() -> dict:
    # Reuse the already-tested signed-token-owner-delta collector while keeping a
    # completely separate state lane. This prevents PRE-WAKING cursor history from
    # competing with or mutating the WAKING/24h evidence state.
    collector.STATE = STATE
    collector.LATEST = LATEST
    collector.MAX_SIGNATURES_PER_TOKEN_PER_RUN = MAX_SIGNATURES
    collector.KEEP_SECONDS = KEEP_SECONDS
    collector._targets = _targets

    payload = collector.run()
    target_map = {row["token_address"]: row for row in _targets()}
    payload["version"] = VERSION
    payload["mode"] = MODE
    payload["lane"] = "PRE_WAKING_DEEP_WATCH"
    payload["selection_policy"] = {
        "status_required": "DEEP_WATCH",
        "market_age_verified_min_days": forensic.MIN_AGE_DAYS,
        "exact_pair_required": True,
        "max_targets": MAX_TARGETS,
        "rank_order": [
            "revival_score_verified_desc",
            "volume_24h_desc",
            "pair_liquidity_desc",
            "token_address_desc_tiebreak",
        ],
        "future_data_used": False,
    }
    payload["collector_limits"] = {
        "max_signatures_per_token_per_run": MAX_SIGNATURES,
        "keep_seconds": KEEP_SECONDS,
    }
    payload["smart_money_bridge"] = {
        "raw_verified_wallet_evidence_connected": True,
        "wallet500_tiers_connected": False,
        "reason": "HISTORICAL_REGISTRY_SCORES_ONLY_AFTER_COMPLETED_OUTCOMES",
    }
    for row in payload.get("tokens") or []:
        target = target_map.get(str(row.get("token_address") or "")) or {}
        row["target_reason"] = target.get("reason")
        row["prewaking_rank_score"] = target.get("prewaking_rank_score")
        row["source_revival_generated_at"] = target.get("source_revival_generated_at")
        # PRE-WAKING monitoring has no event T0 yet. It may become T0-eligible later
        # only if a future WAKING publication occurs after this monitor started.
        (row.setdefault("coverage", {}))[
            "eligible_as_forensics_t0_wallet_evidence"
        ] = False
        row["future_t0_eligibility"] = "POTENTIAL_IF_WAKING_OCCURS_AFTER_MONITOR_START"
    collector._write(LATEST, payload)

    state = collector._load(STATE, {})
    state["version"] = VERSION
    state["mode"] = MODE
    state["lane"] = "PRE_WAKING_DEEP_WATCH"
    state["selection_policy"] = payload["selection_policy"]
    collector._write(STATE, state)
    return payload


def main() -> None:
    payload = run()
    print(
        json.dumps(
            {
                "version": payload.get("version"),
                "targets": payload.get("targets"),
                "selection_policy": payload.get("selection_policy"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
