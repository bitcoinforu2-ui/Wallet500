from wallet500.holder_cluster_production_gate import apply_gate


def c(token="0xabc", pair="0xpair"):
    return {"chain": "ethereum", "token_address": token, "pair_address": pair}


def g(status, verified=False, token="0xabc", pair="0xpair"):
    return {"chain": "ethereum", "token_address": token, "pair_address": pair, "status": status, "cluster_verified": verified, "reasons": []}


def test_verified_pass_promotes():
    p, q, b = apply_gate([c()], [g("PASS", True)])
    assert len(p) == 1 and not q and not b


def test_pass_without_verification_quarantines():
    p, q, b = apply_gate([c()], [g("PASS", False)])
    assert not p and len(q) == 1 and not b
    assert q[0]["holder_cluster_reason"] == "PASS_WITHOUT_CLUSTER_VERIFICATION"


def test_review_quarantines():
    p, q, b = apply_gate([c()], [g("REVIEW", False)])
    assert not p and len(q) == 1 and not b


def test_block_rejects():
    p, q, b = apply_gate([c()], [g("BLOCK", True)])
    assert not p and not q and len(b) == 1


def test_missing_evidence_quarantines():
    p, q, b = apply_gate([c()], [])
    assert not p and len(q) == 1 and not b
    assert q[0]["holder_cluster_reason"] == "HOLDER_CLUSTER_EVIDENCE_MISSING"


def test_pair_identity_is_part_of_key():
    p, q, b = apply_gate([c(pair="0xpair1")], [g("PASS", True, pair="0xpair2")])
    assert not p and len(q) == 1 and not b
