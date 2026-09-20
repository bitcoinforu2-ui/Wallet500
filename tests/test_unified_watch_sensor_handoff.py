from scripts.unified_watch_engine import spot_cex_sensor
from scripts.spot_cex_fast_handoff import _pending_identity_candidates, _should_refresh


def test_island_style_relative_volume_shock_escalates_from_own_baseline():
    previous = {
        "cex_quote_volume_baseline_usd": 314.99,
        "cex_quote_volume_24h_usd": 494.46,
        "positive_gainer_rank": 25,
    }
    current = {
        "dynamic_spot_candidate": True,
        "quote_volume_24h_usd": 1802.33,
        "positive_gainer_rank": 8,
    }
    sensor = spot_cex_sensor(current, previous)
    assert sensor["cex_led"] is True
    assert sensor["baseline_multiple"] > 5.7
    assert "CEX_RELATIVE_VOLUME_SHOCK" in sensor["triggers"]
    assert "CEX_RANK_ACCELERATION" in sensor["triggers"]


def test_first_spot_observation_sets_baseline_without_false_trigger():
    sensor = spot_cex_sensor(
        {
            "dynamic_spot_candidate": True,
            "quote_volume_24h_usd": 314.99,
            "positive_gainer_rank": 11,
        },
        {},
    )
    assert sensor["baseline_volume_usd"] == 314.99
    assert sensor["baseline_multiple"] == 1.0
    assert sensor["triggers"] == []


def test_fast_handoff_refreshes_on_first_shock_and_not_on_identical_repeat():
    sensor = {
        "baseline_multiple": 5.72,
        "current_rank": 8,
    }
    assert _should_refresh({}, sensor) is True
    previous = {
        "last_internal_escalation": {
            "cex_relative_volume_multiple": 5.72,
            "positive_gainer_rank": 8,
        }
    }
    assert _should_refresh(previous, sensor) is False
    assert _should_refresh(previous, {"baseline_multiple": 8.7, "current_rank": 8}) is True
    assert _should_refresh(previous, {"baseline_multiple": 5.9, "current_rank": 3}) is True


def test_island_replay_first_trigger_is_1256_local():
    previous = {}
    sequence = [
        ("2026-09-19T04:20:30.918153+00:00", 314.99, 11),
        ("2026-09-19T04:45:11.592679+00:00", 365.24, 11),
        ("2026-09-19T07:58:55.162025+00:00", 378.04, 11),
        ("2026-09-19T08:59:20.944460+00:00", 494.46, 25),
        ("2026-09-19T09:44:24.160924+00:00", 712.86, 21),
        ("2026-09-19T09:56:19.811417+00:00", 1802.33, 8),
    ]
    first_trigger = None
    for observed_at, volume, rank in sequence:
        target = {
            "dynamic_spot_candidate": True,
            "quote_volume_24h_usd": volume,
            "positive_gainer_rank": rank,
        }
        sensor = spot_cex_sensor(target, previous)
        if sensor["triggers"] and first_trigger is None:
            first_trigger = (observed_at, volume, rank, sensor)
        previous = {
            **previous,
            "cex_quote_volume_24h_usd": sensor["current_volume_usd"],
            "cex_quote_volume_baseline_usd": sensor["baseline_volume_usd"],
            "positive_gainer_rank": sensor["current_rank"],
        }

    assert first_trigger is not None
    observed_at, volume, rank, sensor = first_trigger
    assert observed_at == "2026-09-19T09:56:19.811417+00:00"
    assert volume == 1802.33
    assert rank == 8
    assert sensor["baseline_multiple"] == 5.7219
    assert "CEX_RELATIVE_VOLUME_SHOCK" in sensor["triggers"]
    assert "CEX_VOLUME_ACCELERATION" in sensor["triggers"]
    assert "CEX_RANK_ACCELERATION" in sensor["triggers"]


def test_one_identity_pending_replay_keeps_cex_sensors_alive_without_contract():
    doc = {
        "candidates": [{
            "symbol": "ONEUSDT",
            "base_symbol": "ONE",
            "coingecko_id": "harmony",
            "market_age_verified": True,
            "identity_status": "IDENTITY_PENDING",
            "identity_blocker": "NO_EXACT_ONCHAIN_PLATFORM_IDENTITY",
            "current_coherent_confirmations": 3,
            "current_change_24h_max_pct": 37.8,
            "leaderboard_best_rank": 2,
            "leaderboard_volume_24h_max": 2_949_639.18,
            "markets": [
                {"exchange": "gate", "price": 0.0027884, "volume_24h": 2_949_639.18, "volume_comparable_usd_like": True},
                {"exchange": "okx", "price": 0.00275, "volume_24h": 1_200_000, "volume_comparable_usd_like": True},
            ],
            "milestones": {
                "first_seen": {"observed_at": "2026-09-04T10:50:55+00:00", "reference_price": 0.00071}
            },
        }]
    }
    targets = _pending_identity_candidates(doc)
    assert len(targets) == 1
    target = targets[0]
    assert target["candidate_type"] == "CEX_IDENTITY_PENDING"
    assert target["coingecko_id"] == "harmony"
    assert target["asset_identity_verified"] is True
    assert target["asset_identity_scope"] == "CURATED_NATIVE_ASSET_PLUS_CANONICAL_WRAPPER"
    assert target["asset_network"] == "harmony"
    assert target["canonical_wrapper_contract"].lower() == "0xcf664087a5bb0237a0bad6742852ec6c8d69a27a"
    assert target["execution_identity_verified"] is False
    assert "contract" not in target
    assert "pair" not in target

    previous = {
        "cex_quote_volume_baseline_usd": 2_806_980.14,
        "cex_quote_volume_24h_usd": 2_806_980.14,
        "positive_gainer_rank": 643,
    }
    sensor = spot_cex_sensor(target, previous)
    assert sensor["cex_led"] is True
    assert "CEX_TOP3_BREAKOUT" in sensor["triggers"]
    assert "CEX_RANK_ACCELERATION" in sensor["triggers"]
