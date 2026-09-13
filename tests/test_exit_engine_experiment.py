from wallet500.exit_engine_experiment import _earliest_per_token, apply_observation, reconcile


def base_position():
    return {
        "status": "OPEN",
        "entry_price_usd": 1.0,
        "quantity": 10.0,
        "cost_usd": 10.0,
        "observed_peak_price_usd": 1.0,
        "trailing_active": False,
        "last_observed_at": "2026-09-13T00:00:00+00:00",
        "observations_applied": 1,
    }


def strategy():
    return {"hard_stop_pct": -8.0, "trailing_activation_gain_pct": 25.0, "trailing_stop_from_peak_pct": 10.0}


def test_hard_stop_first_observed_mark():
    p = base_position()
    apply_observation(p, "2026-09-13T00:01:00+00:00", 0.93, strategy())
    assert p["status"] == "OPEN"
    apply_observation(p, "2026-09-13T00:02:00+00:00", 0.91, strategy())
    assert p["status"] == "CLOSED"
    assert p["exit_reason"] == "HARD_STOP"
    assert p["exit_price_usd"] == 0.91


def test_trailing_activates_only_after_observed_25pct_gain():
    p = base_position()
    apply_observation(p, "2026-09-13T00:01:00+00:00", 1.24, strategy())
    assert p["trailing_active"] is False
    apply_observation(p, "2026-09-13T00:02:00+00:00", 1.30, strategy())
    assert p["trailing_active"] is True
    assert round(p["active_stop_price_usd"], 6) == 1.17
    apply_observation(p, "2026-09-13T00:03:00+00:00", 1.18, strategy())
    assert p["status"] == "OPEN"
    apply_observation(p, "2026-09-13T00:04:00+00:00", 1.16, strategy())
    assert p["status"] == "CLOSED"
    assert p["exit_reason"] == "TRAILING_STOP"


def test_one_position_per_token_across_pairs_keeps_earliest():
    rows = [
        {"key":"base:t:p2","chain":"base","token_address":"0xABC","pair_address":"p2","entry_price_usd":2,"entry_time":"2026-09-13T01:00:00+00:00"},
        {"key":"base:t:p1","chain":"base","token_address":"0xabc","pair_address":"p1","entry_price_usd":1,"entry_time":"2026-09-13T00:00:00+00:00"},
    ]
    kept, excluded = _earliest_per_token(rows)
    assert len(kept) == 1
    assert kept[0]["pair_address"] == "p1"
    assert len(excluded) == 1


def test_legacy_replay_uses_only_persisted_chronological_points():
    config = {
        "experiment_id": "X",
        "started_at": "2026-09-13T00:00:00+00:00",
        "strategy": strategy(),
    }
    ledger = {"positions":[{
        "key":"ethereum:t:p",
        "symbol":"TEST",
        "chain":"ethereum",
        "token_address":"0xabc",
        "pair_address":"0xpair",
        "entry_time":"2026-09-12T00:00:00+00:00",
        "entry_price_usd":1.0,
        "cost_usd":10.0,
        "quantity":10.0,
        "checkpoints":{
            "1h":{"captured_at":"2026-09-12T01:00:00+00:00","price_usd":1.30},
            "4h":{"captured_at":"2026-09-12T04:00:00+00:00","price_usd":1.16},
        },
        "last_mark_at":"2026-09-12T05:00:00+00:00",
        "current_price_usd":1.15,
    }]}
    out = reconcile(config, ledger, now="2026-09-13T00:01:00+00:00")
    p = next(iter(out["positions"].values()))
    assert p["status"] == "CLOSED"
    assert p["exit_price_usd"] == 1.16
    assert p["exit_reason"] == "TRAILING_STOP"
    assert p["historical_replay_basis"] == "PERSISTED_CHECKPOINTS_ONLY"
