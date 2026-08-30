from wallet500.measurable_bias_experiment import earliest_features, market_summary, technical_summary


def test_earliest_features_uses_first_history_mark_only():
    rec={"history":[
        {"observed_at":"t0","liquidity_usd":50000,"volume_h1":100000,"buys_h1":60,"sells_h1":40},
        {"observed_at":"t1","liquidity_usd":900000,"volume_h1":9000000,"buys_h1":900,"sells_h1":10},
    ]}
    z=earliest_features(rec)
    assert z["liquidity_usd"] == 50000
    assert z["volume_h1"] == 100000
    assert z["buy_sell_ratio"] == 1.5
    assert z["txns_h1"] == 100


def test_technical_summary_keeps_missing_history_in_denominator():
    rows=[
        {"pair_identity_status":"LOCKED","current_pair_address":"p","measurement_status":"VERIFIED_EXACT_PAIR","chain":"solana","features":{"liquidity_usd":50000}},
        {"pair_identity_status":"LEGACY_MISSING_IMMUTABLE_PAIR","current_pair_address":None,"measurement_status":"LEGACY_UNVERIFIABLE_PAIR","chain":"solana","features":None},
    ]
    z=technical_summary(rows)
    assert z["n"] == 2
    assert z["pair_locked_pct"] == 50.0
    assert z["earliest_snapshot_available_pct"] == 50.0


def test_market_summary_excludes_missing_history_without_hiding_coverage():
    rows=[
        {"features":{"liquidity_usd":50000,"volume_h1":100000,"turnover_h1":2,"buy_sell_ratio":1.5,"txns_h1":100}},
        {"features":None},
    ]
    z=market_summary(rows)
    assert z["comparable_n"] == 1
    assert z["liquidity_usd_median"] == 50000
    assert z["turnover_h1_median"] == 2
