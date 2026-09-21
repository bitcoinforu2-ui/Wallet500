from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unified_watch_engine as engine
import user_watch_final_buy as gate
import resilient_unified_watch_runner as runner


def test_exact_pair_survives_single_provider_429(monkeypatch):
    token = "0x3c6256f234ba638e5883c46b3fedb00ea2e66b8a"
    pair = "0xdce2e6fe348f8c8a2b08bbff8f447c64224d75fb"

    def fake_http(url):
        if "geckoterminal" in url:
            raise RuntimeError("HTTP Error 429: Too Many Requests")
        if "dexscreener" in url:
            return {
                "pairs": [{
                    "chainId": "bsc",
                    "pairAddress": pair,
                    "baseToken": {"address": token},
                    "quoteToken": {"address": "0x55d398326f99059ff775485246999027b3197955"},
                    "priceUsd": "0.00023545",
                    "liquidity": {"usd": 1900},
                    "volume": {"h1": 250, "h24": 30000},
                    "txns": {"h1": {"buys": 7, "sells": 5}},
                    "priceChange": {"h1": 4.2, "h24": 252.2},
                }]
            }
        raise AssertionError(url)

    monkeypatch.setattr(engine, "http_json", fake_http)
    snap = engine.live_exact_pair(
        {"network": "bsc", "contract": token, "pair": pair},
        2.0,
    )
    assert snap["price_source_count"] == 1
    assert snap["single_source_degraded"] is True
    assert snap["price_sources"] == ["dexscreener"]
    assert snap["price"] == 0.00023545
    assert snap["liquidity"] == 1900


def test_immutable_anchor_repairs_late_legacy_state():
    prev = {
        "quarter_wave_anchor_price": 0.00026431,
        "first_verified_price": 0.00026431,
        "first_verified_at": "2026-09-20T19:47:29+00:00",
        "first_seen_change_24h_pct": 252.0,
        "quarter_wave_revalidation_armed": True,
        "quarter_wave_revalidation_basis": "PERSISTED",
        "quarter_wave_revalidation_trigger_price": 0.00030989,
    }
    out = engine.quarter_wave_revalidation(
        prev,
        0.00023545,
        "2026-09-21T03:46:00+00:00",
        anchor_price=0.0000751,
        anchor_change_24h_pct=10.78,
        anchor_at="2026-09-20T14:15:55+00:00",
    )
    assert out["quarter_wave_anchor_repaired"] is True
    assert out["quarter_wave_anchor_price"] == 0.0000751
    assert out["first_verified_at"] == "2026-09-20T14:15:55+00:00"
    assert out["quarter_wave_late_discovery"] is False
    assert out["gain_from_first_verified_pct"] > 200
    assert out["quarter_wave_revalidation_basis"] == "ANCHOR_REPAIRED_FROM_IMMUTABLE_FIRST_SEEN"
    assert out["quarter_wave_trigger_price_is_threshold_estimate"] is True


def test_single_dex_source_requires_coherent_exact_cex_execution():
    policy = gate._policy({})
    target = {
        "candidate_type": "GATE_SPOT_DISCOVERY",
        "symbol": "MGT",
        "network": "bsc",
        "contract": "0x3c6256f234ba638e5883c46b3fedb00ea2e66b8a",
        "pair": "0xdce2e6fe348f8c8a2b08bbff8f447c64224d75fb",
        "quarter_wave_revalidation_lane": True,
        "quarter_wave_anchor_price_usd": 0.0000751,
        "quarter_wave_gain_from_anchor_pct": 213.0,
    }
    key = gate.identity_key(target)
    market = {
        "identity_key": key,
        "price": 0.00023545,
        "liquidity": 2000,
        "volume_h1": 100,
        "buys_h1": 2,
        "sells_h1": 2,
        "spread_pct": 0.0,
        "price_source_count": 1,
        "single_source_degraded": True,
        "observed_at": "2026-09-20T00:00:00+00:00",
        "cex_quote_volume_24h_usd": 300000,
        "cex_relative_volume_multiple": 10.0,
        "positive_gainer_rank": 1,
        "cex_execution_verified": False,
    }
    observed = {
        "identity_key": key,
        "market_verified": True,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": 20,
            "families": 1,
            "current_evidence_count": 5,
            "evidence_age_minutes": 1,
            "hard_risks": [],
            "family_scores": {"market_microstructure": 10, "holder_network": 0, "wallet_flow": 0},
        },
    }
    from datetime import datetime, timezone
    now = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)

    blocked, _ = gate.evaluate(target, market, observed, {}, policy, now=now)
    assert "PRICE_SOURCE_REDUNDANCY_MISSING" in blocked["blockers"]

    coherent = dict(market)
    coherent.update({
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "cex_market_price_spread_pct": 0.4,
        "cex_orderbook_spread_pct": 0.3,
        "cex_depth_1pct_usd": 12000,
        "cex_bid_ask_depth_ratio": 1.3,
    })
    allowed, _ = gate.evaluate(
        target,
        coherent,
        observed,
        {"last_price": 0.00023, "watch_low_price": 0.00020},
        policy,
        now=now,
    )
    assert "PRICE_SOURCE_REDUNDANCY_MISSING" not in allowed["blockers"]
    assert "CEX_DEX_PRICE_DIVERGENCE" not in allowed["blockers"]

    divergent = dict(coherent, cex_market_price_spread_pct=5.0)
    bad, _ = gate.evaluate(
        target,
        divergent,
        observed,
        {"last_price": 0.00023, "watch_low_price": 0.00020},
        policy,
        now=now,
    )
    assert "CEX_DEX_PRICE_DIVERGENCE" in bad["blockers"]


