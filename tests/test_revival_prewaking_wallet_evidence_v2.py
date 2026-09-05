import wallet500.revival_prewaking_wallet_evidence_v2 as mod


def test_non_target_mint_pair_traffic_is_not_unresolved(monkeypatch):
    txs = {
        "nontrade": {"meta": {"err": None}},
        "swap": {"meta": {"err": None}},
    }
    monkeypatch.setattr(mod.rpcbase, "_rpc", lambda method, params: txs[params[0]])
    monkeypatch.setattr(
        mod.rpcbase,
        "_mint_owner_deltas",
        lambda tx, mint: {} if tx is txs["nontrade"] else {"wallet": 5.0},
    )
    monkeypatch.setattr(
        mod.collector,
        "_extract_trade",
        lambda tx, sig, mint, block_time=None: {"t": 1, "sig": sig, "w": "wallet", "side": "BUY", "token_delta": 5.0}
        if sig == "swap" else None,
    )
    events, unresolved = mod._fetch_transactions_resilient([
        {"signature": "nontrade"},
        {"signature": "swap"},
    ], "mint")
    assert len(events) == 1
    assert unresolved == 0


def test_target_mint_touch_without_signed_owner_stays_unresolved(monkeypatch):
    tx = {"meta": {"err": None}}
    monkeypatch.setattr(mod.rpcbase, "_rpc", lambda method, params: tx)
    monkeypatch.setattr(mod.rpcbase, "_mint_owner_deltas", lambda tx, mint: {"wallet": 5.0})
    monkeypatch.setattr(mod.collector, "_extract_trade", lambda *args, **kwargs: None)
    events, unresolved = mod._fetch_transactions_resilient([{"signature": "x"}], "mint")
    assert events == []
    assert unresolved == 1
