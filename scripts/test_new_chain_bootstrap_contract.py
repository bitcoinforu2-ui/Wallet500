from __future__ import annotations

from datetime import datetime, timezone

import new_chain_bootstrap_radar as radar


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    now = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)

    row = {
        "symbol": "ARCUS",
        "liquidity_usd": 64000,
        "volume_h1": 42000,
        "volume_h24": 131000,
        "buys_h1": 95,
        "sells_h1": 41,
        "price_change_h1": 18,
        "pair_age_hours": 36,
    }
    score, reasons = radar.score_pool(row)
    assert_true(score >= radar.MIN_SCORE, f"expected strong bootstrap score, got {score}")
    assert_true("BUY_PRESSURE_POSITIVE" in reasons or "BUY_PRESSURE_2X" in reasons, "buy pressure signal missing")
    assert_true(radar.candidate_eligible(row) is True, "healthy Arc candidate should be eligible")

    stable = dict(row, symbol="USDC")
    assert_true(radar.candidate_eligible(stable) is False, "stable/base assets must be filtered")

    initial = {"version": 1, "baseline_initialized": False, "known_networks": {}, "auto_active_networks": []}
    baseline, new1 = radar.update_network_state(initial, ["eth", "bsc", "futurex"], now)
    assert_true(new1 == [], "first provider catalog must be baseline, not false new-chain alerts")
    assert_true("arc" in radar.active_networks(baseline), "seeded Arc must always be active")

    later = dict(baseline)
    later["baseline_initialized"] = True
    after, new2 = radar.update_network_state(later, ["eth", "bsc", "futurex", "brandnew"], now)
    assert_true("brandnew" in new2, "post-baseline provider network must auto-bootstrap")
    assert_true("brandnew" in radar.active_networks(after), "auto-detected network must enter active bootstrap window")

    print("NEW_CHAIN_BOOTSTRAP_CONTRACT_OK", {"score": score, "active": radar.active_networks(after)})


if __name__ == "__main__":
    main()
