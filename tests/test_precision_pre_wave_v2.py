import json
from pathlib import Path

from wallet500.precision_pre_wave_v2 import MODE, run, update_ledger


def test_earliest_signal_is_immutable_when_later_alert_arrives():
    previous = {"symbols": {"STORJ": {
        "symbol": "STORJ",
        "first_alert_observed_at": "2026-09-06T09:41:49+00:00",
        "first_alert_reference_price": 0.03035,
        "first_alert_score": 35,
        "first_alert_coherent_confirmations": 2,
    }}}
    pending = {"candidates": [{
        "symbol": "STORJUSDT",
        "first_alert_observed_at": "2026-09-12T09:00:00+00:00",
        "first_alert_reference_price": 0.07,
        "first_alert_score": 80,
        "first_alert_coherent_confirmations": 4,
    }]}
    out = update_ledger(previous, pending, {}, "2026-09-12T10:00:00+00:00")
    row = out["symbols"]["STORJ"]
    assert row["first_alert_observed_at"] == "2026-09-06T09:41:49+00:00"
    assert row["first_alert_reference_price"] == 0.03035


def test_signal_survives_watchlist_exit_and_feeds_precision_lane(tmp_path: Path):
    data = tmp_path
    now1 = "2026-09-12T09:30:00+00:00"
    early = {
        "generated_at": "2026-09-12T09:25:00+00:00",
        "candidates": [{
            "symbol": "STORJUSDT",
            "first_alert_observed_at": "2026-09-06T09:41:49+00:00",
            "first_alert_reference_price": 0.03035,
            "first_alert_score": 35,
            "first_alert_coherent_confirmations": 2,
            "current_coherent_confirmations": 2,
            "current_change_24h_max_pct": 8.0,
        }],
    }
    (data / "cex-early-revival-pending.json").write_text(json.dumps(early))
    (data / "cex-spot-revival-radar.json").write_text(json.dumps({"watchlist": []}))
    (data / "near-alert-observatory.json").write_text(json.dumps({"near_alert_leaderboard": []}))
    (data / "cex-spot-identity-radar.json").write_text(json.dumps({"generated_at": "2026-09-12T09:25:00+00:00", "candidates": []}))
    (data / "real-alerts.json").write_text(json.dumps({"alerts": []}))
    run(data, now1)

    ledger = json.loads((data / "precision-pre-wave-early-signal-ledger.json").read_text())
    assert ledger["symbols"]["STORJ"]["first_alert_reference_price"] == 0.03035

    # STORJ leaves the early/pending feed after exact identity resolves.
    (data / "cex-early-revival-pending.json").write_text(json.dumps({"candidates": []}))
    near = {"near_alert_leaderboard": [{
        "symbol": "STORJ",
        "chain": "ethereum",
        "token_address": "0xb64ef51c888972c908cfacf59b47c1afbc0ab8ac",
        "pair_address": "0xaef16913b6c50ebcf627a394921f306985fc8604",
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
        "dex_volume_h1": 15462.44,
        "turnover_h1": 0.1274,
        "buys_h1": 39,
        "sells_h1": 39,
        "price_usd": 0.034,
    }]}
    identity = {"generated_at": "2026-09-12T09:45:00+00:00", "candidates": [{
        "symbol": "STORJUSDT",
        "pair_address": "0xaef16913b6c50ebcf627a394921f306985fc8604",
        "coherent_confirmations": 2,
    }]}
    (data / "near-alert-observatory.json").write_text(json.dumps(near))
    (data / "cex-spot-identity-radar.json").write_text(json.dumps(identity))
    out = run(data, "2026-09-12T10:00:00+00:00")
    assert out["mode"] == MODE
    assert out["truth_contract"]["early_signal_survives_watchlist_exit"] is True
    assert out["candidate_count"] == 1
    row = out["candidates"][0]
    assert row["first_alert_reference_price"] == 0.03035
    assert row["timing"] == "EARLY_REVIEW"
    assert row["user_alert_eligible"] is True
    assert row["automatic_buy"] is False
