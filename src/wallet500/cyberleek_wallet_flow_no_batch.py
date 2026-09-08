from __future__ import annotations

import json
import os
import time

from wallet500 import cyberleek_wallet_flow as flow

MIN_RESOLUTION_PCT = float(os.environ.get("CYBERLEEK_MIN_RESOLUTION_PCT", "80"))

_RPC_FETCH_TOTAL = 0
_RPC_FETCH_FAILURES = 0
_RPC_FETCH_NULLS = 0


def _reset_rpc_metrics() -> None:
    global _RPC_FETCH_TOTAL, _RPC_FETCH_FAILURES, _RPC_FETCH_NULLS
    _RPC_FETCH_TOTAL = 0
    _RPC_FETCH_FAILURES = 0
    _RPC_FETCH_NULLS = 0


def _rpc_individual(method: str, params_list: list[list]) -> list:
    """Compatibility path for providers that reject JSON-RPC batch bodies.

    Transport failure and a successfully decoded transaction that cannot be attributed
    to a signed token owner are deliberately different truth states. The old collector
    mixed both into ``unresolved`` which understated RPC coverage whenever the locked
    pair had transfers/LP/program touches that were not verified swaps.
    """
    global _RPC_FETCH_TOTAL, _RPC_FETCH_FAILURES, _RPC_FETCH_NULLS
    if not params_list:
        return []
    out: list = []
    failures = 0
    for index, params in enumerate(params_list):
        _RPC_FETCH_TOTAL += 1
        try:
            value = flow._rpc(method, params)
            if value is None:
                _RPC_FETCH_NULLS += 1
            out.append(value)
        except Exception:
            failures += 1
            _RPC_FETCH_FAILURES += 1
            out.append(None)
        if index + 1 < len(params_list):
            time.sleep(0.04)
    if failures == len(params_list):
        raise RuntimeError(f"RPC_{method}_ALL_INDIVIDUAL_READS_FAILED")
    return out


def _coverage_metrics(result: dict) -> dict:
    coverage = dict(result.get("coverage") or {})
    resolved_swaps = int(coverage.get("last_run_resolved_swaps") or 0)
    legacy_unresolved = int(coverage.get("last_run_unresolved") or 0)

    rpc_total = int(_RPC_FETCH_TOTAL)
    rpc_failures = int(_RPC_FETCH_FAILURES)
    rpc_nulls = int(_RPC_FETCH_NULLS)
    rpc_decoded = max(0, rpc_total - rpc_failures - rpc_nulls)
    rpc_resolution_pct = round(rpc_decoded / rpc_total * 100.0, 2) if rpc_total else None

    # Parent unresolved includes three different classes: transport/null reads and
    # successfully decoded pair touches that fail the strict signed-owner swap rule.
    # Preserve all of them, but never call a decoded non-swap an RPC failure.
    non_attributable = max(0, legacy_unresolved - rpc_failures - rpc_nulls)
    attribution_denom = resolved_swaps + non_attributable
    trade_attribution_pct = (
        round(resolved_swaps / attribution_denom * 100.0, 2)
        if attribution_denom
        else None
    )

    prior_gap = bool(coverage.get("coverage_gap"))
    low_rpc_resolution = rpc_resolution_pct is not None and rpc_resolution_pct < MIN_RESOLUTION_PCT
    coverage.update({
        "minimum_resolution_pct": MIN_RESOLUTION_PCT,
        "rpc_reads_attempted": rpc_total,
        "rpc_reads_decoded": rpc_decoded,
        "rpc_transport_failures": rpc_failures,
        "rpc_null_results": rpc_nulls,
        "rpc_resolution_pct": rpc_resolution_pct,
        "non_attributable_pair_touches": non_attributable,
        "trade_attribution_pct": trade_attribution_pct,
        "attribution_gap": bool(non_attributable),
        # Keep the legacy field for consumers, but make its meaning explicit.
        "last_run_resolution_pct": rpc_resolution_pct,
        "coverage_gap": prior_gap or low_rpc_resolution,
    })
    coverage["coverage_quality"] = "PARTIAL" if coverage["coverage_gap"] else "ACCEPTABLE"
    return coverage


def _harden_coverage(result: dict) -> dict:
    """Persist transport coverage separately from conservative swap attribution."""
    coverage = _coverage_metrics(result)
    result["coverage"] = coverage
    result.setdefault("truth_contract", {})["decoded_non_swap_pair_touches_are_not_rpc_failures"] = True
    result["truth_contract"]["non_attributable_pair_touches_are_not_guessed_as_wallets"] = True

    flow._write(flow.SUMMARY_PATH, result)
    state = flow._load(flow.STATE_PATH, {})
    if isinstance(state, dict) and isinstance(state.get("last_run"), dict):
        state["last_run"].update({
            "coverage_gap": coverage["coverage_gap"],
            "rpc_resolution_pct": coverage["rpc_resolution_pct"],
            "trade_attribution_pct": coverage["trade_attribution_pct"],
            "non_attributable_pair_touches": coverage["non_attributable_pair_touches"],
            "minimum_resolution_pct": MIN_RESOLUTION_PCT,
        })
        flow._write(flow.STATE_PATH, state)
    return result


def main() -> None:
    _reset_rpc_metrics()
    flow._rpc_batch = _rpc_individual
    result = _harden_coverage(flow.run())
    print(json.dumps({"status": result.get("status"), "coverage": result.get("coverage")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
