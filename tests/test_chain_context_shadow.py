from __future__ import annotations

from scripts import chain_context_shadow as mod


def test_chain_benchmark_mapping_is_explicit_and_shadow_only():
    assert mod.benchmark_for_network("ethereum") == "ETH"
    assert mod.benchmark_for_network("base") == "ETH"
    assert mod.benchmark_for_network("arbitrum") == "ARB"
    assert mod.benchmark_for_network("bsc") == "BNB"
    assert mod.benchmark_for_network("solana") == "SOL"
    assert mod.benchmark_for_network("arc") is None


def test_gate_candles_parse_close_and_sort():
    rows = [
        ["2000", "99", "102.0", "105", "98", "100"],
        ["1000", "77", "100.0", "101", "96", "97"],
    ]
    assert mod.parse_gate_candles(rows) == [(1000.0, 100.0), (2000.0, 102.0)]


def test_relative_strength_and_shadow_flags():
    context = mod.token_event_relative(
        10.0,
        15.0,
        {"event_at": "2026-09-21T10:00:00+00:00", "network_since_event_pct": 10.0},
    )
    assert context["token_since_event_pct"] == 50.0
    assert context["relative_strength_since_event_pct"] == 40.0

    flags = mod.build_flags(
        token_since_discovery=10.0,
        network_since_discovery=-2.0,
        relative_since_discovery=12.0,
        network_since_final_buy=-3.0,
    )
    assert "TOKEN_UP_NETWORK_DOWN" in flags
    assert "RELATIVE_STRENGTH_POSITIVE" in flags
    assert "POST_BUY_NETWORK_DETERIORATION" in flags


def test_real_alert_research_groups_by_pre_entry_network_regime():
    base = 1_800_000_000
    candles = [(base + i * 3600, 100.0 + i) for i in range(60)]
    entry = mod.iso_from_ts(base + 30 * 3600)
    ledger = {
        "positions": [{
            "symbol": "TEST",
            "chain": "ethereum",
            "entry_time": entry,
            "checkpoints": {"24h": {"return_pct": 20.0}},
        }]
    }
    research = mod.build_real_alert_research(ledger, {"ETH": {"candles_1h": candles}})
    assert research["sample_size"] == 1
    assert research["buy_gate_effect"] is False
    assert research["groups"]["RISING"]["n"] == 1
    assert research["groups"]["RISING"]["positive_24h_pct"] == 100.0
