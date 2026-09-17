from datetime import datetime, timezone

from wallet500 import market_cross_check as mcc


MINT = "3DmF2srrZX1d47W1x7JQn49yk6QwEWoJBNkRvJ3Ppump"
NOW = datetime(2026, 9, 17, 18, 0, 0, tzinfo=timezone.utc)


def snap(source, *, role="verifier", at="2026-09-17T17:59:30+00:00", **metrics):
    return mcc.MarketSnapshot(
        chain="solana",
        token=MINT,
        source=source,
        role=role,
        observed_at=at,
        **metrics,
    )


def test_matching_independent_source_is_ok():
    result = mcc.cross_check_asset([
        snap("wallet500", role="primary", price_usd=0.001, liquidity_usd=100_000, holders=1800, top10_pct=31.0),
        snap("provider_b", price_usd=0.00102, liquidity_usd=103_000, holders=1820, top10_pct=31.5),
    ], now=NOW)
    assert result["status"] == "ok"
    assert result["agreement_score"] == 1.0
    assert result["discrepancies"] == []
    assert set(result["compared_fields"]) == {"holders", "liquidity_usd", "price_usd", "top10_pct"}


def test_large_market_data_difference_is_flagged():
    result = mcc.cross_check_asset([
        snap("wallet500", role="primary", price_usd=0.001, liquidity_usd=100_000, market_cap_usd=1_000_000),
        snap("provider_b", price_usd=0.00101, liquidity_usd=55_000, market_cap_usd=700_000),
    ], now=NOW)
    assert result["status"] == "diverged"
    fields = {row["field"] for row in result["discrepancies"]}
    assert "liquidity_usd" in fields
    assert "market_cap_usd" in fields
    assert 0 <= result["agreement_score"] < 1


def test_stale_verifier_does_not_vote():
    result = mcc.cross_check_asset([
        snap("wallet500", role="primary", at="2026-09-17T17:59:30+00:00", price_usd=0.001),
        snap("provider_b", at="2026-09-17T17:40:00+00:00", price_usd=0.003),
    ], now=NOW)
    assert result["status"] == "stale"
    assert result["agreement_score"] is None
    assert result["stale_sources"] == ["provider_b"]


def test_one_source_is_insufficient_not_false_confirmation():
    result = mcc.cross_check_asset([
        snap("wallet500", role="primary", price_usd=0.001, liquidity_usd=100_000),
    ], now=NOW)
    assert result["status"] == "insufficient"
    assert result["agreement_score"] is None


def test_token_aggregate_never_confirms_exact_pair():
    result = mcc.cross_check_asset([
        snap("wallet500", role="primary", market_scope="exact_pair", pair_address="PAIR_A", price_usd=0.001),
        snap("binance_web3", market_scope="token_aggregate", price_usd=0.001),
    ], now=NOW)
    assert result["status"] == "scope_mismatch"
    assert result["agreement_score"] is None
    assert result["scope_mismatch_sources"] == ["binance_web3"]


def test_different_exact_pairs_never_cross_confirm():
    result = mcc.cross_check_asset([
        snap("wallet500", role="primary", market_scope="exact_pair", pair_address="PAIR_A", price_usd=0.001),
        snap("provider_b", market_scope="exact_pair", pair_address="PAIR_B", price_usd=0.001),
    ], now=NOW)
    assert result["status"] == "scope_mismatch"
    assert result["agreement_score"] is None


def test_builder_keeps_exact_chain_mint_identity_and_risk_flags():
    raw = [
        {
            "chain": "sol",
            "mint": MINT,
            "source": "wallet500",
            "role": "primary",
            "observed_at": "2026-09-17T17:59:30+00:00",
            "price_usd": 0.001,
            "holders": 1800,
        },
        {
            "chain": "solana",
            "token": MINT,
            "provider": "provider_b",
            "observed_at": "2026-09-17T17:59:35+00:00",
            "price_usd": 0.00101,
            "holder_count": 1810,
            "risk_flags": ["mint_authority_present"],
        },
    ]
    payload = mcc.build(raw, ts="2026-09-17T18:00:00+00:00")
    asset = payload["assets"][f"solana:{MINT}"]
    assert asset["status"] == "ok"
    assert asset["risk_flags"] == ["mint_authority_present"]
    assert payload["automatic_trade"] is False
    assert payload["policy"]["price_integrity_tolerance"] == 0.02
