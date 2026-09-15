"""No-hindsight replay for Early Revival checkpoints."""
from __future__ import annotations
from typing import Any, Iterable


def replay(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    ordered=sorted(rows,key=lambda r:r["observed_at"])
    if not ordered:return {"status":"NO_EVIDENCE","checkpoints":[]}
    identity=ordered[0]["identity_key"]
    if any(r["identity_key"]!=identity for r in ordered):
        raise ValueError("EARLY_REVIVAL_REPLAY_FAIL_CLOSED_IDENTITY_MIX")
    first=ordered[0]
    out=[]
    for r in ordered:
        if r.get("production_promotion_allowed") is not False or r.get("retroactive_t0_allowed") is not False:
            raise ValueError("EARLY_REVIVAL_REPLAY_FAIL_CLOSED_PRODUCTION_OR_RETROACTIVE")
        out.append({
            "observed_at":r["observed_at"],"price_usd":r["current_price_usd"],
            "move_from_first_pct":r["move_from_first_pct"],
            "crossed_checkpoint_levels_pct":r["crossed_checkpoint_levels_pct"],
            "truth_hash_sha256":r["truth_hash_sha256"],"evidence":r.get("evidence",{}),
        })
    return {"status":"RESEARCH_REPLAY_ONLY","identity_key":identity,
            "first_detected_at":first["observed_at"],"first_detected_price_usd":first["first_price_usd"],
            "checkpoints":out,"may_rewrite_t0":False,"may_promote_production":False}
