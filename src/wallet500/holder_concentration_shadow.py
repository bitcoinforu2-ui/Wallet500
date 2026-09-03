from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .revival_1000 import looks_like_solana_address
from .waking_fallbacks import scan_rugcheck

DATA = Path("data")
HYBRID = DATA / "hybrid-token-profiles.json"
OUT = DATA / "holder-concentration-shadow.json"
STATE = DATA / "holder-concentration-shadow-state.json"
MODE = "RESEARCH_ONLY_HOLDER_CONCENTRATION_SHADOW_V1"
NETWORK = "solana"
DEFAULT_BUDGET = 16


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _n(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _gate_pass(profile: dict) -> bool:
    gates = profile.get("promotion_gates") or {}
    if gates.get("absolute_volume_ready") is True:
        return True
    return _n(gates.get("volume_24h_usd")) >= _n(gates.get("min_ignition_volume_24h_usd"), 10_000.0)


def _exact_pair(profile: dict) -> bool:
    identity = profile.get("identity") or {}
    return identity.get("exact_pair_verified") is True and looks_like_solana_address(str(identity.get("dex_pair_address") or ""))


def priority_reason(profile: dict) -> str:
    status = str(profile.get("status") or "")
    if status == "HYBRID_IGNITION" and _gate_pass(profile):
        return "HYBRID_IGNITION_VOLUME_GATE_PASS"
    if status == "ABNORMAL_ACTIVITY" and _gate_pass(profile):
        return "ABNORMAL_ACTIVITY_VOLUME_GATE_PASS"
    if _gate_pass(profile):
        return "VOLUME_GATE_PASS_RESEARCH"
    return "ROTATION_RESEARCH"


def select_candidates(profiles: list[dict], budget: int) -> list[dict]:
    rows = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        mint = str(profile.get("token_address") or "")
        if not looks_like_solana_address(mint) or not _exact_pair(profile):
            continue
        reason = priority_reason(profile)
        status = str(profile.get("status") or "")
        rank = {
            "HYBRID_IGNITION_VOLUME_GATE_PASS": 0,
            "ABNORMAL_ACTIVITY_VOLUME_GATE_PASS": 1,
            "VOLUME_GATE_PASS_RESEARCH": 2,
            "ROTATION_RESEARCH": 3,
        }[reason]
        rows.append(
            {
                "profile": profile,
                "token_address": mint,
                "priority_reason": reason,
                "rank": rank,
                "score": _n(profile.get("hybrid_score_verified_normalized")),
                "raw": _n(profile.get("hybrid_score_raw")),
                "volume": _n((profile.get("market_context") or {}).get("volume_24h_usd")),
                "status": status,
            }
        )
    rows.sort(key=lambda x: (x["rank"], -x["score"], -x["raw"], -x["volume"], x["token_address"]))
    return rows[: max(1, budget)]


def sanitize_distribution(distribution: dict | None) -> dict | None:
    if not isinstance(distribution, dict):
        return None
    if distribution.get("verified") is not True or distribution.get("contract_match") is not True:
        return None
    source = str(distribution.get("source") or "")
    if not source.startswith("RUGCHECK_EXACT_MINT"):
        return None
    metrics = distribution.get("metrics") or {}
    top1 = metrics.get("top1_pct")
    top10 = metrics.get("top10_pct")
    if top1 is None or top10 is None:
        return None
    return {
        "source": source,
        "observed_at": distribution.get("observed_at"),
        "verified": True,
        "contract_match": True,
        "semantics": "TOP_TOKEN_ACCOUNT_CONCENTRATION_NOT_OWNER_CLUSTER_CONCENTRATION",
        "top_holder_rows": metrics.get("top_holder_rows"),
        "top1_pct": top1,
        "top5_pct": metrics.get("top5_pct"),
        "top10_pct": top10,
        "top20_pct": metrics.get("top20_pct"),
        "concentration_risk_score": distribution.get("risk_score"),
        "signals": list(distribution.get("signals") or []),
        "limitations": list(distribution.get("limitations") or []),
        "positive_signal_eligible": False,
        "hybrid_score_impact": "NONE",
    }


def sanitize_holder_shadow(holders: dict | None) -> dict | None:
    if not isinstance(holders, dict) or holders.get("available") is not True or holders.get("verified") is not True:
        return None
    if str(holders.get("source") or "") != "RUGCHECK_EXACT_MINT_PUBLIC_REPORT":
        return None
    metrics = holders.get("metrics") or {}
    count = metrics.get("holder_count")
    if count is None:
        return None
    return {
        "source": holders.get("source"),
        "observed_at": holders.get("observed_at"),
        "holder_count_shadow": int(count),
        "previous_holder_count_shadow": metrics.get("previous_holder_count"),
        "holder_change_since_previous_scan_pct_shadow": metrics.get("holder_change_pct"),
        "semantics": "THIRD_PARTY_CACHED_HOLDER_COUNT_SHADOW_NOT_TRUSTED_GROWTH",
        "growth_signal_eligible": False,
        "hybrid_score_impact": "NONE",
        "limitations": list(holders.get("limitations") or []),
    }


def _rugcheck_state(old: dict) -> dict:
    count = old.get("holder_count_shadow")
    observed = old.get("holder_shadow_observed_at") or old.get("observed_at")
    out = {}
    if count is not None:
        out["rugcheck_holder_count"] = int(count)
    if observed:
        out["rugcheck_observed_at"] = observed
    return out


def build() -> dict:
    hybrid = load(HYBRID, {})
    if hybrid.get("mode") != "RESEARCH_ONLY_HYBRID_TOKEN_PROFILE_V1" or hybrid.get("contract") != "HYBRID_TOKEN_PROFILE_V1":
        raise SystemExit("HOLDER_CONCENTRATION_HYBRID_CONTRACT_INVALID")
    if hybrid.get("network") != NETWORK or hybrid.get("production_portfolio_impact") != "NONE":
        raise SystemExit("HOLDER_CONCENTRATION_HYBRID_NETWORK_INVALID")

    budget = max(1, min(60, int(os.getenv("HOLDER_CONCENTRATION_BUDGET", str(DEFAULT_BUDGET)))))
    selected = select_candidates(list(hybrid.get("profiles") or []), budget)
    previous = load(STATE, {"version": 1, "rows": {}})
    rows = dict(previous.get("rows") or {})
    observed_at = now_iso()
    scan_status = []
    verified_this_run = 0
    holder_shadow_this_run = 0

    for item in selected:
        profile = item["profile"]
        mint = item["token_address"]
        old = dict(rows.get(mint) or {})
        holders_raw, distribution, _state, status = scan_rugcheck(mint, _rugcheck_state(old), observed_at)
        safe = sanitize_distribution(distribution)
        holder_shadow = sanitize_holder_shadow(holders_raw)
        if holder_shadow is not None:
            holder_shadow_this_run += 1
        scan_status.append(
            {
                "token_address": mint,
                "symbol": profile.get("symbol"),
                "priority_reason": item["priority_reason"],
                "status": status.get("status"),
                "verified_concentration": safe is not None,
                "holder_count_shadow_available": holder_shadow is not None,
            }
        )
        if safe is None and holder_shadow is None:
            if old:
                old["latest_scan_status"] = status.get("status") or "UNAVAILABLE"
                old["latest_scan_attempt_at"] = observed_at
                old["retained_from_previous_verified_observation"] = True
                rows[mint] = old
            continue

        base = {
            **old,
            "network": NETWORK,
            "token_address": mint,
            "symbol": profile.get("symbol"),
            "name": profile.get("name"),
            "hybrid_status_at_scan": profile.get("status"),
            "hybrid_score_at_scan": profile.get("hybrid_score_verified_normalized"),
            "market_volume_24h_usd_at_scan": (profile.get("market_context") or {}).get("volume_24h_usd"),
            "priority_reason": item["priority_reason"],
            "latest_scan_status": status.get("status") or "OK",
            "latest_scan_attempt_at": observed_at,
            "retained_from_previous_verified_observation": safe is None,
        }
        if holder_shadow is not None:
            base.update(holder_shadow)
            base["holder_shadow_observed_at"] = observed_at
        if safe is not None:
            verified_this_run += 1
            base.update(safe)
            base["retained_from_previous_verified_observation"] = False
        rows[mint] = base

    active_mints = {str(p.get("token_address") or "") for p in (hybrid.get("profiles") or [])}
    rows = {mint: row for mint, row in rows.items() if mint in active_mints}
    ordered = sorted(
        rows.values(),
        key=lambda x: (
            0 if x.get("priority_reason") == "HYBRID_IGNITION_VOLUME_GATE_PASS" else 1,
            -_n(x.get("hybrid_score_at_scan")),
            -_n(x.get("concentration_risk_score")),
            str(x.get("symbol") or ""),
        ),
    )
    total_verified = sum(x.get("verified") is True for x in ordered)
    retained = sum(x.get("retained_from_previous_verified_observation") is True for x in ordered)
    holder_shadow_total = sum(x.get("holder_count_shadow") is not None for x in ordered)
    payload = {
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": observed_at,
        "hybrid_source_generated_at": hybrid.get("source_generated_at"),
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "truth_rules": [
            "exact Solana mint and exact verified pair are required before scanning",
            "RugCheck top-holder rows are token-account concentration, not verified owner-cluster concentration",
            "LP, burn, CEX and market-maker exclusions are not inferred",
            "concentration may add research risk but is never an independent positive signal family",
            "RugCheck holder total is displayed only as a cached third-party shadow and is not trusted 1h/6h/24h/7d growth",
            "holder-count shadow changes never change Hybrid score or create a positive signal family",
            "missing scans retain the last verified concentration row but are explicitly marked retained",
        ],
        "budget": budget,
        "selected_this_run": len(selected),
        "verified_this_run": verified_this_run,
        "holder_shadow_this_run": holder_shadow_this_run,
        "holder_shadow_total_rows": holder_shadow_total,
        "retained_verified_rows": retained,
        "total_verified_rows": total_verified,
        "scan_status": scan_status,
        "rows": ordered,
    }
    state_payload = {
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "updated_at": observed_at,
        "rows": {str(x.get("token_address")): x for x in ordered},
    }
    write(OUT, payload)
    write(STATE, state_payload)
    return payload


def main() -> None:
    payload = build()
    print(
        json.dumps(
            {
                "mode": payload.get("mode"),
                "selected": payload.get("selected_this_run"),
                "verified_concentration": payload.get("verified_this_run"),
                "holder_shadow": payload.get("holder_shadow_this_run"),
                "total_verified": payload.get("total_verified_rows"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
