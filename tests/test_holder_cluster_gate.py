from wallet500 import holder_cluster_gate as h


def test_components_group_directly_linked_top_holders():
    holders=[
        {'owner':'0xaaa','pct':6.0},
        {'owner':'0xbbb','pct':5.0},
        {'owner':'0xccc','pct':2.0},
    ]
    graph=[
        {'from':'0xaaa','to':'0xbbb','transfer_count':3},
        {'from':'0xbbb','to':'0xccc','transfer_count':1},
    ]
    comps=h._components(holders,graph,set())
    assert len(comps)==1
    assert comps[0]['wallet_count']==3
    assert comps[0]['combined_pct']==13.0
    assert comps[0]['direct_transfer_count']==4
    assert comps[0]['ownership_claim'] is False


def test_components_exclude_pair_or_known_infrastructure():
    holders=[{'owner':'0xaaa','pct':8.0},{'owner':'0xpair','pct':20.0},{'owner':'0xbbb','pct':7.0}]
    graph=[
        {'from':'0xaaa','to':'0xpair','transfer_count':5},
        {'from':'0xpair','to':'0xbbb','transfer_count':5},
    ]
    assert h._components(holders,graph,{'0xpair'})==[]


def test_evm_start_block_is_fail_closed_when_unverified():
    start,source,verified=h._evm_start_block({},100000)
    assert verified is False
    assert source=='bounded_lookback'
    assert start==max(0,100000-h.EVM_LOOKBACK)


def test_incomplete_evm_concentration_cannot_hard_block(monkeypatch):
    def fake_evm(chain,token,row):
        holders=[{'owner':'0xaaa','pct':80.0},{'owner':'0xbbb','pct':10.0}]
        return holders,[],[],{'complete':False,'reason':'BOUNDED_LOOKBACK_RECONSTRUCTION'}
    monkeypatch.setattr(h,'_evm_holders',fake_evm)
    out=h.analyze({'chain':'bsc','token':'0x123','pair_address':'0xpair'})
    assert out['status']=='REVIEW'
    assert 'TOP1_CONCENTRATION_HIGH_REVIEW_ONLY' in out['reasons']
    assert out['cluster_verified'] is False


def test_complete_evm_concentration_can_hard_block(monkeypatch):
    def fake_evm(chain,token,row):
        holders=[{'owner':'0xaaa','pct':25.0},{'owner':'0xbbb','pct':10.0}]
        return holders,[],[],{'complete':True,'reason':'FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK'}
    monkeypatch.setattr(h,'_evm_holders',fake_evm)
    out=h.analyze({'chain':'ethereum','token':'0x123','deployment_block':1})
    assert out['status']=='BLOCK'
    assert 'TOP1_OWNER_CONCENTRATION_HIGH' in out['reasons']


def test_linked_component_is_review_not_ownership_proof(monkeypatch):
    def fake_evm(chain,token,row):
        holders=[{'owner':'0xaaa','pct':6.0},{'owner':'0xbbb','pct':5.0}]
        graph=[{'from':'0xaaa','to':'0xbbb','transfer_count':2}]
        clusters=h._components(holders,graph,set())
        return holders,graph,clusters,{'complete':True,'reason':'FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK'}
    monkeypatch.setattr(h,'_evm_holders',fake_evm)
    out=h.analyze({'chain':'ethereum','token':'0x123','deployment_block':1})
    assert out['status']=='REVIEW'
    assert len(out['linked_cluster_candidates'])==1
    assert out['linked_cluster_candidates'][0]['ownership_claim'] is False
    assert 'LINKED_TOP_HOLDER_COMPONENT_REQUIRES_CORROBORATION' in out['reasons']


def test_rows_from_source_accepts_plain_list():
    rows=[{'chain':'solana','token':'abc'}]
    assert h._rows_from_source(rows)==rows


def test_rows_from_source_accepts_wrapped_rows_only():
    rows=[{'chain':'bsc','token':'0x123'}]
    assert h._rows_from_source({'rows':rows})==rows
    assert h._rows_from_source({'rows':{}})==[]
    assert h._rows_from_source(None)==[]
