import json
from datetime import datetime, timezone

from wallet500 import hybrid_runner
from wallet500.hybrid_token_profile import (
    CHANNEL_WEIGHTS,
    _external_channel,
    _metric_deviation,
    _update_stat,
    build_profile,
)

TOKEN = "11111111111111111111111111111111"
PAIR_A = "22222222222222222222222222222222"
PAIR_B = "33333333333333333333333333333333"


def coin(**overrides):
    row = {
        "id": "test-token",
        "network": "solana",
        "network_verified": True,
        "solana_only_platform_verified": True,
        "token_address": TOKEN,
        "symbol": "TEST",
        "name": "Test Token",
        "price_usd": 1.2,
        "market_cap_usd": 1_000_000,
        "volume_24h_usd": 400_000,
        "change_24h_pct": 12.0,
        "change_7d_pct": 8.0,
        "change_30d_pct": 15.0,
        "drawdown_from_ath_pct": 82.0,
        "watch_score_market_only": 70.0,
        "revival_score_verified": 68.0,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "dex_pair_address": PAIR_A,
        "dex_pair_liquidity_usd": 80_000,
        "dex_pair_volume_24h_usd": 300_000,
        "dex_link": f"https://dexscreener.com/solana/{PAIR_A}",
    }
    row.update(overrides)
    return row


def stat(mean, var, last, count=4):
    return {"count": count, "mean": mean, "var": var, "last": last}


def mature_state(pair=PAIR_A):
    return {
        "observations": 4,
        "pair_address": pair,
        "metrics": {
            "price_usd": stat(1.0, 0.01, 1.0),
            "market_cap_usd": stat(900_000, 10_000_000_000, 900_000),
            "volume_24h_usd": stat(100_000, 400_000_000, 100_000),
            "dex_pair_liquidity_usd": stat(60_000, 25_000_000, 60_000),
            "dex_pair_volume_24h_usd": stat(80_000, 100_000_000, 80_000),
        },
    }


def test_ewma_state_uses_previous_baseline_then_updates():
    s = stat(100.0, 25.0, 105.0, count=4)
    d = _metric_deviation(120.0, s)
    assert d["baseline_count"] == 4
    assert d["baseline_mean"] == 100.0
    assert d["change_from_previous_pct"] > 14
    u = _update_stat(s, 120.0)
    assert u["count"] == 5
    assert u["mean"] > 100.0
    assert u["last"] == 120.0


def test_missing_external_channels_are_not_invented_or_counted():
    p, _ = build_profile(coin(), mature_state(), None, "2026-08-31T07:00:00+00:00")
    assert p["channels"]["holders"]["available"] is False
    assert p["channels"]["wallets"]["available"] is False
    assert p["channels"]["social"]["available"] is False
    assert p["channels"]["news"]["available"] is False
    assert p["evidence_coverage_pct"] == CHANNEL_WEIGHTS["market"] + CHANNEL_WEIGHTS["liquidity_pair"]


def test_external_evidence_requires_verified_exact_contract_match():
    bad = {"social": {"verified": True, "contract_match": False, "source": "x", "anomaly_score": 99}}
    assert _external_channel("social", bad)["available"] is False
    good = {"social": {"verified": True, "contract_match": True, "source": "x", "anomaly_score": 88, "signals": ["MENTIONS_SPIKE"]}}
    out = _external_channel("social", good)
    assert out["available"] is True
    assert out["score"] == 88
    assert out["signals"] == ["MENTIONS_SPIKE"]


def test_self_baseline_can_detect_multi_channel_abnormal_activity():
    p, _ = build_profile(coin(), mature_state(), None, "2026-08-31T07:00:00+00:00")
    assert p["baseline_ready"] is True
    assert p["channels"]["market"]["score"] >= 55
    assert p["channels"]["liquidity_pair"]["score"] >= 55
    assert len(p["strong_channels"]) >= 2
    assert p["status"] in {"HYBRID_IGNITION", "ABNORMAL_ACTIVITY"}


