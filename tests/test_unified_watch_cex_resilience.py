from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unified_watch_engine as engine
import user_watch_final_buy as gate


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
