from wallet500.evidence_engine import build_evidence_snapshot


def test_evidence_snapshot_keeps_pair_identity_and_missing_layers_explicit():
    c={
        "chain":"bsc","token":"0xabc","pair_address":"0xpair","dex":"pancakeswap",
        "price_usd":0.001,"liquidity_usd":50000,"anomaly_score":92,
        "qualification":"QUALIFIED","qualification_reasons":["PASS"]
    }
    e=build_evidence_snapshot(c,observed_at="2026-08-28T00:00:00+00:00")
    assert e["identity"]["pair_address"]=="0xpair"
    assert e["market"]["price_usd"]==0.001
    assert e["holder_intelligence"]["status"]=="NO_VERIFIED_HOLDER_DATA"
    assert e["holder_intelligence"]["trust_score"] is None
    assert e["wallet_intelligence"]["status"]=="NO_VERIFIED_WALLET_DATA"
    assert e["evidence_policy"]=="IMMUTABLE_DISCOVERY_EVIDENCE_NO_HINDSIGHT"
