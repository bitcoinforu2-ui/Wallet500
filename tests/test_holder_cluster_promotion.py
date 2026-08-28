from wallet500 import holder_cluster_promotion as p


def test_missing_gate_evidence_is_review_not_promoted():
    promoted,review,blocked=p.classify([{'chain':'solana','token':'mint1'}],[])
    assert promoted==[] and blocked==[]
    assert review[0]['holder_cluster_reason']=='GATE_EVIDENCE_MISSING'


def test_block_is_excluded():
    active=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair'}]
    gate=[{'chain':'ethereum','token':'0xabc','pair_address':'0xpair','status':'BLOCK','cluster_verified':False,'reasons':['TOP1_OWNER_CONCENTRATION_HIGH']}]
    promoted,review,blocked=p.classify(active,gate)
    assert promoted==[] and review==[]
    assert blocked[0]['holder_cluster_promotion']=='BLOCK'


def test_review_is_quarantined():
    active=[{'chain':'bsc','token':'0xabc'}]
    gate=[{'chain':'bsc','token':'0xabc','status':'REVIEW','cluster_verified':False}]
    promoted,review,blocked=p.classify(active,gate)
    assert promoted==[] and blocked==[]
    assert review[0]['holder_cluster_promotion']=='REVIEW'


def test_unverified_pass_cannot_promote():
    active=[{'chain':'ethereum','token':'0xabc'}]
    gate=[{'chain':'ethereum','token':'0xabc','status':'PASS','cluster_verified':False}]
    promoted,review,blocked=p.classify(active,gate)
    assert promoted==[] and blocked==[]
    assert review[0]['holder_cluster_promotion']=='REVIEW'


def test_verified_pass_promotes():
    active=[{'chain':'ethereum','token':'0xabc'}]
    gate=[{'chain':'ethereum','token':'0xabc','status':'PASS','cluster_verified':True,'evidence_level':'CORROBORATED_CLUSTER'}]
    promoted,review,blocked=p.classify(active,gate)
    assert review==[] and blocked==[]
    assert promoted[0]['holder_cluster_promotion']=='PASS'
