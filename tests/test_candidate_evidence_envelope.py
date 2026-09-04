import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500.candidate_evidence_envelope import build


NOW = datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc)
TOKEN = "Mint111111111111111111111111111111111111111"
PAIR = "Pair111111111111111111111111111111111111111"


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def seed_revival(root: Path):
    write(root, "revival-1000-latest.json", {
        "generated_at": "2026-09-04T23:50:00+00:00",
        "coins": [{
            "network": "solana",
            "network_verified": True,
            "token_address": TOKEN,
            "symbol": "OLD",
            "dex_pair_address": PAIR,
            "dex_link": "https://dexscreener.com/solana/" + PAIR,
            "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
            "dex_pair_liquidity_usd": 120000,
            "dex_pair_volume_24h_usd": 250000,
            "market_age_verified": True,
            "market_age_min_days": 900,
            "revival_score_verified": 72,
            "watch_status": "WAKING_MARKET_ONLY",
            "drawdown_from_ath_pct": 88,
            "revival_score_components": {
                "same_pair_as_previous": True,
                "liquidity_change_pct": 4,
                "pair_volume_change_pct": 22,
            },
        }],
    })


def seed_supporting_evidence(root: Path, generated_at="2026-09-04T23:55:00+00:00"):
    write(root, "revival-holder-latest.json", {
        "generated_at": generated_at,
        "coins": [{
            "token_address": TOKEN,
            "holder_truth_status": "FORWARD_VERIFIED",
            "growth_eligible": True,
            "holder_count": 1000,
            "holder_growth_24h_ready": True,
            "holder_growth_24h_count": 25,
            "holder_growth_24h_pct": 2.5,
            "holder_growth_7d_ready": False,
        }],
    })
    write(root, "revival-prewaking-wallet-evidence.json", {
        "generated_at": generated_at,
        "tokens": [{
            "token_address": TOKEN,
            "exact_pair": PAIR,
            "coverage": {
                "coverage_quality": "ACCEPTABLE",
                "coverage_gap": False,
                "last_run_resolution_pct": 100,
                "minimum_resolution_pct": 80,
            },
            "windows": {"h1": {
                "resolved_swaps": 12,
                "unique_traders": 10,
                "first_seen_buyers_since_monitor_t0": 5,
                "net_accumulating_wallets": 6,
                "net_distributing_wallets": 3,
                "wallet_buy_sell_ratio": 1.5,
            }},
        }],
    })


def seed_empty_optional(root: Path):
    for name, payload in {
        "revival-wallet-registry.json": {"generated_at": "2026-09-04T23:55:00+00:00", "event_bridge": []},
        "revival-precursor-latest.json": {"generated_at": "2026-09-04T23:55:00+00:00", "targets": []},
        "waking-confirmation-latest.json": {"generated_at": "2026-09-04T23:55:00+00:00", "targets": []},
        "cex-revival-radar.json": {"generated_at": "2026-09-04T23:55:00+00:00", "alerts": []},
        "revival-pre-t0-evidence.json": {"generated_at": "2026-09-04T23:55:00+00:00", "active_deep_watch": []},
    }.items():
        write(root, name, payload)


def test_verified_holder_and_wallet_evidence_promotes_to_evidence_ready(tmp_path):
    seed_revival(tmp_path)
    seed_supporting_evidence(tmp_path)
    seed_empty_optional(tmp_path)
    result = build(tmp_path, now=NOW)
    assert result["counts"]["evidence_ready"] == 1
    row = result["candidates"][0]
    assert row["status"] == "EVIDENCE_READY"
    assert row["production_effect"] is False
    assert row["automatic_buy"] is False
    assert set(row["coverage"]["positive_independent_lanes"]) == {"HOLDER_GROWTH", "WALLET_ACCUMULATION"}
    assert row["families"]["concentration"]["positive"] is False


def test_stale_supporting_evidence_cannot_promote(tmp_path):
    seed_revival(tmp_path)
    seed_supporting_evidence(tmp_path, generated_at="2026-09-04T18:00:00+00:00")
    seed_empty_optional(tmp_path)
    result = build(tmp_path, now=NOW)
    row = result["candidates"][0]
    assert row["status"] == "VERIFIED_WATCH"
    assert row["coverage"]["positive_independent_count"] == 0
    assert "NO_INDEPENDENT_POSITIVE_EVIDENCE" in row["blockers"]


def test_unverified_holder_source_is_never_counted_positive(tmp_path):
    seed_revival(tmp_path)
    seed_supporting_evidence(tmp_path)
    seed_empty_optional(tmp_path)
    holder = {
        "generated_at": "2026-09-04T23:55:00+00:00",
        "coins": [{
            "token_address": TOKEN,
            "holder_truth_status": "QUARANTINED_PROVIDER_SEMANTICS",
            "growth_eligible": False,
            "holder_count": None,
            "raw_rugcheck_holder_count": 999999,
        }],
    }
    write(tmp_path, "revival-holder-latest.json", holder)
    result = build(tmp_path, now=NOW)
    row = result["candidates"][0]
    assert row["families"]["holder_growth"]["verified"] is False
    assert row["families"]["holder_growth"]["positive"] is False
    assert "HOLDER_GROWTH" not in row["coverage"]["positive_independent_lanes"]
