from wallet500.filter_tuning_advisor import advise


def test_small_sample_never_recommends_change():
 r=advise({'records':{}},{'filters':{'X':{'records':10,'false_negative_winners':5,'false_negative_major_winners':2,'false_negative_rate_pct':50}}})
 assert r['filters']['X']['tuning_verdict']=='INSUFFICIENT_SAMPLE'
 assert r['review_candidates']==[]
 assert r['production_thresholds_modified'] is False


def test_enough_evidence_only_creates_backtest_candidate():
 r=advise({'records':{}},{'filters':{'X':{'records':40,'false_negative_winners':5,'false_negative_major_winners':2,'false_negative_rate_pct':12.5}}})
 assert r['filters']['X']['tuning_verdict']=='REVIEW_THRESHOLD_CANDIDATE'
 assert r['review_candidates'][0]['action']=='BACKTEST_ONLY'
 assert r['review_candidates'][0]['production_change_allowed'] is False


def test_low_false_negative_rate_keeps_policy():
 r=advise({'records':{}},{'filters':{'X':{'records':100,'false_negative_winners':3,'false_negative_major_winners':0,'false_negative_rate_pct':3}}})
 assert r['filters']['X']['tuning_verdict']=='KEEP_CURRENT_POLICY'
 assert not r['review_candidates']
