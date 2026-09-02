from wallet500 import wallet_candidate_discovery as w


def test_evm_forensics_fails_closed_without_exact_pair_lock():
    row={"chain":"bsc","token":"0xtoken","pair_address":"0xpair","locked_pair_address":"0xother","pair_identity_locked":True}
    out=w.discover_evm_candidate_wallets(row,transactions_limit=3,block_lookback=100)
    assert out["error"]=="EXACT_PAIR_IDENTITY_NOT_LOCKED"
    assert out["wallets"]==[]


def test_evm_forensics_uses_only_exact_pair_log_transactions(monkeypatch):
    pair="0x1111111111111111111111111111111111111111"
    candidate={"chain":"bsc","token":"0xtoken","pair_address":pair,"locked_pair_address":pair,"pair_identity_locked":True}

    def fake_rpc(urls,method,params):
        if method=="eth_blockNumber": return hex(1000),"rpc-a"
        if method=="eth_getTransactionByHash":
            txh=params[0]
            senders={"0xtx3":"0xaaa","0xtx2":"0xbbb","0xtx1":"0xaaa"}
            return {"hash":txh,"from":senders[txh]},"rpc-a"
        raise AssertionError(method)

    def fake_logs(urls,flt,a,b):
        assert flt=={"address":pair}
        assert a==901 and b==1000
        return [
            {"transactionHash":"0xtx1","blockNumber":hex(950),"logIndex":"0x0"},
            {"transactionHash":"0xtx2","blockNumber":hex(980),"logIndex":"0x0"},
            {"transactionHash":"0xtx3","blockNumber":hex(990),"logIndex":"0x0"},
            {"transactionHash":"0xtx3","blockNumber":hex(990),"logIndex":"0x1"},
        ],{"queries":1,"splits":0,"rpc_endpoints_used":1,"failed_range":None}

    monkeypatch.setattr(w,"_rpc_any",fake_rpc)
    monkeypatch.setattr(w,"_logs_resilient",fake_logs)
    out=w.discover_evm_candidate_wallets(candidate,transactions_limit=3,block_lookback=100)
    assert out["error"] is None
    assert out["logs_seen"]==4
    assert out["transactions_loaded"]==3
    assert out["blocks_scanned"]==100
    got={x["address"]:x for x in out["wallets"]}
    assert got["0xaaa"]["signer_appearances"]==2
    assert got["0xbbb"]["signer_appearances"]==1
    assert all(x["verified"] is True for x in out["wallets"])
    assert all(x["economic_owner_inference"] is False for x in out["wallets"])
