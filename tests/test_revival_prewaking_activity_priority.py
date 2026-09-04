from wallet500.revival_prewaking_wallet_evidence import select_targets


def row(name, score, liq, vol):
    return {
        "token_address": name + "111111111111111111111111111111111111",
        "symbol": name,
        "dex_pair_address": "Pair" + name + "111111111111111111111111111111111",
        "watch_status": "DEEP_WATCH",
        "market_age_verified": True,
        "market_age_min_days": 200,
        "revival_score_verified": score,
        "dex_pair_liquidity_usd": liq,
        "dex_pair_volume_24h_usd": vol,
    }


def payload(coins):
    return {
        "network": "solana",
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "generated_at": "2026-09-04T10:00:00+00:00",
        "coins": coins,
    }


def test_active_market_beats_dead_high_score_for_priority_slot():
    cold = row("COLD", 99, 50, 10)
    active = row("ACTIVE", 60, 60000, 3000)
    warm = row("WARM", 80, 12000, 1000)
    selected = select_targets(payload([cold, active, warm]), {}, max_targets=3, priority_slots=2)
    assert [x["symbol"] for x in selected[:2]] == ["ACTIVE", "WARM"]
    assert [x["activity_tier"] for x in selected[:2]] == ["ACTIVE_DEEP_WATCH", "WARM_DEEP_WATCH"]
    assert selected[2]["symbol"] == "COLD"
    assert selected[2]["selection_lane"] == "ROTATION_COVERAGE"


def test_cold_rows_are_not_deleted_from_rotation_universe():
    coins = [row("A", 70, 60000, 1000), row("B", 99, 100, 1), row("C", 98, 100, 1)]
    first = select_targets(payload(coins), {}, max_targets=2, priority_slots=1)
    second = select_targets(payload(coins), {"tokens": first}, max_targets=2, priority_slots=1)
    rotated = {first[1]["symbol"], second[1]["symbol"]}
    assert rotated == {"B", "C"}
    assert all(x["activity_tier"] == "COLD_DEEP_WATCH" for x in [first[1], second[1]])