def test_cex_sensor_repairs_late_volume_baseline():
    target = {
        "candidate_type": "CEX_MARKET_DISCOVERY",
        "dynamic_spot_candidate": True,
        "symbol": "TRIO",
        "quote_volume_24h_usd": 44725.83,
        "first_seen_quote_volume_24h_usd": 9468.26,
        "positive_gainer_rank": 7,
    }
    previous = {
        # Legacy bug: this was captured after the wave was already running.
        "cex_quote_volume_baseline_usd": 44778.51,
        "cex_quote_volume_24h_usd": 44000.0,
        "positive_gainer_rank": 71,
    }
    sensor = engine.spot_cex_sensor(target, previous)
    assert sensor["baseline_source"] == "IMMUTABLE_FIRST_SEEN_VOLUME"
    assert sensor["baseline_repaired_from_first_seen"] is True
    assert sensor["baseline_volume_usd"] == 9468.26
    assert sensor["baseline_multiple"] > 4.7
    assert sensor["cex_led"] is True
    assert "CEX_RELATIVE_VOLUME_SHOCK" in sensor["triggers"]


def test_hot_exact_cex_candidate_is_marked_for_proactive_evidence_recovery(monkeypatch, tmp_path):
    import json
    dynamic = tmp_path / "dynamic.json"
    dynamic.write_text(json.dumps({
        "candidates": [{
            "candidate_type": "GATE_SPOT_DISCOVERY",
            "symbol": "R2",
            "network": "bsc",
            "contract": "0x223a20e1b83aa3832e78d4b7b132df022e739222",
            "pair": "0xfdbeffa804bc58e9edd720165f41a62b2ee251b6",
            "gain_from_first_seen_pct": 31.0,
            "discovery_momentum_change_pct": 40.0,
            "quote_volume_24h_usd": 50000,
            "positive_gainer_rank": 4,
        }]
    }))
    monkeypatch.setattr(engine, "DYNAMIC", dynamic)
    rows = engine.dynamic_candidates({})
    assert len(rows) == 1
    assert rows[0]["deep_investigation"] is True
    assert rows[0]["full_intelligence"] is True
    assert rows[0]["proactive_evidence_recovery"] is True
    assert rows[0]["collector_priority"] == 1


def test_missing_hot_cex_intelligence_triggers_bounded_deep_refresh(monkeypatch):
    key = "bsc:0x223a20e1b83aa3832e78d4b7b132df022e739222:0xfdbeffa804bc58e9edd720165f41a62b2ee251b6"
    target = {
        "candidate_type": "GATE_SPOT_DISCOVERY",
        "dynamic_spot_candidate": True,
        "deep_investigation": True,
        "symbol": "R2",
        "network": "bsc",
        "contract": "0x223a20e1b83aa3832e78d4b7b132df022e739222",
        "pair": "0xfdbeffa804bc58e9edd720165f41a62b2ee251b6",
    }
    runner._TARGETS_BY_IDENTITY = {key: target}
    runner._PREVIOUS_STATE = {"tokens": {}}
    runner._DEEP_DONE.clear()
    runner._DEEP_REPORTS.clear()
    runner._DEEP_FAILURES.clear()
    captured = {}

    def fake_run_one(engine_module, policy, t, live, previous_scan, triggers, base_reasons):
        captured["called"] = True
        return (
            {"identity_key": key, "qualification": ["TEST"]},
            {"identity_key": key},
        )

    monkeypatch.setattr(runner.deep_investigation_refresh, "run_one", fake_run_one)
    monkeypatch.setattr(
        runner,
        "identity_aware_fusion_summary",
        lambda row, notable_min_raw=0.30: {
            "_identity_key": key,
            "status": "CURRENT",
            "score": 12,
            "families": 1,
            "current_evidence_count": 5,
            "hard_risks": [],
            "family_scores": {"market_microstructure": 8},
        },
    )

    fusion = {
        "_identity_key": key,
        "status": "NOT_AVAILABLE",
        "score": None,
        "families": 0,
        "current_evidence_count": 0,
        "hard_risks": [],
        "family_scores": {},
    }
    refreshed = runner._refresh_deep_intelligence(
        {},
        {"buys_h1": 0, "sells_h1": 0},
        fusion,
        [],
        [],
        {
            "deep_investigation_max_targets_per_cycle": 8,
            "real_alert_min_current_evidence": 2,
            "real_alert_relaxed_min_positive_families_with_wallet_or_new_intel": 2,
        },
    )
    assert refreshed is True
    assert captured["called"] is True
    assert fusion["status"] == "CURRENT"
    assert fusion["current_evidence_count"] == 5


