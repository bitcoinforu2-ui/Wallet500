from datetime import datetime, timezone

from scripts import early_kol_convergence as mod


def event(wallet, sig, cap, ts, mint="MINT"):
    return {
        "wallet_id": wallet,
        "wallet_name": wallet,
        "mint": mint,
        "side": "BUY",
        "signature": sig,
        "block_time": ts,
        "entry_market_cap_usd": cap,
    }


def test_three_independent_under_100k_triggers_deep_scan():
    now = datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)
    meta = {x: {"name": x, "independence_group": x} for x in ("a", "b", "c")}
    rows = [
        event("a", "s1", 11900, now.timestamp() - 600),
        event("b", "s2", 28100, now.timestamp() - 300),
        event("c", "s3", 29400, now.timestamp() - 60),
    ]
    out = mod.convergence_for_mint(rows, "MINT", meta, now=now)
    assert out["signal_state"] == "EARLY_KOL_DEEP_SCAN"
    assert out["emergency_deep_scan"] is True
    assert out["independent_groups_under_100k"] == 3
    assert out["automatic_buy"] is False


def test_shared_transaction_dedupes_independence():
    now = datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)
    meta = {x: {"name": x, "independence_group": x} for x in ("a", "b", "c")}
    rows = [
        event("a", "shared", 20000, now.timestamp() - 600),
        event("b", "shared", 25000, now.timestamp() - 300),
        event("c", "s3", 30000, now.timestamp() - 60),
    ]
    out = mod.convergence_for_mint(rows, "MINT", meta, now=now)
    assert out["signal_state"] == "EARLY_KOL_CONVERGENCE_WATCH"
    assert out["emergency_deep_scan"] is False
    assert out["independent_groups_under_100k"] == 2


def test_exact_market_rejects_ticker_only_or_quote_side():
    rows = [
        {
            "chainId": "solana",
            "baseToken": {"address": "OTHER", "symbol": "MINT"},
            "quoteToken": {"address": "MINT"},
            "priceUsd": "1",
            "liquidity": {"usd": 10000},
            "pairAddress": "P1",
        },
        {
            "chainId": "solana",
            "baseToken": {"address": "MINT", "symbol": "REAL"},
            "quoteToken": {"address": "Q"},
            "priceUsd": "0.1",
            "liquidity": {"usd": 9000},
            "pairAddress": "P2",
            "marketCap": 90000,
        },
    ]
    market = mod.exact_solana_market(rows, "MINT", 5000)
    assert market["pair"] == "P2"
    assert market["symbol"] == "REAL"
    assert market["market_cap_usd"] == 90000


def test_two_independent_is_watch_not_buy():
    now = datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)
    meta = {x: {"name": x, "independence_group": x} for x in ("a", "b")}
    rows = [
        event("a", "s1", 120000, now.timestamp() - 500),
        event("b", "s2", 180000, now.timestamp() - 100),
    ]
    out = mod.convergence_for_mint(rows, "MINT", meta, now=now)
    assert out["signal_state"] == "EARLY_KOL_CONVERGENCE_WATCH"
    assert out["emergency_deep_scan"] is False
    assert out["production_promotion_allowed"] is False
