from wallet500 import holder_cluster_promotion as p


def test_missing_gate_evidence_is_review_not_promoted():
    promoted,review,blocked=p.classify([{'chain':'solana','token':'mint1','pair_address':'pair1'}],[])
    assert promoted==[] and blocked==[]
    assert review[0]['holder_cluster_reason']=='GATE_EVIDENCE_MISSING'


def test_block_is_excluded():
    active=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair'}]
    gate=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair','status':'BLOCK','verification_complete':True,'cluster_verified':False,'reasons':['TOP1_OWNER_CONCENTRATION_HIGH']}]
    promoted,review,blocked=p.classify(active,gate)
    assert promoted==[] and review==[]
    assert blocked[0]['holder_cluster_promotion']=='BLOCK'


def test_review_is_quarantined():
    active=[{'chain':'bsc','token':'0xabc','pair_address':'0xpair'}]
    gate=[{'chain':'bsc','token':'0xabc','pair_address':'0xpair','status':'REVIEW','verification_complete':True,'cluster_verified':False}]
    promoted,review,blocked=p.classify(active,gate)
    assert promoted==[] and blocked==[]
    assert review[0]['holder_cluster_promotion']=='REVIEW'


def test_incomplete_pass_cannot_promote():
    active=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair'}]
    gate=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair','status':'PASS','verification_complete':False,'cluster_verified':False}]
    promoted,review,blocked=p.classify(active,gate)
    assert promoted==[] and blocked==[]
    assert review[0]['holder_cluster_promotion']=='REVIEW'


def test_complete_clean_pass_promotes():
    active=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair'}]
    gate=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair','status':'PASS','verification_complete':True,'cluster_verified':False,'evidence_level':'FULL_EVM_TRANSFER_LEDGER'}]
    promoted,review,blocked=p.classify(active,gate)
    assert review==[] and blocked==[]
    assert promoted[0]['holder_cluster_promotion']=='PASS'
    assert promoted[0]['holder_cluster_verification_complete'] is True


def test_pair_mismatch_cannot_fallback_to_token_only():
    active=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair1'}]
    gate=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair2','status':'PASS','verification_complete':True}]
    promoted,review,blocked=p.classify(active,gate)
    assert promoted==[] and blocked==[]
    assert review[0]['holder_cluster_reason']=='GATE_EVIDENCE_MISSING'
