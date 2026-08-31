from wallet500.cyberleek_wallet_flow import MINT, _extract_trade, _summarize_window


def _tx(owner: str, signer: str, pre: int, post: int, decimals: int = 6):
    return {
        "blockTime": 1_800_000_000,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": signer, "signer": True, "writable": True},
                    {"pubkey": "Other111111111111111111111111111111111", "signer": False, "writable": True},
                ]
            }
        },
        "meta": {
            "err": None,
            "preTokenBalances": [
                {"mint": MINT, "owner": owner, "uiTokenAmount": {"amount": str(pre), "decimals": decimals}}
            ],
            "postTokenBalances": [
                {"mint": MINT, "owner": owner, "uiTokenAmount": {"amount": str(post), "decimals": decimals}}
            ],
        },
    }


def test_extract_trade_requires_signed_owner_and_classifies_buy():
    owner = "Trader11111111111111111111111111111111111"
    event = _extract_trade(_tx(owner, owner, 1_000_000, 3_500_000), "sig-buy")
    assert event is not None
    assert event["w"] == owner
    assert event["side"] == "BUY"
    assert event["token_delta"] == 2.5


def test_extract_trade_fails_closed_when_owner_is_not_signer():
    owner = "Trader11111111111111111111111111111111111"
    signer = "Router11111111111111111111111111111111111"
    assert _extract_trade(_tx(owner, signer, 3_500_000, 1_000_000), "sig-router") is None


def test_window_separates_first_seen_and_repeat_buyers():
    events = [
        {"t": 1000, "sig": "a", "w": "A", "side": "BUY", "token_delta": 100.0},
        {"t": 1010, "sig": "b", "w": "A", "side": "BUY", "token_delta": 50.0},
        {"t": 1020, "sig": "c", "w": "B", "side": "SELL", "token_delta": -60.0},
        {"t": 1030, "sig": "d", "w": "C", "side": "BUY", "token_delta": 20.0},
    ]
    first = {
        "A": {"t": 900, "side": "BUY"},
        "B": {"t": 1020, "side": "SELL"},
        "C": {"t": 1030, "side": "BUY"},
    }
    s = _summarize_window(events, first, 950)
    assert s["unique_buyers"] == 2
    assert s["unique_sellers"] == 1
    assert s["first_seen_buyers_since_t0"] == 1
    assert s["repeat_buyers"] == 1
    assert s["buy_token_flow"] == 170.0
    assert s["sell_token_flow"] == 60.0
    assert s["tx_per_unique_trader"] == 1.3333
