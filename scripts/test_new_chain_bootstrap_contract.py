from __future__ import annotations

from datetime import datetime, timezone

import new_chain_bootstrap_radar as radar


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    now = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)

    row = {
        "network": "arc",
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

    # Seeded emerging networks stay observable through their configured 30-day
    # bootstrap period. This is research coverage only and never bypasses FINAL BUY.
    seeded_older = dict(row, pair_age_hours=24 * 20)
    assert_true(radar.pair_age_limit_hours(seeded_older) == 30 * 24, "seeded network age window should be 30d")
    assert_true(radar.candidate_eligible(seeded_older) is True, "20d Arc candidate should remain observable")

    ordinary_older = dict(row, network="brandnew", pair_age_hours=24 * 20)
    assert_true(radar.pair_age_limit_hours(ordinary_older) == radar.MAX_PAIR_AGE_HOURS, "ordinary network age policy drift")
    assert_true(radar.candidate_eligible(ordinary_older) is False, "ordinary network must keep bounded default age window")
    assert_true(radar.ACTIVE_POOL_SCAN_PAGES >= 3, "active pool scan depth regressed")

    initial = {"version": 1, "baseline_initialized": False, "known_networks": {}, "auto_active_networks": []}
    baseline, new1 = radar.update_network_state(initial, ["eth", "bsc", "futurex"], now)
    assert_true(new1 == [], "first provider catalog must be baseline, not false new-chain alerts")
    assert_true("arc" in radar.active_networks(baseline), "seeded Arc must always be active")
    assert_true("robinhood" in radar.active_networks(baseline), "seeded Robinhood must stay active even when it was already present in the provider baseline")

    later = dict(baseline)
    later["baseline_initialized"] = True
    after, new2 = radar.update_network_state(later, ["eth", "bsc", "futurex", "brandnew"], now)
    assert_true("brandnew" in new2, "post-baseline provider network must auto-bootstrap")
    assert_true("brandnew" in radar.active_networks(after), "auto-detected network must enter active bootstrap window")

    print("NEW_CHAIN_BOOTSTRAP_CONTRACT_OK", {"score": score, "active": radar.active_networks(after)})


if __name__ == "__main__":
    main()
