from wallet500.precision_pre_wave import MODE, build

NOW = "2026-09-12T10:00:00+00:00"


def _near(**overrides):
    row = {
        "symbol": "STORJ",
        "chain": "ethereum",
        "token_address": "0xb64ef51c888972c908cfacf59b47c1afbc0ab8ac",
        "pair_address": "0xaef16913b6c50ebcf627a394921f306985fc8604",
        "dex_url": "https://dexscreener.com/ethereum/0xaef16913b6c50ebcf627a394921f306985fc8604",
        "readiness_passed": 6,
        "readiness_total": 7,
        "missing_gates": ["STRONG_DECISION_LANE"],
        "blockers": ["NO_STRONG_DECISION_LANE"],
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "market_age_verified": True,
        "market_activity_verified": True,
        "execution_pool_liquidity_usd": 121328.05,
        "source_lane_count": 2,
        "signal_score": 54.0,
        "dex_volume_h1": 15462.44,
        "turnover_h1": 0.1274,
        "buys_h1": 39,
        "sells_h1": 39,
        "price_usd": 0.034,
    }
    row.update(overrides)
    return {"near_alert_leaderboard": [row]}


def _pending(move=12.0):
    return {"candidates": [{
        "symbol": "STORJUSDT",
        "first_alert_observed_at": "2026-09-06T09:41:49+00:00",
        "first_alert_reference_price": 0.03035,
        "first_alert_score": 35,
        "first_alert_coherent_confirmations": 2,
        "current_coherent_confirmations": 2,
        "current_change_24h_max_pct": move,
    }]}


def _identity(pair="0xaef16913b6c50ebcf627a394921f306985fc8604"):
    return {
        "generated_at": "2026-09-12T09:45:00+00:00",
        "candidates": [{
            "symbol": "STORJUSDT",
            "pair_address": pair,
            "coherent_confirmations": 2,
        }],
    }


def test_clean_storj_style_six_of_seven_is_early_manual_review():
    out = build(_near(), _pending(), _identity(), {}, NOW)
    assert out["mode"] == MODE
    assert out["truth_contract"]["real_alert_gate_unchanged"] is True
    assert out["user_alert_eligible_count"] == 1
    row = out["candidates"][0]
    assert row["timing"] == "EARLY_REVIEW"
    assert row["user_alert_eligible"] is True
    assert row["manual_review_only"] is True
    assert row["automatic_buy"] is False


def test_late_storj_style_move_is_tracked_but_never_alerted():
    out = build(_near(price_usd=0.07158), _pending(move=107.79), _identity(), {}, NOW)
    assert out["candidate_count"] == 1
    row = out["candidates"][0]
    assert row["timing"] == "LATE_DO_NOT_CHASE"
    assert row["user_alert_eligible"] is False
    assert row["status"] == "PRECISION_PRE_WAVE_LATE_NO_ALERT"


def test_extra_blocker_or_single_lane_fails_closed():
    out = build(
        _near(blockers=["NO_STRONG_DECISION_LANE", "EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL"], source_lane_count=1),
        _pending(), _identity(), {}, NOW,
    )
    assert out["candidate_count"] == 0
    reasons = out["rejected"][0]["reasons"]
    assert "EXTRA_BLOCKER" in reasons
    assert "SOURCE_LANES_LT_2" in reasons


def test_pair_mismatch_fails_closed():
    out = build(_near(), _pending(), _identity(pair="0xdeadbeef"), {}, NOW)
    assert out["candidate_count"] == 0
    assert "PAIR_MISMATCH" in out["rejected"][0]["reasons"]


def test_existing_real_alert_is_suppressed():
    near = _near()
    r = near["near_alert_leaderboard"][0]
    real = {"alerts": [{
        "status": "REAL_ALERT",
        "chain": r["chain"],
        "token_address": r["token_address"],
        "pair_address": r["pair_address"],
    }]}
    out = build(near, _pending(), _identity(), real, NOW)
    assert out["candidate_count"] == 0
    assert "ALREADY_REAL_ALERT" in out["rejected"][0]["reasons"]


def test_stale_identity_source_fails_closed():
    identity = _identity()
    identity["generated_at"] = "2026-09-12T08:00:00+00:00"
    out = build(_near(), _pending(), identity, {}, NOW)
    assert out["candidate_count"] == 0
    assert "CEX_IDENTITY_SOURCE_STALE" in out["rejected"][0]["reasons"]
