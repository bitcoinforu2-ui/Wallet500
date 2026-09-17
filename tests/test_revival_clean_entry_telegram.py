from __future__ import annotations

import json
from datetime import datetime, timezone

from wallet500 import revival_clean_entry_telegram as mod

NOW = datetime(2026, 9, 16, 14, 30, tzinfo=timezone.utc)


def _row(*, buys=120, sells=80, source_price=1.35, live_price=1.35):
    return {
        "network": "solana",
        "network_verified": True,
        "token_address": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "dex_pair_address": "2AXXcN6oN9bBT5owwmTH53C7QHUxvhLeu718Kqt8rvY2",
        "pair_address": "2AXXcN6oN9bBT5owwmTH53C7QHUxvhLeu718Kqt8rvY2",
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "base_token_symbol": "RAY",
        "market_age_verified": True,
        "market_age_min_days": 1830,
        "liquidity_usd": 2_600_000,
        "revival_score": 73.8,
        "price_usd": source_price,
        "active_display_gate": {"pass": True},
        "url": "https://dexscreener.com/solana/2axxc",
        "_test_live": {
            "price_usd": live_price,
            "liquidity_usd": 2_600_000,
            "volume_h1": 704_200,
            "buys_h1": buys,
            "sells_h1": sells,
            "base_token_address": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        },
    }


def _fake_with_live(row):
    out = dict(row)
    live = dict(out.get("_test_live") or {})
    out["live_h1"] = live
    out["liquidity_usd"] = live.get("liquidity_usd")
    return out


def test_clean_entry_requires_buyers_to_lead(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.revival, "_with_live", _fake_with_live)
    ok, _, meta = mod._clean_meta(_row(buys=120, sells=80), tmp_path, NOW)
    assert ok is True
    assert meta["buy_sell_ratio_h1"] == 1.5
    assert meta["live_price_usd"] == 1.35

    ok, _, meta = mod._clean_meta(_row(buys=80, sells=120), tmp_path, NOW)
    assert ok is False
    assert "BUYERS_NOT_LEADING_H1" in meta["blockers"]
    assert "BUY_SELL_RATIO_BELOW_CLEAN_THRESHOLD" in meta["blockers"]


def test_clean_entry_blocks_source_live_price_divergence(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.revival, "_with_live", _fake_with_live)
    ok, _, meta = mod._clean_meta(_row(source_price=1.35, live_price=1.25), tmp_path, NOW)
    assert ok is False
    assert meta["source_live_price_diff_pct"] == 8.0
    assert "SOURCE_LIVE_PRICE_DIVERGENCE" in meta["blockers"]


def test_clean_entry_blocks_fresh_cross_venue_dispersion(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.revival, "_with_live", _fake_with_live)
    (tmp_path / mod.FRAGMENTATION).write_text(json.dumps({
        "generated_at": NOW.isoformat(),
        "current_shadow_candidates": [{
            "symbol": "RAYUSDT",
            "observed_at": NOW.isoformat(),
            "price_dispersion_pct": 7.1,
            "shadow_features": ["CROSS_VENUE_PRICE_DISPERSION_SHADOW"],
        }],
    }), encoding="utf-8")
    ok, _, meta = mod._clean_meta(_row(), tmp_path, NOW)
    assert ok is False
    assert "FRESH_CROSS_VENUE_PRICE_RISK" in meta["blockers"]


def test_clean_entry_is_research_only_and_never_sends_telegram(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.revival, "_with_live", _fake_with_live)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    def forbidden_send(*args, **kwargs):
        raise AssertionError("legacy clean-entry lane must never send Telegram")

    monkeypatch.setattr(mod.revival, "_send", forbidden_send)
    src = tmp_path / mod.SOURCE
    src.write_text(json.dumps([_row()]), encoding="utf-8")

    first = mod.run(str(tmp_path), now=NOW)
    again = mod.run(str(tmp_path), now=NOW)

    assert first["baseline_count"] == 1
    assert first["delivered_count"] == 0
    assert again["delivered_count"] == 0
    assert first["configured"] is False
    assert first["truth_contract"]["research_only"] is True
    assert first["truth_contract"]["actionable_only"] is False
    assert first["truth_contract"]["telegram_delivery_forbidden"] is True
    assert first["truth_contract"]["delivery_lane"] == "UNIFIED_WATCH_ENGINE_ONLY"
