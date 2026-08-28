from wallet500.holder_cluster_production_gate import apply_gate


def c(token='0xabc',pair='0xpair'):
    return {'chain':'ethereum','token_address':token,'pair_address':pair}


def g(status,complete=False,risk_cluster=False,token='0xabc',pair='0xpair'):
    return {'chain':'ethereum','token_address':token,'pair_address':pair,'status':status,'verification_complete':complete,'cluster_verified':risk_cluster,'reasons':[]}


def test_evidence_complete_clean_pass_promotes_without_suspicious_cluster():
    p,q,b=apply_gate([c()],[g('PASS',True,False)])
    assert len(p)==1 and not q and not b
    assert p[0]['holder_cluster_verification_complete'] is True
    assert p[0]['holder_cluster_risk_cluster_verified'] is False


def test_pass_without_complete_verification_quarantines():
    p,q,b=apply_gate([c()],[g('PASS',False,False)])
    assert not p and len(q)==1 and not b
    assert q[0]['holder_cluster_reason']=='PASS_WITHOUT_COMPLETE_HOLDER_CLUSTER_VERIFICATION'


def test_review_quarantines():
    p,q,b=apply_gate([c()],[g('REVIEW',True,False)])
    assert not p and len(q)==1 and not b


def test_block_rejects():
    p,q,b=apply_gate([c()],[g('BLOCK',True,True)])
    assert not p and not q and len(b)==1


def test_missing_evidence_quarantines():
    p,q,b=apply_gate([c()],[])
    assert not p and len(q)==1 and not b
    assert q[0]['holder_cluster_reason']=='HOLDER_CLUSTER_EVIDENCE_MISSING'


def test_pair_identity_is_part_of_key():
    p,q,b=apply_gate([c(pair='0xpair1')],[g('PASS',True,False,pair='0xpair2')])
    assert not p and len(q)==1 and not b
