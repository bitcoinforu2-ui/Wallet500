from wallet500 import cryptoyeezus_source_wallet_watch as w


def _bal(owner, mint, amount, decimals=6):
    raw = int(amount * (10 ** decimals))
    return {"owner": owner, "mint": mint, "uiTokenAmount": {"amount": str(raw), "decimals": decimals}}


def _tx(target_pre, target_post, usdc_pre, usdc_post, *, swap_log=True, signer=True):
    logs = ["Program log: Instruction: Swap"] if swap_log else []
    return {
        "blockTime": 1770000000,
        "transaction": {"message": {"accountKeys": [
            {"pubkey": w.SOURCE_WALLET, "signer": signer},
            {"pubkey": "SomeDexAccount111111111111111111111111111111", "signer": False},
        ]}},
        "meta": {
            "err": None,
            "fee": 5000,
            "preBalances": [10_000_000_000, 0],
            "postBalances": [10_000_000_000, 0],
            "preTokenBalances": [
                _bal(w.SOURCE_WALLET, "TargetMint111111111111111111111111111111111", target_pre),
                _bal(w.SOURCE_WALLET, w.USDC, usdc_pre),
            ],
            "postTokenBalances": [
                _bal(w.SOURCE_WALLET, "TargetMint111111111111111111111111111111111", target_post),
                _bal(w.SOURCE_WALLET, w.USDC, usdc_post),
            ],
            "logMessages": logs,
        },
    }


def test_verified_buy_requires_two_sided_swap_evidence():
    event = w.classify_verified_swap(_tx(0, 1000, 100, 75), "sig-buy", 1770000000)
    assert event is not None
    assert event["side"] == "BUY"
    assert event["token_mint"].startswith("TargetMint")
    assert event["source_notional"]["asset"] == "USDC"
    assert event["source_notional"]["usd"] == 25.0
    assert event["copy_1pct_notional"]["usd"] == 0.25
    assert event["simulation_only"] is True
    assert event["real_trade_claimed"] is False


def test_verified_sell_classifies_opposite_deltas():
    event = w.classify_verified_swap(_tx(1000, 400, 75, 95), "sig-sell", 1770000000)
    assert event is not None
    assert event["side"] == "SELL"
    assert event["source_notional"]["amount"] == 20.0


def test_plain_transfer_is_excluded_without_swap_evidence():
    event = w.classify_verified_swap(_tx(0, 1000, 100, 75, swap_log=False), "sig-transfer", 1770000000)
    assert event is None


def test_unsigned_wallet_event_is_excluded():
    event = w.classify_verified_swap(_tx(0, 1000, 100, 75, signer=False), "sig-other", 1770000000)
    assert event is None


def test_single_sided_airdrop_is_excluded():
    tx = _tx(0, 1000, 100, 100)
    event = w.classify_verified_swap(tx, "sig-airdrop", 1770000000)
    assert event is None


def test_first_run_is_forward_only_and_never_backfills(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "DATA", tmp_path)
    monkeypatch.setattr(w, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(w, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(w, "EVENTS_PATH", tmp_path / "events.json")
    monkeypatch.setattr(w, "_rpc", lambda method, params, attempts=4: [{"signature": "latest-sig"}])
    result = w.run()
    assert result["status"] == "FORWARD_BASELINE_ESTABLISHED"
    assert result["new_verified_swaps"] == 0
