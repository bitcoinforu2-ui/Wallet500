from __future__ import annotations

"""Run the guarded CEX action lane with resilient endpoints and hold confirmation."""

import run_cex_action_guarded as guard
from wallet500.cex_endpoint_fallbacks import install
from wallet500.cex_reactivation_hold import install as install_reactivation_hold

install(guard.promo)
reactivation_hold = install_reactivation_hold(guard)
_hold_eligibility = guard.promo._eligibility


def strict_reactivation_eligibility(row: object):
    ok, metrics = _hold_eligibility(row)
    if not ok or not isinstance(row, dict) or metrics.get("reactivation_hold_verified") is not True:
        return ok, metrics

    key = guard.canonical_key(row)
    entry = reactivation_hold.state.get("assets", {}).get(key, {})
    fresh_liquidity = float(entry.get("last_exact_pair_liquidity_usd") or 0.0)
    pair_price = float(metrics.get("reactivation_validation_pair_price_usd") or 0.0)
    cex_price = float(metrics.get("current_price") or 0.0)
    price_error = abs(pair_price / cex_price - 1.0) * 100.0 if pair_price > 0 and cex_price > 0 else None

    metrics["reactivation_validation_pair_liquidity_usd"] = fresh_liquidity
    metrics["reactivation_validation_cex_dex_price_error_pct"] = round(price_error, 4) if price_error is not None else None
    blockers = list(metrics.get("blockers") or [])
    if fresh_liquidity < guard.promo.MIN_EXECUTION_LIQUIDITY_USD:
        blockers.append("REACTIVATION_FRESH_EXECUTION_LIQUIDITY_LT_15K")
    if price_error is None or price_error > guard.promo.MAX_CEX_DEX_PRICE_ERROR_PCT:
        blockers.append("REACTIVATION_FRESH_CEX_DEX_PRICE_COHERENCE_FAILED")

    blockers = sorted(set(blockers))
    if blockers:
        metrics["blockers"] = blockers
        metrics["action_state"] = "REACTIVATION_FADE"
        metrics["action_basis"] = "FRESH_REACTIVATION_HOLD_FAILED_FINAL_EXACT_PAIR_RECHECK"
        metrics["reactivation_hold_verified"] = False
        metrics["runner_candidate"] = False
        return False, metrics
    return True, metrics


guard.promo._eligibility = strict_reactivation_eligibility
guard.bypass._eligibility = strict_reactivation_eligibility


if __name__ == "__main__":
    guard.promo.run()
    guard.bypass.run()
    reactivation_hold.persist()
