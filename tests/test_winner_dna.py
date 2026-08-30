from wallet500.winner_dna import distance, feature_summary


def test_control_distance_uses_only_point_in_time_features():
    a={"liquidity_usd":100000,"volume_h1":50000,"txns_h1":200}
    b={"liquidity_usd":110000,"volume_h1":55000,"txns_h1":210}
    assert distance(a,b) >= 0


def test_feature_summary_ignores_future_outcome():
    rows=[
        {"features":{"liquidity_usd":100000,"volume_h1":50000,"turnover_h1":.5,"buy_sell_ratio":1.5,"txns_h1":200},"outcome":{"peak_return_pct":1000}},
        {"features":{"liquidity_usd":200000,"volume_h1":100000,"turnover_h1":.5,"buy_sell_ratio":1.0,"txns_h1":400},"outcome":{"peak_return_pct":-90}},
    ]
    z=feature_summary(rows)
    assert z["liquidity_usd"] == 150000
    assert z["turnover_h1"] == .5