def test_market_row_prefers_freshest_duplicate_exact_identity():
    key = "bsc:0xabc:0xpair"
    stale = {
        "identity_key": key,
        "candidate_type": "PUBLIC_ALPHA",
        "observed_at": "2026-09-18T13:52:51+00:00",
        "price": 0.0301,
    }
    fresh = {
        "identity_key": key,
        "candidate_type": "GATE_SPOT_DISCOVERY",
        "dynamic_spot_candidate": True,
        "observed_at": "2026-09-21T14:16:36+00:00",
        "price": 0.0407,
        "cex_execution_verified": True,
    }
    state = {"tokens": {"ALPHA:" + key: stale, "SPOT:" + key: fresh}}
    selected = gate.market_row(state, key)
    assert selected is fresh
    assert selected["price"] == 0.0407


def test_hybrid_continuation_accepts_strong_absolute_turnover_fallback():
    from datetime import datetime, timezone

    policy = gate._policy({})
    target = {
        "candidate_type": "GATE_SPOT_DISCOVERY",
        "symbol": "RHEA",
        "network": "bsc",
        "contract": "0x4c067de26475e1cefee8b8d1f6e2266b33a2372e",
        "pair": "0x05f4a518fe9271cb45d4a1d708ece2ac04bc6a6c",
        "quarter_wave_revalidation_lane": True,
        "quarter_wave_anchor_price_usd": 0.014385,
        "quarter_wave_gain_from_anchor_pct": 180.0,
    }
    key = gate.identity_key(target)
    now = datetime(2026, 9, 21, 14, 20, tzinfo=timezone.utc)
    market = {
        "identity_key": key,
        "price": 0.0408,
        "liquidity": 515000,
        "volume_h1": 206000,
        "buys_h1": 636,
        "sells_h1": 328,
        "spread_pct": 0.35,
        "observed_at": now.isoformat(),
        "price_source_count": 2,
        "cex_quote_volume_24h_usd": 321000,
        "cex_relative_volume_multiple": 1.25,
        "positive_gainer_rank": 7,
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "cex_market_price_spread_pct": 0.25,
        "cex_orderbook_spread_pct": 1.0,
        "cex_depth_1pct_usd": 900,
        "cex_bid_ask_depth_ratio": 4.0,
    }
    observed = {
        "identity_key": key,
        "market_verified": True,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": 7,
            "families": 1,
            "current_evidence_count": 20,
            "evidence_age_minutes": 1,
            "hard_risks": [],
            "family_scores": {
                "market_microstructure": 15,
                "wallet_flow": 0,
                "holder_network": 0,
            },
        },
    }
    decision, _ = gate.evaluate(
        target,
        market,
        observed,
        {"last_price": 0.0400, "watch_low_price": 0.0350},
        policy,
        now=now,
    )
    assert decision["quarter_wave_revalidation"]["hybrid_breakout_continuation"] is True
    assert "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET" not in decision["blockers"]
    assert decision["pre_buy"] is True


def test_stale_prior_market_snapshot_is_not_treated_as_scan_to_scan_chase():
    from datetime import datetime, timedelta, timezone

    policy = gate._policy({})
    target = {
        "symbol": "TEST",
        "network": "bsc",
        "contract": "0xabc",
        "pair": "0xpair",
    }
    key = gate.identity_key(target)
    now = datetime(2026, 9, 21, 14, 20, tzinfo=timezone.utc)
    market = {
        "identity_key": key,
        "price": 0.0100,
        "liquidity": 70000,
        "volume_h1": 50000,
        "buys_h1": 300,
        "sells_h1": 200,
        "spread_pct": 0.1,
        "observed_at": now.isoformat(),
    }
    observed = {
        "identity_key": key,
        "market_verified": True,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": 60,
            "families": 3,
            "current_evidence_count": 10,
            "evidence_age_minutes": 1,
            "hard_risks": [],
            "family_scores": {
                "market_microstructure": 10,
                "wallet_flow": 5,
                "holder_network": 0,
            },
        },
    }
    decision, state = gate.evaluate(
        target,
        market,
        observed,
        {
            "last_price": 0.0070,
            "watch_low_price": 0.0070,
            "last_market_observed_at": (now - timedelta(hours=3)).isoformat(),
        },
        policy,
        now=now,
    )
    assert "NEED_SECOND_VERIFIED_SCAN" in decision["blockers"]
    assert "SHORT_TERM_CHASE_RISK" not in decision["blockers"]
    assert state["last_market_observed_at"] == now.isoformat()
