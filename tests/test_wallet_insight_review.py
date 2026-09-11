import json
from pathlib import Path

from wallet500.wallet_insight_review import build


TOKEN = "Mint111111111111111111111111111111111111111"
PAIR = "Pair111111111111111111111111111111111111111"


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def candidate(wallet_verified=False, wallet_positive=False, smart_positive=False):
    return {
        "token_address": TOKEN,
        "pair_address": PAIR,
        "symbol": "TEST",
        "status": "EVIDENCE_READY",
        "discovery_tier": "WAKING_EVIDENCE_READY",
        "families": {
            "wallet_accumulation": {"verified": wallet_verified, "positive": wallet_positive},
            "smart_money": {"verified": True, "positive": smart_positive, "metrics": {"historically_qualified_pre_waking_buyers": 0}},
        },
    }


def test_current_probe_without_live_wallet_row_is_pipeline_bottleneck(tmp_path):
    write(tmp_path, "candidate-evidence-envelope.json", {"generated_at": "2026-09-11T20:00:00Z", "candidates": [candidate()]})
    write(tmp_path, "revival-prewaking-wallet-evidence.json", {"generated_at": "2026-09-11T20:00:00Z", "tokens": []})
    write(tmp_path, "revival-wallet-coverage-probe.json", {
        "generated_at": "2026-09-11T20:00:00Z",
        "tokens": [{"token_address": TOKEN, "pair_address": PAIR, "coverage_verified": True, "historical_coverage_verified": True, "coverage_degraded": False}],
    })
    result = build(tmp_path)
    row = result["rows"][0]
    assert row["classification"] == "DATA_PIPELINE_BOTTLENECK"
    assert "NO_LIVE_PREWAKING_WALLET_ROW" in row["blockers"]
    assert result["truth_contract"]["promotion_allowed"] is False
    assert row["production_effect"] is False


def test_historical_coverage_never_becomes_current_positive(tmp_path):
    write(tmp_path, "candidate-evidence-envelope.json", {"candidates": [candidate()]})
    write(tmp_path, "revival-prewaking-wallet-evidence.json", {"tokens": []})
    write(tmp_path, "revival-wallet-coverage-probe.json", {
        "tokens": [{"token_address": TOKEN, "pair_address": PAIR, "coverage_verified": False, "historical_coverage_verified": True, "coverage_degraded": True}],
    })
    result = build(tmp_path)
    row = result["rows"][0]
    assert row["metrics"]["current_probe_verified"] is False
    assert row["metrics"]["historical_probe_verified"] is True
    assert "CURRENT_COVERAGE_DEGRADED" in row["blockers"]
    assert row["metrics"]["wallet_family_positive"] is False


def test_verified_wallet_lane_reports_behavioral_shortfall_without_relaxing_thresholds(tmp_path):
    write(tmp_path, "candidate-evidence-envelope.json", {"candidates": [candidate(wallet_verified=True)]})
    write(tmp_path, "revival-wallet-coverage-probe.json", {
        "tokens": [{"token_address": TOKEN, "pair_address": PAIR, "coverage_verified": True, "historical_coverage_verified": True, "coverage_degraded": False}],
    })
    write(tmp_path, "revival-prewaking-wallet-evidence.json", {
        "tokens": [{
            "token_address": TOKEN,
            "exact_pair": PAIR,
            "coverage": {"coverage_quality": "ACCEPTABLE", "coverage_gap": False, "last_run_resolution_pct": 100, "minimum_resolution_pct": 80},
            "windows": {"h1": {"resolved_swaps": 4, "first_seen_buyers_since_monitor_t0": 2, "net_accumulating_wallets": 2, "net_distributing_wallets": 2, "wallet_buy_sell_ratio": 1.0}},
        }],
    })
    result = build(tmp_path)
    row = result["rows"][0]
    assert row["classification"] == "MARKET_WALLET_EVIDENCE_WEAK"
    assert "INSUFFICIENT_H1_RESOLVED_SWAPS" in row["blockers"]
    assert "INSUFFICIENT_FIRST_SEEN_BUYERS" in row["blockers"]
    assert "INSUFFICIENT_NET_ACCUMULATORS" in row["blockers"]
    assert "BUY_SELL_RATIO_BELOW_1_15" in row["blockers"]
    assert result["truth_contract"]["wallet_thresholds_are_diagnostic_mirrors_not_changed"] is True


def test_positive_wallet_lane_is_reported_but_never_promotes(tmp_path):
    write(tmp_path, "candidate-evidence-envelope.json", {"candidates": [candidate(wallet_verified=True, wallet_positive=True, smart_positive=True)]})
    write(tmp_path, "revival-wallet-coverage-probe.json", {"tokens": [{"token_address": TOKEN, "pair_address": PAIR, "coverage_verified": True}]})
    write(tmp_path, "revival-prewaking-wallet-evidence.json", {
        "tokens": [{
            "token_address": TOKEN,
            "exact_pair": PAIR,
            "coverage": {"coverage_quality": "ACCEPTABLE", "coverage_gap": False, "last_run_resolution_pct": 100, "minimum_resolution_pct": 80},
            "windows": {"h1": {"resolved_swaps": 8, "first_seen_buyers_since_monitor_t0": 4, "net_accumulating_wallets": 5, "net_distributing_wallets": 1, "wallet_buy_sell_ratio": 1.7}},
        }],
    })
    result = build(tmp_path)
    row = result["rows"][0]
    assert row["classification"] == "ACCUMULATION_CONFIRMED"
    assert result["production_effect"] is False
    assert result["automatic_buy"] is False
    assert result["truth_contract"]["production_threshold_change_allowed"] is False
