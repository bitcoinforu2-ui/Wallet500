from __future__ import annotations

import json
import os
import time

from wallet500 import cyberleek_wallet_flow as flow

MIN_RESOLUTION_PCT = float(os.environ.get("CYBERLEEK_MIN_RESOLUTION_PCT", "80"))


def _rpc_individual(method: str, params_list: list[list]) -> list:
    """Compatibility path for RPC providers that reject JSON-RPC batch bodies.

    Truth behavior stays fail-closed: an individual failed read is unresolved, and if
    every transport/RPC read in the chunk fails we raise so the parent writer emits
    RPC_ERROR_FAIL_CLOSED rather than pretending there were zero traders.
    """
    if not params_list:
        return []
    out: list = []
    failures = 0
    for index, params in enumerate(params_list):
        try:
            out.append(flow._rpc(method, params))
        except Exception:
            failures += 1
            out.append(None)
        if index + 1 < len(params_list):
            time.sleep(0.04)
    if failures == len(params_list):
        raise RuntimeError(f"RPC_{method}_ALL_INDIVIDUAL_READS_FAILED")
    return out


def _harden_coverage(result: dict) -> dict:
    """Mark partial RPC resolution as a coverage gap without inventing wallets.

    The underlying event set remains exactly the signed token-owner deltas resolved by
    the parent collector. This only hardens the quality label so dashboards/research
    cannot interpret a low-resolution sample as complete coverage.
    """
    coverage = result.get("coverage") or {}
    resolved = int(coverage.get("last_run_resolved_swaps") or 0)
    unresolved = int(coverage.get("last_run_unresolved") or 0)
    denom = resolved + unresolved
    resolution_pct = round(resolved / denom * 100.0, 2) if denom else None
    if resolution_pct is not None:
        coverage["last_run_resolution_pct"] = resolution_pct
    low_resolution = resolution_pct is not None and resolution_pct < MIN_RESOLUTION_PCT
    coverage["coverage_gap"] = bool(coverage.get("coverage_gap")) or low_resolution
    coverage["minimum_resolution_pct"] = MIN_RESOLUTION_PCT
    coverage["coverage_quality"] = "PARTIAL" if coverage["coverage_gap"] else "ACCEPTABLE"
    result["coverage"] = coverage

    # Persist the hardened label in both public summary and forward-only state.
    flow._write(flow.SUMMARY_PATH, result)
    state = flow._load(flow.STATE_PATH, {})
    if isinstance(state, dict) and isinstance(state.get("last_run"), dict):
        state["last_run"]["coverage_gap"] = coverage["coverage_gap"]
        state["last_run"]["resolution_pct"] = resolution_pct
        state["last_run"]["minimum_resolution_pct"] = MIN_RESOLUTION_PCT
        flow._write(flow.STATE_PATH, state)
    return result


def main() -> None:
    flow._rpc_batch = _rpc_individual
    result = _harden_coverage(flow.run())
    print(json.dumps({"status": result.get("status"), "coverage": result.get("coverage")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
