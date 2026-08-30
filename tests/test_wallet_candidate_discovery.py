import json
from wallet500.wallet_candidate_discovery import extract_signers, discover_solana_candidate_wallets, _candidate_source


def test_extract_signers_only_returns_explicit_signers():
    tx={"transaction":{"message":{"accountKeys":[{"pubkey":"walletA","signer":True},{"pubkey":"pool","signer":False},{"pubkey":"walletB","signer":True},{"pubkey":"walletA","signer":True}]}}}
    assert extract_signers(tx)==["walletA","walletB"]


class FakeAdapter:
    def signatures_for_address(self,address,limit=10):
        assert address=="pool"
        return [{"signature":"s1","blockTime":100},{"signature":"s2","blockTime":200}]
    def transaction(self,signature):
        keys={"s1":[{"pubkey":"walletA","signer":True},{"pubkey":"pool","signer":False}],"s2":[{"pubkey":"walletA","signer":True},{"pubkey":"walletB","signer":True}]}
        return {"blockTime":100 if signature=="s1" else 200,"transaction":{"message":{"accountKeys":keys[signature]}}}


def test_discovery_counts_verified_pool_transaction_signers():
    out=discover_solana_candidate_wallets(FakeAdapter(),{"chain":"solana","token":"mint","pair_address":"pool"},signatures_limit=2)
    assert out["error"] is None
    assert out["signatures_seen"]==2
    assert out["transactions_loaded"]==2
    assert out["wallets"][0]["address"]=="walletA"
    assert out["wallets"][0]["signer_appearances"]==2
    assert out["wallets"][0]["verified"] is True


def test_candidate_source_uses_active_preproduction_even_when_postgate_is_empty(tmp_path,monkeypatch):
    (tmp_path/'active-qualified-candidates.json').write_text(json.dumps([{'chain':'solana','token':'mint','pair_address':'pool'}]))
    (tmp_path/'holder-cluster-production-qualified.json').write_text('[]')
    monkeypatch.delenv('WALLET500_FORENSICS_INPUT',raising=False)
    rows,source=_candidate_source(tmp_path)
    assert source=='active-qualified-candidates.json'
    assert len(rows)==1
    assert rows[0]['token']=='mint'


def test_candidate_source_can_be_explicitly_overridden(tmp_path,monkeypatch):
    (tmp_path/'research.json').write_text(json.dumps([{'chain':'solana','token':'x'}]))
    monkeypatch.setenv('WALLET500_FORENSICS_INPUT','research.json')
    rows,source=_candidate_source(tmp_path)
    assert source=='research.json'
    assert rows==[{'chain':'solana','token':'x'}]
