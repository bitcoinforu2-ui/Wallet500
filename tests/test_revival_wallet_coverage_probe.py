from wallet500 import revival_wallet_coverage_probe as probe


def test_probe_verified_is_never_promotion_alpha(monkeypatch):
    calls = []

    def fake_rpc(method, params):
        calls.append(method)
        if method == "getSignaturesForAddress":
            return [{"signature": "sig1"}]
        if method == "getTransaction":
            return {"meta": {"err": None}, "transaction": {"message": {"accountKeys": []}}}
        raise AssertionError(method)

    monkeypatch.setattr(probe.rpcbase, "_rpc", fake_rpc)
    monkeypatch.setattr(probe.rpcbase, "_mint_owner_deltas", lambda tx, mint: {})
    monkeypatch.setattr(probe.rpcbase, "_signers", lambda tx: set())

    row = probe._probe({"token_address": "MintA", "symbol": "A", "pair_address": "PairA"}, 1000)
    assert row["coverage_verified"] is True
    assert row["positive"] is False
    assert row["promotion_eligible"] is False
    assert row["status"] == "VERIFIED_LATEST_PAIR_TRANSACTION_NOT_TARGET_MINT"
    assert row["truth_contract"]["does_not_change_real_alert_gate"] is True


def test_unresolved_target_touch_fails_closed(monkeypatch):
    monkeypatch.setattr(probe.rpcbase, "_rpc", lambda method, params: [{"signature": "sig1"}] if method == "getSignaturesForAddress" else {"meta": {"err": None}})
    monkeypatch.setattr(probe.rpcbase, "_mint_owner_deltas", lambda tx, mint: {"owner": 2.0})
    monkeypatch.setattr(probe.rpcbase, "_signers", lambda tx: set())

    row = probe._probe({"token_address": "MintA", "symbol": "A", "pair_address": "PairA"}, 1000)
    assert row["coverage_verified"] is False
    assert row["unresolved_target_touch"] is True
    assert row["positive"] is False
