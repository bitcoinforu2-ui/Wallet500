import json

from wallet500.smart_buyer_conviction import BuyerObservation, build, score_buyers


def obs(wallet: str, **overrides):
    payload = {
        "wallet": wallet,
        "buy_usd": 5_000,
        "sell_usd": 500,
        "current_position_usd": 4_500,
        "realized_pnl_30d": 12_000,
        "win_rate_30d": 0.72,
        "trades_30d": 50,
        "winners_2x_30d": 8,
        "winners_5x_30d": 2,
        "entry_move_pct": 15,
        "supply_pct": 1.0,
        "is_accumulating": True,
        "flags": ["smart_degen"],
    }
    payload.update(overrides)
    return BuyerObservation.from_dict(payload)


def test_multiple_independent_quality_buyers_create_high_conviction():
    result = score_buyers([obs(f"w{i}") for i in range(4)], liquidity_usd=100_000)
    assert result.available is True
    assert result.score >= 75
    assert result.confidence >= 0.65
    assert result.qualified_wallets >= 3
    assert any(reason.startswith("QUALITY_WALLET_OVERLAP") for reason in result.reasons)


def test_one_whale_cannot_create_high_confidence():
    result = score_buyers(
        [obs("whale", buy_usd=250_000, current_position_usd=240_000)],
        liquidity_usd=500_000,
    )
    assert result.available is True
    assert result.confidence <= 0.42
    assert result.score <= 68
    assert "SINGLE_WALLET_EVIDENCE" in result.warnings


def test_toxic_wallet_flags_are_penalized():
    clean = score_buyers([obs(f"c{i}") for i in range(3)], liquidity_usd=100_000)
    toxic = score_buyers(
        [obs(f"t{i}", flags=["bundler", "sniper"]) for i in range(3)],
        liquidity_usd=100_000,
    )
    assert toxic.score < clean.score - 25
    assert toxic.qualified_wallets == 0
    assert any(x.startswith("TOXIC_WALLET_FLAGS") for x in toxic.warnings)


def test_fresh_low_sample_wallets_reduce_confidence():
    mature = score_buyers([obs(f"m{i}") for i in range(4)], liquidity_usd=100_000)
    fresh = score_buyers(
        [obs(f"f{i}", flags=["fresh_wallet"], trades_30d=1) for i in range(4)],
        liquidity_usd=100_000,
    )
    assert fresh.confidence < mature.confidence
    assert "FRESH_WALLET_SAMPLE_LOW_CONFIDENCE" in fresh.warnings


def test_no_data_is_unavailable_and_neutral_not_bearish():
    result = score_buyers([])
    assert result.available is False
    assert result.score == 50.0
    assert result.confidence == 0.0

    wallets_only = score_buyers([BuyerObservation(wallet="w1")])
    assert wallets_only.available is False
    assert wallets_only.score == 50.0


def test_high_supply_concentration_is_penalized():
    diversified = score_buyers(
        [obs(f"d{i}", supply_pct=1.0) for i in range(3)],
        liquidity_usd=100_000,
    )
    concentrated = score_buyers(
        [obs("x1", supply_pct=18.0), obs("x2", supply_pct=8.0), obs("x3", supply_pct=6.0)],
        liquidity_usd=100_000,
    )
    assert concentrated.score < diversified.score
    assert "BUYER_CONCENTRATION_RISK" in concentrated.warnings


def test_holding_and_accumulation_boost_retention():
    holding = score_buyers([obs(f"h{i}") for i in range(3)], liquidity_usd=100_000)
    dumping = score_buyers(
        [
            obs(
                f"s{i}",
                sell_usd=4_900,
                current_position_usd=100,
                is_accumulating=False,
            )
            for i in range(3)
        ],
        liquidity_usd=100_000,
    )
    assert holding.components["retention"] > dumping.components["retention"]
    assert holding.score > dumping.score


def test_build_accepts_percent_win_rate_and_provider_aliases(tmp_path):
    payload = {
        "network": "solana",
        "tokens": [
            {
                "mint": "Mint111",
                "symbol": "TEST",
                "liquidity_usd": 100_000,
                "observations": [
                    {
                        "address": "Wallet111",
                        "bought_usd": 10_000,
                        "sold_usd": 1_000,
                        "position_usd": 9_000,
                        "pnl_30d": 8_000,
                        "win_rate": 72,
                        "trades": 40,
                        "winners_2x": 5,
                        "winners_5x": 1,
                        "entry_price_move_pct": 20,
                        "supply_share_pct": 1.5,
                        "labels": ["smart_degen"],
                    }
                ],
            }
        ],
    }
    (tmp_path / "smart-buyer-observations.json").write_text(json.dumps(payload), encoding="utf-8")
    result = build(tmp_path)
    row = result["tokens"][0]
    assert row["identity_key"] == "solana:Mint111"
    assert row["available"] is True
    assert row["wallet_count"] == 1
    assert result["truth_contract"]["single_wallet_confidence_is_capped"] is True
