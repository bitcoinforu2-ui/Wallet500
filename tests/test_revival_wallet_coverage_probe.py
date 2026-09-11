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
    assert row["transaction_signature"] == "sig1"
    assert row["truth_contract"]["does_not_change_real_alert_gate"] is True


def test_unresolved_target_touch_fails_closed(monkeypatch):
    monkeypatch.setattr(probe.rpcbase, "_rpc", lambda method, params: [{"signature": "sig1"}] if method == "getSignaturesForAddress" else {"meta": {"err": None}})
    monkeypatch.setattr(probe.rpcbase, "_mint_owner_deltas", lambda tx, mint: {"owner": 2.0})
    monkeypatch.setattr(probe.rpcbase, "_signers", lambda tx: set())

    row = probe._probe({"token_address": "MintA", "symbol": "A", "pair_address": "PairA"}, 1000)
    assert row["coverage_verified"] is False
    assert row["unresolved_target_touch"] is True
    assert row["positive"] is False


def test_weaker_same_pair_probe_preserves_verified_history():
    previous = {
        "token_address": "MintA",
        "pair_address": "PairA",
        "observed_at": "2026-09-11T08:00:00Z",
        "coverage_verified": True,
        "promotion_eligible": False,
        "positive": False,
        "status": "VERIFIED_SIGNED_OWNER_TARGET_TOUCH",
        "resolved_signed_owner": True,
        "target_mint_touched": True,
        "unresolved_target_touch": False,
        "transaction_signature": "verified-sig",
    }
    current = {
        "token_address": "MintA",
        "pair_address": "PairA",
        "observed_at": "2026-09-11T09:00:00Z",
        "coverage_verified": False,
        "promotion_eligible": False,
        "positive": False,
        "status": "PARTIAL_TARGET_TOUCH_OWNER_UNRESOLVED",
        "resolved_signed_owner": False,
        "target_mint_touched": True,
        "unresolved_target_touch": True,
        "transaction_signature": "new-sig",
    }

    merged = probe._merge_probe_result(previous, current)

    assert merged["coverage_verified"] is False
    assert merged["status"] == "PARTIAL_TARGET_TOUCH_OWNER_UNRESOLVED"
    assert merged["coverage_state"] == "COVERAGE_DEGRADED"
    assert merged["coverage_degraded"] is True
    assert merged["historical_coverage_verified"] is True
    assert merged["first_verified_at"] == "2026-09-11T08:00:00Z"
    assert merged["last_verified_at"] == "2026-09-11T08:00:00Z"
    assert merged["first_verified_evidence"]["transaction_signature"] == "verified-sig"
    assert merged["last_verified_evidence"]["status"] == "VERIFIED_SIGNED_OWNER_TARGET_TOUCH"
    assert merged["current_probe"]["transaction_signature"] == "new-sig"


def test_first_verified_timestamp_is_immutable_across_verified_refreshes():
    first = probe._merge_probe_result(None, {
        "token_address": "MintA",
        "pair_address": "PairA",
        "observed_at": "2026-09-11T08:00:00Z",
        "coverage_verified": True,
        "promotion_eligible": False,
        "positive": False,
        "status": "VERIFIED_LATEST_PAIR_TRANSACTION_NOT_TARGET_MINT",
        "resolved_signed_owner": False,
        "target_mint_touched": False,
        "unresolved_target_touch": False,
        "transaction_signature": "sig-1",
    })
    second = probe._merge_probe_result(first, {
        "token_address": "MintA",
        "pair_address": "PairA",
        "observed_at": "2026-09-11T09:00:00Z",
        "coverage_verified": True,
        "promotion_eligible": False,
        "positive": False,
        "status": "VERIFIED_SIGNED_OWNER_TARGET_TOUCH",
        "resolved_signed_owner": True,
        "target_mint_touched": True,
        "unresolved_target_touch": False,
        "transaction_signature": "sig-2",
    })

    assert second["coverage_state"] == "CURRENTLY_VERIFIED"
    assert second["first_verified_at"] == "2026-09-11T08:00:00Z"
    assert second["last_verified_at"] == "2026-09-11T09:00:00Z"
    assert second["first_verified_evidence"]["transaction_signature"] == "sig-1"
    assert second["last_verified_evidence"]["transaction_signature"] == "sig-2"


def test_exact_pair_change_does_not_carry_verified_history():
    previous = probe._merge_probe_result(None, {
        "token_address": "MintA",
        "pair_address": "PairA",
        "observed_at": "2026-09-11T08:00:00Z",
        "coverage_verified": True,
        "promotion_eligible": False,
        "positive": False,
        "status": "VERIFIED_SIGNED_OWNER_TARGET_TOUCH",
        "resolved_signed_owner": True,
        "target_mint_touched": True,
        "unresolved_target_touch": False,
    })
    current = {
        "token_address": "MintA",
        "pair_address": "PairB",
        "observed_at": "2026-09-11T09:00:00Z",
        "coverage_verified": False,
        "promotion_eligible": False,
        "positive": False,
        "status": "RPC_TRANSACTION_READ_FAILED",
        "resolved_signed_owner": False,
        "target_mint_touched": False,
        "unresolved_target_touch": False,
    }

    merged = probe._merge_probe_result(previous, current)

    assert merged["historical_coverage_verified"] is False
    assert merged["first_verified_evidence"] is None
    assert merged["last_verified_evidence"] is None
    assert merged["coverage_state"] == "UNVERIFIED_NO_HISTORY"
