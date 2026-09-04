from wallet500.revival_prewaking_wallet_evidence import select_targets


def coin(i, score):
    return {
        "token_address": f"Mint{i:02d}11111111111111111111111111111111111",
        "symbol": f"T{i}",
        "dex_pair_address": f"Pair{i:02d}11111111111111111111111111111111111",
        "watch_status": "DEEP_WATCH",
        "market_age_verified": True,
        "market_age_min_days": 200,
        "revival_score_verified": score,
        "dex_pair_volume_24h_usd": 1000 - i,
        "dex_pair_liquidity_usd": 100000 - i,
    }


def revival():
    return {
        "network": "solana",
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "generated_at": "2026-09-04T10:00:00+00:00",
        "coins": [coin(i, 100 - i) for i in range(12)],
    }


def test_priority_stays_and_rotation_advances():
    first = select_targets(revival(), {}, max_targets=8, priority_slots=4)
    assert [x["selection_lane"] for x in first[:4]] == ["PRIORITY_PERSISTENT"] * 4
    assert [x["token_address"] for x in first[:4]] == [coin(i, 100-i)["token_address"] for i in range(4)]
    previous = {"tokens": first}
    second = select_targets(revival(), previous, max_targets=8, priority_slots=4)
    assert [x["token_address"] for x in second[:4]] == [x["token_address"] for x in first[:4]]
    assert {x["token_address"] for x in second[4:]}.isdisjoint({x["token_address"] for x in first[4:]})


def test_rotation_wraps_without_duplicates():
    first = select_targets(revival(), {}, max_targets=6, priority_slots=4)
    second = select_targets(revival(), {"tokens": first}, max_targets=6, priority_slots=4)
    third = select_targets(revival(), {"tokens": second}, max_targets=6, priority_slots=4)
    assert len({x["token_address"] for x in third}) == 6
    assert all(x["reason"] == "PRE_WAKING_DEEP_WATCH" for x in third)
