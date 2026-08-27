from wallet500.holder_cluster_intelligence import analyze_holders


def test_unknown_holder_data_never_becomes_zero_concentration():
    r=analyze_holders(None)
    assert r["status"]=="NO_VERIFIED_HOLDER_DATA"
    assert r["trust_score"] is None
    assert r["top10_pct"] is None
    assert "HOLDER_DATA_UNAVAILABLE" in r["risk_flags"]


def test_excludes_verified_lp_and_burn_rows():
    rows=[
        {"address":"lp","supply_pct":50,"is_lp":True},
        {"address":"burn","supply_pct":20,"is_burn":True},
        {"address":"a","supply_pct":8},
        {"address":"b","supply_pct":7},
        {"address":"c","supply_pct":5},
    ]
    r=analyze_holders(rows)
    assert r["status"]=="VERIFIED"
    assert r["holder_count"]==3
    assert r["top1_pct"]==8
    assert r["top10_pct"]==20


def test_connected_wallets_are_measured_as_effective_cluster():
    rows=[
        {"address":"a","supply_pct":9,"cluster_id":"same"},
        {"address":"b","supply_pct":8,"cluster_id":"same"},
        {"address":"c","supply_pct":7,"cluster_id":"same"},
        {"address":"d","supply_pct":5},
        {"address":"e","supply_pct":4},
    ]
    r=analyze_holders(rows)
    assert r["largest_connected_cluster_pct"]==24
    assert r["effective_cluster_pct"]==24
    assert "CONNECTED_CLUSTER_GE_15PCT" in r["risk_flags"]
    assert r["trust_score"]<100


def test_dangerous_distribution_gets_low_trust():
    rows=[
        {"address":"a","supply_pct":24,"cluster_id":"x"},
        {"address":"b","supply_pct":18,"cluster_id":"x"},
        {"address":"c","supply_pct":10},
        {"address":"d","supply_pct":8},
        {"address":"e","supply_pct":7},
    ]
    r=analyze_holders(rows)
    assert r["top10_pct"]==67
    assert r["largest_connected_cluster_pct"]==42
    assert r["distribution_level"] in {"CRITICAL","HIGH_RISK"}
