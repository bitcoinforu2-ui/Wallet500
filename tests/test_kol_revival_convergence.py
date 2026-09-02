from datetime import datetime, timezone

from wallet500.kol_revival_convergence import (
    build_effective_independence_groups,
    convergence_for_mint,
    verified_swap_evidence,
    verify_exact_mint_market,
)


MINT = "Mint111111111111111111111111111111111111111"


def _pair(created_ms, liq=120000, price="1.25"):
    return {
        "chainId": "solana",
        "pairAddress": "Pair111",
        "pairCreatedAt": created_ms,
        "dexId": "testdex",
        "url": "https://dex.example/pair",
        "baseToken": {"address": MINT},
        "quoteToken": {"address": "So11111111111111111111111111111111111111112"},
        "priceUsd": price,
        "liquidity": {"usd": liq},
    }


def _config():
    return {
        "convergence_windows_minutes": [15, 30],
        "thresholds": [2, 3, 4, 5],
        "wallets": [
            {"id": "A", "name": "A", "independence_group": "G1"},
            {"id": "B", "name": "B", "independence_group": "G2"},
            {"id": "C", "name": "C", "independence_group": "G3"},
            {"id": "D", "name": "D", "independence_group": "G3"},
        ],
    }


def _event(wallet, minute, sig, *, group=None, effective=None):
    base = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc).timestamp()
    row = {
        "side": "BUY",
        "mint": MINT,
        "wallet_id": wallet,
        "independence_group": group or wallet,
        "signature": sig,
        "block_time": base + minute * 60,
    }
    if effective:
        row["effective_independence_group"] = effective
    return row


def test_market_verifier_requires_exact_old_mint_and_liquidity():
    now_ms = 2_000_000_000_000
    old = now_ms - 220 * 86400 * 1000
    out = verify_exact_mint_market([_pair(old)], MINT, now_ms=now_ms)
    assert out["exact_mint_verified"] is True
    assert out["market_age_verified"] is True
    assert out["market_age_min_days"] >= 220
    assert out["liquidity_pass"] is True
    assert out["pair_address"] == "Pair111"


def test_market_verifier_blocks_young_or_low_liquidity():
    now_ms = 2_000_000_000_000
    young = now_ms - 179 * 86400 * 1000
    out = verify_exact_mint_market([_pair(young, liq=9000)], MINT, now_ms=now_ms)
    assert out["market_age_verified"] is False
    assert out["liquidity_pass"] is False


def test_three_independent_wallets_create_strong_mature_watch():
    events = [_event("A", 0, "s1"), _event("B", 6, "s2"), _event("C", 12, "s3")]
    market = {"market_age_verified": True, "market_age_min_days": 500, "liquidity_pass": True, "liquidity_usd": 150000}
    now = datetime(2026, 9, 2, 12, 13, tzinfo=timezone.utc)
    out = convergence_for_mint(events, MINT, _config(), market, now=now)
    assert out is not None
    assert out["independent_wallet_groups"] == 3
    assert out["independent_count_by_window"]["15"] == 3
    assert out["signal_state"] == "KOL_REVIVAL_CONVERGENCE_STRONG"
    assert out["eligible_research_watch"] is True
    assert out["production_portfolio_impact"] == "NONE"
    assert out["automatic_buy"] is False


def test_linked_wallet_group_counts_once_and_repeat_buy_is_separate_signal():
    events = [
        _event("A", 0, "s1"),
        _event("A", 3, "s1b"),
        _event("C", 5, "s2"),
        _event("D", 8, "s3"),
    ]
    market = {"market_age_verified": True, "liquidity_pass": True}
    out = convergence_for_mint(events, MINT, _config(), market, now=datetime(2026, 9, 2, 12, 9, tzinfo=timezone.utc))
    assert out is not None
    assert out["independent_wallet_groups"] == 2
    assert out["signal_state"] == "KOL_REVIVAL_CONVERGENCE_WATCH"
    assert out["repeat_accumulator_count"] == 1
    assert out["repeat_accumulators"] == ["A"]


def test_shared_recent_signature_auto_links_wallets_and_link_is_sticky():
    cfg = {
        "wallets": [
            {"id": "A", "independence_group": "A"},
            {"id": "B", "independence_group": "B"},
            {"id": "C", "independence_group": "C"},
        ]
    }
    mapping, links, clusters = build_effective_independence_groups(
        {"A": {"shared", "a1"}, "B": {"shared", "b1"}, "C": {"c1"}}, cfg
    )
    assert mapping["A"] == mapping["B"]
    assert mapping["A"] != mapping["C"]
    assert len(clusters) == 1
    assert set(clusters[0]["wallet_ids"]) == {"A", "B"}
    assert links and links[0]["reason"] == "SHARED_RECENT_SOLANA_TRANSACTION"

    # Once observed, the conservative link remains even when it falls out of the recent RPC window.
    mapping2, _, _ = build_effective_independence_groups(
        {"A": {"a2"}, "B": {"b2"}, "C": {"c2"}}, cfg, links
    )
    assert mapping2["A"] == mapping2["B"]


def test_effective_auto_link_group_overrides_configured_independence():
    events = [
        _event("A", 0, "s1", effective="AUTO:A+B"),
        _event("B", 2, "s2", effective="AUTO:A+B"),
        _event("C", 4, "s3", effective="C"),
    ]
    market = {"market_age_verified": True, "liquidity_pass": True}
    out = convergence_for_mint(events, MINT, _config(), market, now=datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc))
    assert out is not None
    assert out["independent_wallet_groups"] == 2
    assert out["signal_state"] == "KOL_REVIVAL_CONVERGENCE_WATCH"


def test_mature_or_liquidity_failures_never_become_eligible_signal():
    events = [_event("A", 0, "s1"), _event("B", 2, "s2"), _event("C", 4, "s3")]
    age_block = convergence_for_mint(events, MINT, _config(), {"market_age_verified": False, "liquidity_pass": True}, now=datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc))
    liq_block = convergence_for_mint(events, MINT, _config(), {"market_age_verified": True, "liquidity_pass": False}, now=datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc))
    assert age_block["signal_state"] == "AGE_BLOCKED"
    assert age_block["eligible_research_watch"] is False
    assert liq_block["signal_state"] == "LIQUIDITY_BLOCKED"
    assert liq_block["eligible_research_watch"] is False


def test_verified_swap_evidence_fails_closed_without_swap_route_log():
    no_swap = {"meta": {"logMessages": ["Program log: Instruction: Transfer"]}}
    yes_swap = {"meta": {"logMessages": ["Program log: Instruction: SharedAccountsRoute"]}}
    assert verified_swap_evidence(no_swap) is None
    assert verified_swap_evidence(yes_swap) == "INSTRUCTION: SHAREDACCOUNTSROUTE"
