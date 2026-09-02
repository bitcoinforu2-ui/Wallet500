from wallet500 import revival_wallet_registry as registry


def exposure(event_id, token, outcome, completed_at):
    return {
        "exposure_id": event_id + ":W",
        "event_id": event_id,
        "wallet": "W",
        "token_address": token,
        "completed_at": completed_at,
        "outcome_class": outcome,
        "eligible_for_future_tiers": True,
    }


def test_tier_stays_pending_without_minimum_history():
    rows = [
        exposure("e1", "a", "REVIVAL_X2", "2026-01-01T01:00:00+00:00"),
        exposure("e2", "b", "REVIVAL_X4", "2026-01-02T01:00:00+00:00"),
    ]
    score = registry.tier_from_exposures(rows)
    assert score["tier"] == "PENDING_HISTORY"
    assert score["completed_pre_waking_buy_exposures"] == 2


def test_strong_and_elite_require_real_completed_cross_token_history():
    strong_rows = [
        exposure(f"e{i}", f"t{i%3}", "REVIVAL_X2" if i < 3 else "NO_REVIVAL_24H", f"2026-01-0{i+1}T01:00:00+00:00")
        for i in range(5)
    ]
    strong = registry.tier_from_exposures(strong_rows)
    assert strong["tier"] == "STRONG"
    assert strong["x2_plus_hit_rate"] == 0.6

    elite_rows = [
        exposure(f"x{i}", f"z{i%5}", "REVIVAL_X10" if i < 5 else "NO_REVIVAL_24H", f"2026-02-{i+1:02d}T01:00:00+00:00")
        for i in range(8)
    ]
    elite = registry.tier_from_exposures(elite_rows)
    assert elite["tier"] == "ELITE"
    assert elite["distinct_completed_tokens"] == 5


def test_as_of_t0_excludes_outcome_completed_later():
    rows = [
        exposure("old1", "a", "REVIVAL_X2", "2026-01-01T01:00:00+00:00"),
        exposure("old2", "b", "REVIVAL_X2", "2026-01-02T01:00:00+00:00"),
        exposure("future", "c", "REVIVAL_X10", "2026-01-10T01:00:00+00:00"),
    ]
    score = registry.tier_from_exposures(rows, as_of="2026-01-05T00:00:00+00:00")
    assert score["completed_pre_waking_buy_exposures"] == 2
    assert score["distinct_completed_tokens"] == 2
    assert score["tier"] == "PENDING_HISTORY"


def test_completed_exposure_requires_verified_buy_at_or_before_t0():
    t0 = "2026-09-02T10:00:00+00:00"
    fs = {
        "events": {
            "E": {
                "event_id": "E",
                "token_address": "M",
                "symbol": "OLD",
                "completed": True,
                "completed_at": "2026-09-03T10:00:00+00:00",
                "outcome_class": "REVIVAL_X2",
                "t0": {"waking_t0": t0, "pair_address": "P"},
            }
        }
    }
    before = registry.epoch("2026-09-02T09:59:00+00:00")
    after = registry.epoch("2026-09-02T10:01:00+00:00")
    merged = {
        "M": [
            {"t": before, "sig": "1", "w": "BUYER", "side": "BUY", "pair_address": "P", "lane": "PRE_WAKING_DEEP_WATCH"},
            {"t": before, "sig": "2", "w": "SELLER", "side": "SELL", "pair_address": "P", "lane": "PRE_WAKING_DEEP_WATCH"},
            {"t": after, "sig": "3", "w": "LATE", "side": "BUY", "pair_address": "P", "lane": "WAKING_AND_FOLLOWUP"},
            {"t": before, "sig": "4", "w": "WRONGPAIR", "side": "BUY", "pair_address": "OTHER", "lane": "PRE_WAKING_DEEP_WATCH"},
        ]
    }
    rows = registry.build_completed_exposures(fs, merged)
    assert [row["wallet"] for row in rows] == ["BUYER"]
    assert rows[0]["signal_lane"] == "PRE_WAKING_DEEP_WATCH"


def test_merged_evidence_deduplicates_same_signature_wallet():
    state_a = {
        "tokens": {
            "M": {
                "pair_address": "P",
                "monitor_started_at": 1,
                "events": [{"t": 10, "sig": "S", "w": "W", "side": "BUY", "token_delta": 1}],
            }
        }
    }
    state_b = {
        "tokens": {
            "M": {
                "pair_address": "P",
                "monitor_started_at": 5,
                "events": [{"t": 10, "sig": "S", "w": "W", "side": "BUY", "token_delta": 1}],
            }
        }
    }
    merged = registry.merged_evidence_by_token(state_a, state_b)
    assert len(merged["M"]) == 1
