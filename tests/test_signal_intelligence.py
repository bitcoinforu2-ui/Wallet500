import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wallet500.signal_intelligence import FEATURES, build, train


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def market_row(**extra):
    row = {
        "chain": "solana",
        "token_address": "MINT1",
        "pair_address": "PAIR1",
        "symbol": "OLD",
        "price_usd": 1.0,
        "execution_pool_liquidity_usd": 120000,
        "market_age_verified": True,
        "market_age_min_days": 700,
        "holder_growth_pct": 20,
        "unique_buyers_change_pct": 25,
        "smart_wallet_buy_count": 4,
        "volume_change_pct": 90,
        "liquidity_change_pct": 12,
        "cex_revival_score": 60,
        "coherent_confirmations": 3,
    }
    row.update(extra)
    return row


def seed(root: Path, stamp: str, row=None):
    row = row or market_row()
    write(root, "candidate-evidence-envelope.json", {"generated_at": stamp, "candidates": [row]})
    write(root, "run-summary.json", {"updated_at": stamp})
    write(root, "holder-cluster-production-report.json", {"updated_at": stamp})
    write(root, "active-qualified-candidates.json", [row])
    write(root, "revival-precursor-latest.json", {"targets": [row]})
    write(root, "waking-confirmation-latest.json", {"targets": []})
    write(root, "revival-1000-latest.json", {"coins": [row]})
    write(root, "cex-revival-radar.json", {"alerts": [row]})
    write(root, "holder-cluster-gate.json", {"rows": [row]})
    write(root, "social-intelligence-v2.json", {"tokens": []})
    write(root, "cross-signal-fusion-v2.json", {"tokens": []})
    write(root, "real-alert-10usd-summary.json", {"positions": []})
    write(root, "rejected-outcome-report.json", {
        "records": 20,
        "false_negatives": [{
            "identity": {"chain": "solana", "token": "X", "pair_address": "Y"},
            "first_reject_source": "LIVE_SURVIVAL_FAILED",
            "first_reject_reasons": ["CURRENT_LIQUIDITY_BELOW_50K"],
            "tradable_peak_gain_since_reject_pct": 500,
        }],
    })


def test_fresh_inputs_create_signal_dna_phase_wallet_intent_and_missed_winner_lab(tmp_path):
    now = datetime(2026, 9, 5, 18, 5, tzinfo=timezone.utc)
    seed(tmp_path, "2026-09-05T18:00:00+00:00")
    payload, ledger = build(tmp_path, now=now, enforce_freshness=True)
    assert payload["data_health"]["production_safe"] is True
    assert payload["counts"]["candidates"] == 1
    row = payload["candidates"][0]
    assert set(row["signal_dna"]["features"]) == set(FEATURES)
    assert row["wallet_intent"]["label"] == "CLUSTER_ACCUMULATION"
    assert row["revival_phase"]["phase"] in {"WAKING", "ACCELERATING", "BREAKOUT"}
    assert row["expected_value"]["research_only"] is True
    assert payload["missed_winner_lab"]["major_false_negatives"] == 1
    assert ledger["records"][0]["immutable_t0"] is True


def test_stale_required_input_fails_closed(tmp_path):
    now = datetime(2026, 9, 5, 18, 5, tzinfo=timezone.utc)
    seed(tmp_path, "2026-09-05T10:00:00+00:00")
    payload, _ = build(tmp_path, now=now, enforce_freshness=True)
    assert payload["data_health"]["production_safe"] is False
    assert payload["data_health"]["status"] == "DATA_DEGRADED_FAIL_CLOSED"
    assert payload["data_health"]["blockers"]


def test_t0_signal_dna_is_immutable_across_later_observations(tmp_path):
    now = datetime(2026, 9, 5, 18, 5, tzinfo=timezone.utc)
    seed(tmp_path, "2026-09-05T18:00:00+00:00", market_row(holder_growth_pct=10))
    _, first = build(tmp_path, now=now, enforce_freshness=True)
    write(tmp_path, "signal-dna-ledger.json", first)
    original = first["records"][0]["t0_signal_dna"]
    later = now + timedelta(minutes=20)
    seed(tmp_path, later.isoformat(), market_row(holder_growth_pct=45, smart_wallet_buy_count=8))
    _, second = build(tmp_path, now=later, enforce_freshness=True)
    rec = second["records"][0]
    assert rec["t0_signal_dna"] == original
    assert len(rec["observations"]) == 2


def test_distribution_is_explicit_phase_when_smart_wallets_are_selling(tmp_path):
    now = datetime(2026, 9, 5, 18, 5, tzinfo=timezone.utc)
    seed(tmp_path, "2026-09-05T18:00:00+00:00", market_row(smart_wallet_buy_count=1, smart_wallet_sell_count=5))
    payload, _ = build(tmp_path, now=now, enforce_freshness=True)
    row = payload["candidates"][0]
    assert row["wallet_intent"]["label"] == "DISTRIBUTION"
    assert row["revival_phase"]["phase"] == "DISTRIBUTION"


def test_self_learning_requires_holdout_validation_and_never_changes_production_gate():
    examples = []
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for i in range(40):
        winner = i % 2 == 0
        value = 0.9 if winner else 0.1
        examples.append({
            "t0_at": (base + timedelta(hours=i)).isoformat(),
            "features": {name: value for name in FEATURES},
            "winner_100": winner,
            "winner_300": winner and i % 4 == 0,
            "loss_50": not winner,
        })
    model = train(examples)
    assert model["sample_size"] == 40
    assert model["production_gate_effect"] is False
    assert model["status"] in {"VALIDATED_FOR_RANKING_ONLY", "VALIDATION_FAILED_SHADOW_ONLY"}
    if model["validated"]:
        assert model["ranking_effect"] is True
