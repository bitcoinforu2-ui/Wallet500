from wallet500.cmc_holder_truth import parse_count_response, parse_holder_list_response


def test_cmc_count_accepts_exact_token_identity():
    out = parse_count_response({"count": 1234, "tokenAddress": "MintABC", "platformId": 16}, "MintABC")
    assert out["verified"] is True
    assert out["holder_count"] == 1234


def test_cmc_count_rejects_token_identity_mismatch():
    out = parse_count_response({"count": 1234, "tokenAddress": "OtherMint"}, "MintABC")
    assert out["verified"] is False
    assert out["status"] == "CMC_TOKEN_IDENTITY_MISMATCH"


def test_cmc_holder_list_preserves_wallet_tags_and_activity():
    payload = {
        "holders": [
            {
                "walletAddress": "Wallet1",
                "tokenAddress": "MintABC",
                "percent": "1.5",
                "buyUsd": "1000.5",
                "sellUsd": "200.25",
                "realizedPnl": "88.1",
                "realizedPnlPercent": "12.3",
                "tags": ["tag_smart_money", "tag_whale"],
                "fundingSource": "exchange",
            }
        ]
    }
    out = parse_holder_list_response(payload, "MintABC")
    assert out["verified"] is True
    assert out["wallet_sample_count"] == 1
    assert out["tag_counts"]["tag_smart_money"] == 1
    assert out["tag_counts"]["tag_whale"] == 1
    assert out["wallets"][0]["wallet_address"] == "Wallet1"
    assert out["wallets"][0]["buy_usd"] == 1000.5
