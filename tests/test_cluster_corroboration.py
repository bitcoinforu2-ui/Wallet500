from wallet500.cluster_corroboration import verify_evm_deployer, verified_native_funding_edges, corroborate_clusters


def test_verify_deployer_requires_contract_creation_receipt_match():
    token='0x'+'11'*20
    def rpc(method,params):
        if method=='eth_getTransactionReceipt': return {'contractAddress':token}
        if method=='eth_getTransactionByHash': return {'from':'0x'+'22'*20,'to':None}
    out=verify_evm_deployer(rpc,token,{'deployment_tx_hash':'0xabc'})
    assert out['verified'] is True
    assert out['deployer']=='0x'+'22'*20


def test_deployer_mismatch_is_not_verified():
    token='0x'+'11'*20
    def rpc(method,params):
        if method=='eth_getTransactionReceipt': return {'contractAddress':'0x'+'33'*20}
        if method=='eth_getTransactionByHash': return {'from':'0x'+'22'*20,'to':None}
    out=verify_evm_deployer(rpc,token,{'deployment_tx_hash':'0xabc'})
    assert out['verified'] is False
    assert out['reason']=='DEPLOYMENT_RECEIPT_CONTRACT_MISMATCH'


def test_unverified_funding_hint_is_discarded():
    row={'verified_native_funding_edges':[
        {'source':'0xfunder','to':'0xaaa','tx_hash':'0x1','verified':False},
        {'source':'0xfunder','to':'0xbbb','tx_hash':'0x2','verified':True},
    ]}
    out=verified_native_funding_edges(row)
    assert len(out)==1
    assert out[0]['to']=='0xbbb'


def test_deployer_distribution_corroborates_but_never_claims_ownership():
    clusters=[{'wallets':['0xaaa','0xbbb'],'wallet_count':2,'combined_pct':24.0,'direct_transfer_count':1,'ownership_claim':False}]
    graph=[
        {'from':'0xdeployer','to':'0xaaa','transfer_count':1},
        {'from':'0xdeployer','to':'0xbbb','transfer_count':1},
        {'from':'0xaaa','to':'0xbbb','transfer_count':1},
    ]
    out=corroborate_clusters(clusters,graph,{'verified':True,'deployer':'0xdeployer'},[])
    assert out[0]['risk_corroborated'] is True
    assert out[0]['ownership_claim'] is False
    assert len(out[0]['deployer_distribution_targets'])==2


def test_common_native_funder_corroborates_multiple_cluster_wallets():
    clusters=[{'wallets':['0xaaa','0xbbb'],'wallet_count':2,'combined_pct':21.0,'direct_transfer_count':2,'ownership_claim':False}]
    funding=[
        {'source':'0xfunder','to':'0xaaa','tx_hash':'0x1','verified':True},
        {'source':'0xfunder','to':'0xbbb','tx_hash':'0x2','verified':True},
    ]
    out=corroborate_clusters(clusters,[],{'verified':False},funding)
    assert out[0]['risk_corroborated'] is True
    assert out[0]['common_native_funders'][0]['source']=='0xfunder'
