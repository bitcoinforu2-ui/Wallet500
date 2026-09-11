from __future__ import annotations

import json
import time
from pathlib import Path

from . import cyberleek_wallet_flow as rpcbase
from . import revival_prewaking_wallet_evidence as pre
from . import revival_prewaking_wallet_retention as retention
from . import revival_wallet_evidence as collector

WALLET_INSIGHT = Path("data/wallet-insight-review.json")
INSIGHT_PRIORITY_SLOTS = 8
INSIGHT_ALLOWED_STATUSES = {"EVIDENCE_READY", "VERIFIED_WATCH"}
INSIGHT_ALLOWED_CLASSIFICATIONS = {"DATA_PIPELINE_BOTTLENECK", "COVERAGE_TO_ACCUMULATION_GAP"}


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _insight_priority_candidates(previous: dict | None = None, *, slots: int = INSIGHT_PRIORITY_SLOTS) -> list[dict]:
    """Schedule current exact-pair coverage gaps for forward-only deep wallet monitoring only."""
    insight = _load_json(WALLET_INSIGHT)
    if (
        insight.get("version") != "WALLET500_WALLET_INSIGHT_REVIEW_V1"
        or insight.get("mode") != "RESEARCH_ONLY_EXACT_PAIR_WALLET_BOTTLENECK_REVIEW"
        or insight.get("production_effect") is not False
        or insight.get("automatic_buy") is not False
        or insight.get("no_hindsight") is not True
    ):
        return []
    truth = insight.get("truth_contract") or {}
    if (
        truth.get("exact_pair_required") is not True
        or truth.get("coverage_probe_never_counts_as_accumulation_alpha") is not True
        or truth.get("historical_coverage_never_counts_as_current_positive") is not True
        or truth.get("promotion_allowed") is not False
    ):
        return []

    prior = {
        str(row.get("token_address") or "")
        for row in ((previous or {}).get("tokens") or [])
        if isinstance(row, dict) and isinstance(row.get("wallet_insight_bridge"), dict)
    }
    eligible: list[dict] = []
    for row in insight.get("rows") or []:
        if not isinstance(row, dict) or row.get("candidate_status") not in INSIGHT_ALLOWED_STATUSES:
            continue
        if row.get("classification") not in INSIGHT_ALLOWED_CLASSIFICATIONS:
            continue
        metrics = row.get("metrics") or {}
        if metrics.get("current_probe_verified") is not True or metrics.get("coverage_degraded") is True:
            continue
        parts = str(row.get("identity") or "").split("|")
        if len(parts) != 3 or parts[0] != "solana" or not all(parts):
            continue
        _, mint, pair = parts
        eligible.append({
            "token_address": mint,
            "symbol": row.get("symbol"),
            "pair_address": pair,
            "reason": "PRE_WAKING_DEEP_WATCH",
            "activity_tier": "CURRENT_EXACT_PAIR_COVERAGE_GAP",
            "activity_rank": 3,
            "exact_pair_liquidity_usd": 0.0,
            "exact_pair_volume_24h_usd": 0.0,
            "prewaking_rank_score": 1000.0 if row.get("candidate_status") == "EVIDENCE_READY" else 900.0,
            "source_revival_generated_at": None,
            "source_wallet_insight_generated_at": insight.get("generated_at"),
            "scheduling_only": True,
        })
    eligible.sort(key=lambda r: (r["token_address"] in prior, -float(r["prewaking_rank_score"]), r["token_address"]))
    return eligible[: max(0, int(slots))]


def _install_insight_bridge() -> dict:
    previous = collector._load(pre.LATEST, {})
    original = pre._ranked_candidates
    priority = _insight_priority_candidates(previous)

    def bridged(revival: dict) -> list[dict]:
        normal = original(revival)
        priority_tokens = {row["token_address"] for row in priority}
        return priority + [row for row in normal if row.get("token_address") not in priority_tokens]

    pre._ranked_candidates = bridged
    return {"eligible_selected": len(priority), "selected_tokens": [row["token_address"] for row in priority]}


def _fetch_transactions_resilient(rows: list[dict], mint: str) -> tuple[list[dict], int]:
    events: list[dict] = []
    unresolved = 0
    valid = [row for row in rows if row.get("signature")]
    read_failures = 0
    for index, row in enumerate(valid):
        signature = str(row.get("signature") or "")
        try:
            tx = rpcbase._rpc("getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
        except Exception:
            tx = None
            read_failures += 1
        if not isinstance(tx, dict):
            unresolved += 1
        elif (tx.get("meta") or {}).get("err") is not None:
            pass
        else:
            deltas = rpcbase._mint_owner_deltas(tx, mint)
            if deltas:
                event = collector._extract_trade(tx, signature, mint, row.get("blockTime"))
                if event:
                    events.append(event)
                else:
                    unresolved += 1
        if index + 1 < len(valid):
            time.sleep(0.035)
    if valid and read_failures == len(valid):
        raise RuntimeError("RPC_GETTRANSACTION_ALL_READS_FAILED")
    return events, unresolved


def run() -> dict:
    collector._fetch_transactions = _fetch_transactions_resilient
    bridge = _install_insight_bridge()
    payload = pre.run()
    bridge_tokens = set(bridge["selected_tokens"])
    for row in payload.get("tokens") or []:
        if str(row.get("token_address") or "") in bridge_tokens:
            row["wallet_insight_bridge"] = {
                "source_reason": "CURRENT_EXACT_PAIR_COVERAGE_WITHOUT_DEEP_WALLET_ROW",
                "scheduling_only": True,
                "current_exact_pair_coverage_required": True,
                "production_effect": False,
                "automatic_buy": False,
                "no_hindsight": True,
            }

    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth.update({
        "pair_signatures_without_target_mint_delta_excluded_from_resolution_denominator": True,
        "target_mint_touch_without_signed_owner_remains_unresolved": True,
        "wallet_insight_priority_is_scheduling_only": True,
        "wallet_insight_priority_requires_current_exact_pair_coverage": True,
        "wallet_insight_priority_never_counts_as_accumulation_alpha": True,
        "wallet_insight_priority_never_changes_production_thresholds": True,
        "wallet_insight_priority_uses_no_future_outcomes": True,
    })
    payload["truth_contract"] = truth
    payload["resolution_policy"] = "EXACT_MINT_TOUCH_DENOMINATOR_V2"
    payload.setdefault("selection_policy", {})["wallet_insight_priority_bridge"] = {
        "enabled": True,
        "slots": INSIGHT_PRIORITY_SLOTS,
        "eligible_selected": bridge["eligible_selected"],
        "selected_tokens": bridge["selected_tokens"],
        "allowed_candidate_statuses": sorted(INSIGHT_ALLOWED_STATUSES),
        "allowed_classifications": sorted(INSIGHT_ALLOWED_CLASSIFICATIONS),
        "current_exact_pair_coverage_required": True,
        "one_cycle_rotation": True,
        "scheduling_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
    }
    collector._write(pre.LATEST, payload)
    return retention.retain_fresh_rotation_evidence(payload)


def main() -> None:
    payload = run()
    print(json.dumps({"version": payload.get("version"), "targets": payload.get("targets"), "published_wallet_evidence_rows": payload.get("published_wallet_evidence_rows"), "resolution_policy": payload.get("resolution_policy"), "selection_policy": payload.get("selection_policy"), "rotation_retention": payload.get("rotation_retention")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
