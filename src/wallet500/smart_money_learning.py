from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REGISTRY = "revival-wallet-registry.json"
REVIEW = "engine-learning-review.json"
VERSION = "WALLET500_SMART_MONEY_LEARNING_V1"


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    registry = _load(data / REGISTRY, {})
    if registry.get("version") != "REVIVAL_WALLET_REGISTRY_V1": raise RuntimeError("SMART_MONEY_CANONICAL_REGISTRY_VERSION_INVALID")
    if registry.get("mode") != "RESEARCH_ONLY_TIME_SAFE_SMART_MONEY_REGISTRY": raise RuntimeError("SMART_MONEY_CANONICAL_REGISTRY_MODE_INVALID")
    if registry.get("network") != "solana": raise RuntimeError("SMART_MONEY_CANONICAL_REGISTRY_NETWORK_INVALID")
    if registry.get("production_portfolio_impact") != "NONE" or registry.get("automatic_buy") is not False: raise RuntimeError("SMART_MONEY_CANONICAL_REGISTRY_PRODUCTION_SEPARATION_INVALID")
    truth = registry.get("truth_contract") or {}
    if truth.get("wallet_identity") != "SIGNED_TARGET_TOKEN_OWNER_DELTA_ONLY": raise RuntimeError("SMART_MONEY_WALLET_IDENTITY_INVALID")
    if truth.get("pair_identity") != "EXACT_PAIR_ONLY": raise RuntimeError("SMART_MONEY_PAIR_IDENTITY_INVALID")
    if truth.get("tier_input") != "COMPLETED_PRE_WAKING_VERIFIED_BUY_EXPOSURES_ONLY": raise RuntimeError("SMART_MONEY_TIER_INPUT_INVALID")
    if truth.get("as_of_t0_guard") is not True or truth.get("raw_overlap_never_implies_smart_money") is not True: raise RuntimeError("SMART_MONEY_NO_HINDSIGHT_GUARD_INVALID")
    counts = registry.get("counts") or {}
    total = int(counts.get("wallets_registry") or 0); pending_total = int(counts.get("pending_history") or 0)
    watch_total = int(counts.get("watch") or 0); strong_total = int(counts.get("strong") or 0); elite_total = int(counts.get("elite") or 0)
    detailed = [x for x in (registry.get("wallets") or []) if isinstance(x, dict)]
    queue=[]; tier_counts_detailed={}
    for row in detailed:
        wallet=str(row.get("wallet") or "").strip(); tier=row.get("tier_current") or {}; tier_name=str(tier.get("tier") or "UNKNOWN")
        tier_counts_detailed[tier_name]=tier_counts_detailed.get(tier_name,0)+1
        if not wallet or tier_name != "PENDING_HISTORY": continue
        completed=_number(tier.get("completed_pre_waking_buy_exposures")); distinct_completed=_number(tier.get("distinct_completed_tokens")); observed_distinct=_number(row.get("observed_distinct_tokens")); verified_buys=_number(row.get("verified_buys")); verified_events=_number(row.get("verified_events"))
        priority=completed*1_000_000+distinct_completed*100_000+observed_distinct*1_000+verified_buys*10+verified_events
        queue.append({"wallet":wallet,"tier":tier_name,"reason":tier.get("reason"),"completed_pre_waking_buy_exposures":completed,"distinct_completed_tokens":distinct_completed,"observed_distinct_tokens":observed_distinct,"verified_buys":verified_buys,"verified_events":verified_events,"priority_score_existing_evidence_only":priority,"promotion_forbidden":True,"threshold_change_forbidden":True})
    queue.sort(key=lambda x:(-x["priority_score_existing_evidence_only"],x["wallet"])); queue=queue[:100]
    qualified_total=watch_total+strong_total+elite_total
    result={"version":VERSION,"source_file":REGISTRY,"source_version":registry.get("version"),"source_generated_at":registry.get("generated_at"),"mode":"RESEARCH_ONLY_EXISTING_EVIDENCE_PRIORITY","production_effect":False,"automatic_buy":False,"promotion_allowed":False,"threshold_change_allowed":False,"canonical_counts":{"wallets_registry":total,"pending_history":pending_total,"watch":watch_total,"strong":strong_total,"elite":elite_total,"qualified_total":qualified_total,"completed_eligible_exposures":int(counts.get("completed_eligible_exposures") or 0),"cross_token_wallets":int(counts.get("cross_token_wallets") or 0)},"detailed_rows_published":len(detailed),"detailed_row_tier_counts":tier_counts_detailed,"queue_scope":"ONLY_DETAILED_ROWS_PUBLISHED_BY_CANONICAL_REGISTRY; NOT_THE_FULL_REGISTRY","qualification_queue":queue,"qualification_queue_size":len(queue),"backlog_ratio_full_registry":round(pending_total/max(1,total),6),"truth_contract":{"canonical_registry_only":True,"exact_pair_identity_preserved":True,"as_of_t0_preserved":True,"raw_overlap_never_promotes":True,"queue_is_ordering_only":True,"production_threshold_changes":"FORBIDDEN"}}
    _write(data/"smart-money-learning.json",result); return result


def patch_review(data_dir: str | Path = "data") -> dict:
    data=Path(data_dir); result=build(data); review_path=data/REVIEW; review=_load(review_path,{})
    if not review or review.get("production_effect") is not False or review.get("no_hindsight") is not True: raise RuntimeError("ENGINE_LEARNING_REVIEW_TRUTH_INVALID")
    review["smart_money_quality"]=result; _write(review_path,review); return result


def main() -> None: print(json.dumps(patch_review(),ensure_ascii=False))
if __name__ == "__main__": main()
