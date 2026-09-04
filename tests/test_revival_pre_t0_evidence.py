import json
from pathlib import Path

from wallet500.revival_pre_t0_evidence import run as run_evidence
from wallet500.waking_pre_t0_confirmation import shadow_status

TOKEN = "11111111111111111111111111111111"
PAIR = "22222222222222222222222222222222"


def write(data: Path, name: str, payload: dict) -> None:
    (data / name).write_text(json.dumps(payload), encoding="utf-8")


def seed(data: Path, status: str = "DEEP_WATCH", generated_at: str = "2026-09-04T10:00:00+00:00") -> None:
    write(data, "revival-1000-latest.json", {
        "network": "solana", "no_hindsight": True, "production_portfolio_impact": "NONE",
        "generated_at": generated_at,
        "coins": [{
            "token_address": TOKEN, "dex_pair_address": PAIR, "symbol": "TEST",
            "market_age_verified": True, "market_age_min_days": 200,
            "watch_status": status, "revival_score_verified": 72,
        }],
    })
    write(data, "revival-holder-latest.json", {
        "generated_at": "2026-09-04T09:59:00+00:00",
        "coins": [{
            "token_address": TOKEN, "growth_eligible": True, "holder_truth_status": "FORWARD_VERIFIED",
            "source": "TEST_TRUSTED", "first_holder_count": 100, "holder_count": 110,
            "holder_growth_count": 10, "holder_growth_pct": 10.0,
        }],
    })
    write(data, "revival-prewaking-wallet-evidence.json", {
        "generated_at": "2026-09-04T09:59:00+00:00",
        "tokens": [{
            "token_address": TOKEN, "exact_pair": PAIR,
            "coverage": {"coverage_quality": "ACCEPTABLE", "coverage_gap": False},
            "windows": {
                "h1": {"net_accumulating_wallets": 4, "net_distributing_wallets": 1, "unique_buyers": 4, "wallet_buy_sell_ratio": 2.0},
                "h4": {},
            },
            "top_wallets_raw_verified": [{"wallet": "W1", "buys": 2, "sells": 0, "net_token_delta": 10}],
        }],
    })
    write(data, "revival-wallet-registry.json", {
        "generated_at": "2026-09-04T09:59:00+00:00",
        "wallets": [{"wallet": "W1", "tier_current": {"tier": "STRONG", "completed_pre_waking_buy_exposures": 5}}],
    })
    write(data, "holder-concentration-shadow.json", {
        "generated_at": "2026-09-04T09:59:00+00:00",
        "rows": [{"token_address": TOKEN, "verified": True, "top10_pct": 45.0, "concentration_risk_score": 25}],
    })
    write(data, "social-organic-acceleration.json", {
        "updated_at": "2026-09-04T09:59:00+00:00",
        "tokens": [{"chain": "solana", "contract": TOKEN, "status": "ORGANIC_ACCELERATION", "organic_acceleration_score": 70}],
    })


def test_pre_t0_capture_then_immutable_waking_binding(tmp_path):
    seed(tmp_path)
    first = run_evidence(tmp_path, "2026-09-04T10:00:30+00:00")
    assert first["counts"]["records_appended_this_run"] == 1
    snap = first["active_deep_watch"][0]
    assert snap["families"]["holder_acceleration"]["positive"] is True
    assert snap["families"]["independent_wallet_accumulation"]["positive"] is True
    assert snap["families"]["smart_money"]["positive"] is True
    assert snap["families"]["organic_social"]["positive"] is True
    assert snap["families"]["concentration"]["positive"] is False

    revival = json.loads((tmp_path / "revival-1000-latest.json").read_text())
    revival["generated_at"] = "2026-09-04T10:05:00+00:00"
    write(tmp_path, "revival-1000-latest.json", revival)
    second = run_evidence(tmp_path, "2026-09-04T10:05:30+00:00")
    assert second["counts"]["records_appended_this_run"] == 0

    revival["generated_at"] = "2026-09-04T10:10:00+00:00"
    revival["coins"][0]["watch_status"] = "WAKING_MARKET_ONLY"
    write(tmp_path, "revival-1000-latest.json", revival)
    waking = run_evidence(tmp_path, "2026-09-04T10:10:30+00:00")
    binding = waking["active_waking_bindings"][0]
    assert binding["status"] == "BOUND_TO_PRE_WAKING_EVIDENCE"
    assert binding["pre_t0_record_id"] == snap["record_id"]
    assert binding["snapshot"]["captured_at"] < binding["waking_first_seen_at"]

    holder = json.loads((tmp_path / "revival-holder-latest.json").read_text())
    holder["generated_at"] = "2026-09-04T10:11:00+00:00"
    holder["coins"][0]["holder_count"] = 999
    write(tmp_path, "revival-holder-latest.json", holder)
    again = run_evidence(tmp_path, "2026-09-04T10:12:00+00:00")
    assert again["active_waking_bindings"][0]["pre_t0_record_id"] == snap["record_id"]
    assert again["active_waking_bindings"][0]["snapshot"]["families"]["holder_acceleration"]["holder_count"] == 110


def test_waking_without_prior_capture_is_never_backfilled(tmp_path):
    seed(tmp_path, status="WAKING_MARKET_ONLY")
    out = run_evidence(tmp_path, "2026-09-04T10:00:30+00:00")
    binding = out["active_waking_bindings"][0]
    assert binding["status"] == "MISSING_PRE_T0_NO_BACKFILL_ALLOWED"
    assert binding["snapshot"] is None
    status, metrics = shadow_status(binding)
    assert status == "MISSING_PRE_T0_NO_BACKFILL"
    assert metrics["verified_families"] == 0


def test_shadow_confirmation_is_research_only():
    binding = {
        "status": "BOUND_TO_PRE_WAKING_EVIDENCE",
        "snapshot": {
            "coverage": {"verified_families": 4, "positive_families_excluding_concentration": 3},
            "families": {"concentration": {"concentration_risk_score": 20}},
        },
    }
    status, metrics = shadow_status(binding)
    assert status == "PRE_T0_STRONG_SHADOW"
    assert metrics["positive_families"] == 3
