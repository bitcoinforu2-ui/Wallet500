from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .catalyst_dna import run_catalyst_dna
from .cex_revival import run_cex_revival
from .config import Settings
from .established_hour_census import run_established_hour_census
from .multichain_veteran_revival import run as run_multichain_veteran_revival
from .social_catalyst import run_social_catalyst
from .time_machine import run_time_machine


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _stage(name, fn):
    started = time.perf_counter()
    print(f"[orchestrator] START {name}", flush=True)
    try:
        result = fn()
    except Exception:
        print(f"[orchestrator] FAIL {name} after {time.perf_counter()-started:.2f}s", flush=True)
        raise
    print(f"[orchestrator] DONE {name} in {time.perf_counter()-started:.2f}s", flush=True)
    return result


def _cex(out: Path, now: str) -> dict:
    if os.getenv("WALLET500_CEX_PRECOMPUTED", "").strip().lower() in {"1", "true", "yes"}:
        existing = _load(out / "cex-revival-radar.json", {})
        if existing:
            print("[orchestrator] USING precomputed exact-identity CEX fast lane", flush=True)
            return existing
    return _stage("cex_revival", lambda: run_cex_revival(out, now))


def run():
    cfg = Settings()
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # Production discovery is 100% veteran-token revival. The CEX fast lane may
    # already have refreshed this file before the slower learning stages begin.
    cex = _cex(out, now)
    # Core multi-chain expansion is deliberately research-only. It applies the
    # 180d veteran, exact-token/pair, $50k liquidity and activity gates before a
    # DNA watch can exist, but it cannot create a BUY or production candidate.
    multichain = _stage("multichain_veteran_revival", lambda: run_multichain_veteran_revival(out, now))
    census = _stage("established_hour_census", lambda: run_established_hour_census(out, now, cex))
    dna = _stage("catalyst_dna", lambda: run_catalyst_dna(out, now))
    tm = _stage("time_machine", lambda: run_time_machine(out, now))
    try:
        social = _stage("social_catalyst", lambda: run_social_catalyst(out, now))
        social_error = None
    except Exception as e:
        social = {"status": "DEGRADED", "events": 0, "new_events": 0, "candidates": 0, "influencers": 0, "errors": 1}
        social_error = f"{type(e).__name__}: {e}"[:500]

    completed_at = datetime.now(timezone.utc).isoformat()
    summary_path = out / "run-summary.json"
    summary = _load(summary_path, {})
    summary["intelligence_policy"] = {
        "mode": "VETERAN_COIN_REVIVAL_ONLY",
        "production_primary": "ESTABLISHED_TOKEN_REVIVAL",
        "target_attention_pct": {"old_coin_revival": 100, "new_token_research": 0},
        "minimum_verified_market_age_days": 180,
        "unknown_or_ambiguous_age": "REJECT_OR_PENDING_NOT_ACTIONABLE",
        "new_token_lane": "DISABLED",
        "minimum_exchange_confirmations": 2,
        "strong_exchange_confirmations": 4,
        "early_meaning": "EARLY_IN_REVIVAL_NOT_NEW_TOKEN",
        "core_multichain_research": ["solana", "ethereum", "bsc", "arbitrum", "base"],
    }
    summary["lane_health"] = {
        "old_coin_revival": "HEALTHY" if cex.get("healthy_sources", 0) >= 2 and cex.get("contracts_seen", 0) > 0 else "DEGRADED",
        "multichain_veteran_research": "HEALTHY" if multichain.get("snapshots", 0) > 0 else "DEGRADED",
        "new_token_lab": "DISABLED_POLICY",
        "social_catalyst": social.get("status"),
        "social_error": social_error,
    }
    summary["cex"] = {
        "healthy_sources": cex.get("healthy_sources", 0),
        "requested_sources": len(cex.get("requested_sources", [])),
        "contracts_seen": cex.get("contracts_seen", 0),
        "symbols_seen": cex.get("symbols_seen", 0),
        "alerts": cex.get("alerts_count", 0),
        "errors": len(cex.get("errors", [])),
        "identity_counts": cex.get("identity_counts", {}),
    }
    summary["multichain_veteran_research"] = {
        "mode": multichain.get("mode"),
        "core_chains": multichain.get("core_chains", []),
        "discovered": multichain.get("discovered", 0),
        "snapshots": multichain.get("snapshots", 0),
        "veteran_gate_pass": multichain.get("veteran_gate_pass", 0),
        "dna_watch_count": multichain.get("dna_watch_count", 0),
        "late_move_count": multichain.get("late_move_count", 0),
        "counts_by_chain": multichain.get("counts_by_chain", {}),
        "production_portfolio_impact": "NONE",
    }
    summary["established_hour_census"] = {
        "started_at": census.get("started_at"),
        "target_end_at": census.get("target_end_at"),
        "completed": census.get("completed", False),
        **(census.get("summary") or {}),
    }
    summary["catalyst_dna"] = {
        "profiles": dna.get("profiles_count", 0),
        "market_profiles": dna.get("market_profiles_count", dna.get("profiles_count", 0)),
        "unique_symbols": dna.get("unique_symbols_count", 0),
        "consensus_symbols": len(dna.get("consensus_profiles", []) or []),
        "source_attribution_sources": len(dna.get("source_attribution", {})),
        "archetypes": len(dna.get("archetype_frequency", {})),
        "counting_rule": dna.get("counting_rule"),
    }
    summary["time_machine"] = {
        "patterns_tested": tm.get("patterns_tested", 0),
        "source_forward_stats": len(tm.get("source_forward_hit_rates", {})),
        "method": tm.get("method"),
    }
    summary["social_catalyst"] = {
        "status": social.get("status"),
        "events": social.get("events", 0),
        "new_events": social.get("new_events", 0),
        "candidates": social.get("candidates", 0),
        "observed_influencers": social.get("influencers", 0),
        "errors": social.get("errors", 0),
        "rule": "social momentum never overrides exact identity, age, liquidity, security, holder-cluster or manipulation gates",
    }
    summary["cex_revival_alerts"] = cex.get("alerts_count", 0)
    summary["updated_at"] = completed_at
    summary["mode"] = "VETERAN_COIN_REVIVAL_ONLY_180D_MIN+CEX_EXACT_ID+CEX_SPOT_RESEARCH+CORE_MULTICHAIN_RESEARCH+CATALYST_DNA+TIME_MACHINE+SOCIAL"
    _write(summary_path, summary)

    # Keep the old artifact path explicit so no dashboard can silently interpret
    # stale legacy data as an active new-token lane.
    new_lab = {
        "version": 5,
        "updated_at": completed_at,
        "lane": "NEW_TOKEN_LAB",
        "production_status": "DISABLED_POLICY",
        "lane_health": "DISABLED_POLICY",
        "attention_budget_pct": 0,
        "purpose": "disabled: Wallet500 production and discovery policy is 100% veteran-token revival",
        "minimum_veteran_market_age_days": 180,
        "note": "New-token discovery/ranking is disabled. Historical files may remain only as legacy learning evidence.",
    }
    _write(out / "new-token-lab.json", new_lab)

    learning = {
        "version": 10,
        "updated_at": completed_at,
        "objective": "optimize early revival detection in verified veteran tokens with exact identity and no hindsight",
        "attention_budget_pct": {"old_coin_revival": 100, "new_token_research": 0},
        "rules": [
            "only verified veteran coins >=180d enter the revival discovery policy",
            "EARLY means early in a revival, never a new launch",
            "exact contract/mint and exact DEX pair are required before actionable research status",
            "multi-chain research is never production authority by itself",
            "CEX spot evidence can confirm a DEX candidate only through exact registry chain+contract identity",
            "social popularity never overrides risk gates",
            "case studies are never counted as Wallet500 calls",
            "never invent historical catalysts, mentions, entry prices or baselines",
            "no hindsight feature leakage",
            "retain failures and dumps",
            "version threshold changes",
        ],
        "current_run": {
            "cex_revival_alerts": cex.get("alerts_count", 0),
            "cex_healthy_sources": cex.get("healthy_sources", 0),
            "cex_symbols_seen": cex.get("symbols_seen", 0),
            "cex_identity_counts": cex.get("identity_counts", {}),
            "multichain_discovered": multichain.get("discovered", 0),
            "multichain_snapshots": multichain.get("snapshots", 0),
            "multichain_veteran_gate_pass": multichain.get("veteran_gate_pass", 0),
            "multichain_dna_watch": multichain.get("dna_watch_count", 0),
            "multichain_counts_by_chain": multichain.get("counts_by_chain", {}),
            "established_1h_unique": (census.get("summary") or {}).get("unique_established_symbols_observed", 0),
            "established_1h_runs": (census.get("summary") or {}).get("runs_recorded", 0),
            "catalyst_dna_market_profiles": dna.get("market_profiles_count", dna.get("profiles_count", 0)),
            "catalyst_dna_unique_symbols": dna.get("unique_symbols_count", 0),
            "catalyst_consensus_symbols": len(dna.get("consensus_profiles", []) or []),
            "catalyst_archetypes": len(dna.get("archetype_frequency", {})),
            "time_machine_patterns_tested": tm.get("patterns_tested", 0),
            "social_status": social.get("status"),
            "social_events": social.get("events", 0),
            "social_candidates": social.get("candidates", 0),
            "observed_influencers": social.get("influencers", 0),
        },
        "next_learning_targets": [
            "increase exact identity resolution rate for CEX spot and derivatives revival candidates",
            "measure 5m/15m/30m/1h/4h/24h response from first verified revival anomaly",
            "measure forward hit rate separately by Solana/Ethereum/BSC/Arbitrum/Base",
            "rank DNA patterns by verified forward hit rate and drawdown",
            "rank exchanges/sources by verified early-warning contribution",
            "compare cross-venue DEX+CEX spot confirmation against isolated indicators",
            "connect timestamped social/KOL evidence only after exact token identity",
        ],
    }
    _write(out / "learning-observations.json", learning)
    print("[orchestrator] COMPLETE", flush=True)
    return {
        "cex": cex,
        "multichain_veteran_revival": multichain,
        "established_hour_census": census,
        "catalyst_dna": dna,
        "time_machine": tm,
        "social_catalyst": social,
        "social_error": social_error,
        "summary": summary,
        "new_token_lab": new_lab,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
