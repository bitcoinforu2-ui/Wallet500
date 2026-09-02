from wallet500.cex_revival import _market_signal


def test_market_signal_keeps_features_on_same_exchange():
    price_only={
        'exchange':'gate','change_24h_pct':30,'price_delta_pct':4,
        'volume24_delta_pct':0,'oi_delta_pct':0,'funding_rate':0,'volume_24h':1_000_000,
    }
    oi_volume_only={
        'exchange':'mexc','change_24h_pct':0,'price_delta_pct':0,
        'volume24_delta_pct':20,'oi_delta_pct':10,'funding_rate':0,'volume_24h':1_000_000,
    }
    a=_market_signal(price_only);b=_market_signal(oi_volume_only)
    assert set(a['hits'])=={'MOMENTUM','PRICE_ACCEL'}
    assert set(b['hits'])=={'VOLUME_ACCEL','OI_ACCEL'}
    # No helper is allowed to synthesize one venue carrying all four features.
    assert max(a['hit_count'],b['hit_count'])==2


def test_extreme_dispersion_is_not_a_positive_feature():
    # Dispersion itself is deliberately absent from _market_signal feature hits.
    row={
        'exchange':'gate','change_24h_pct':40,'price_delta_pct':0,
        'volume24_delta_pct':0,'oi_delta_pct':0,'funding_rate':0,'volume_24h':0,
    }
    signal=_market_signal(row)
    assert 'DISPERSION' not in signal['hits']
