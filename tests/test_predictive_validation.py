from src.wallet500.predictive_validation import edge


def row(roi, verified, failed, passed=True):
    return {'return_pct':roi,'verified_tradable':verified,'failed_survival':failed,'survivor_first_pass':passed}


def test_small_sample_never_promotes():
    c=[row(20,True,False) for _ in range(29)]
    b=[row(-10,False,True,False) for _ in range(29)]
    z=edge(c,b)
    assert z['status']=='COLLECTING'
    assert z['production_eligible'] is False


def test_large_repeatable_advantage_is_only_edge_candidate():
    c=[row(20,True,False) for _ in range(100)]
    b=[row(-10,False,True,False) for _ in range(100)]
    z=edge(c,b)
    assert z['status']=='EDGE_CANDIDATE'
    assert z['production_eligible'] is True


def test_roi_only_is_not_enough():
    c=[row(20,False,True) for _ in range(100)]
    b=[row(-10,True,False,False) for _ in range(100)]
    z=edge(c,b)
    assert z['status']=='ANALYZABLE'
    assert z['production_eligible'] is False