def test_pair_identity_change_and_liquidity_collapse_become_risk_not_alpha():
    risky = coin(
        dex_pair_address=PAIR_B,
        dex_pair_liquidity_usd=8_000,
        dex_pair_volume_24h_usd=120_000,
        change_24h_pct=55.0,
    )
    p, _ = build_profile(risky, mature_state(pair=PAIR_A), None, "2026-08-31T07:00:00+00:00")
    assert "PAIR_IDENTITY_CHANGE" in p["risk_reasons"]
    assert p["risk_score"] >= 50
    assert p["status"] == "RISK_DISTRIBUTION"


def test_first_observation_is_explicitly_baseline_learning():
    first = coin(change_24h_pct=1.0, watch_score_market_only=10.0)
    p, state = build_profile(first, None, None, "2026-08-31T07:00:00+00:00")
    assert p["baseline_observations_before"] == 0
    assert p["baseline_ready"] is False
    assert p["status"] == "BASELINE_LEARNING"
    assert state["observations"] == 1


def test_runner_accepts_same_run_holder_evidence_after_market_snapshot(tmp_path, monkeypatch):
    external_path = tmp_path / "external.json"
    source_time = "2026-08-31T07:00:00+00:00"
    accepted_time = "2026-08-31T07:09:00+00:00"
    too_late_time = "2026-08-31T10:01:00+00:00"
    external_path.write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "network": "solana",
                        "token_address": TOKEN,
                        "observed_at": accepted_time,
                        "holders": {
                            "verified": True,
                            "contract_match": True,
                            "source": "test-rpc",
                            "anomaly_score": 91,
                        },
                    },
                    {
                        "network": "solana",
                        "token_address": PAIR_A,
                        "observed_at": too_late_time,
                        "holders": {
                            "verified": True,
                            "contract_match": True,
                            "source": "future-test",
                            "anomaly_score": 99,
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(hybrid_runner.engine, "EXTERNAL", external_path)
    run_time = datetime(2026, 8, 31, 7, 10, tzinfo=timezone.utc)
    evidence = hybrid_runner._load_external_truth(source_time, run_time)
    assert TOKEN in evidence
    assert PAIR_A not in evidence


def test_runner_refreshes_external_channel_without_replaying_market_baseline():
    profile, state = build_profile(coin(), mature_state(), None, "2026-08-31T07:00:00+00:00")
    before_observations = profile["baseline_observations_before"]
    holder = {
        "network": "solana",
        "token_address": TOKEN,
        "observed_at": "2026-08-31T07:09:00+00:00",
        "holders": {
            "verified": True,
            "contract_match": True,
            "source": "test-rpc",
            "anomaly_score": 90,
            "signals": ["EXACT_MINT_OWNER_RESOLUTION_COMPLETE"],
        },
    }
    refreshed = hybrid_runner._recompute_profile_with_external(
        profile,
        holder,
        "2026-08-31T07:10:00+00:00",
    )
    assert refreshed["channels"]["holders"]["available"] is True
    assert refreshed["channels"]["holders"]["score"] == 90
    assert refreshed["baseline_observations_before"] == before_observations
    assert state["observations"] == mature_state()["observations"] + 1
    assert refreshed["observed_at"] == "2026-08-31T07:10:00+00:00"


def test_external_fingerprint_is_order_stable_and_changes_with_evidence():
    a = {TOKEN: {"holders": {"anomaly_score": 90}}, PAIR_A: {"holders": {"anomaly_score": 80}}}
    b = {PAIR_A: {"holders": {"anomaly_score": 80}}, TOKEN: {"holders": {"anomaly_score": 90}}}
    c = {TOKEN: {"holders": {"anomaly_score": 91}}, PAIR_A: {"holders": {"anomaly_score": 80}}}
    assert hybrid_runner._external_fingerprint(a) == hybrid_runner._external_fingerprint(b)
    assert hybrid_runner._external_fingerprint(a) != hybrid_runner._external_fingerprint(c)
