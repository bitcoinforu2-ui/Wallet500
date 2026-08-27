from wallet500.anomaly_radar import rank_anomalies


def _row(**overrides):
    row={
        "chain":"bsc","token":"TEST","liquidity_usd":25000,
        "volume_h1":50000,"volume_h24":100000,"buys_h1":200,"sells_h1":50,
        "price_change_h1":80,"price_change_m5":10,
    }
    row.update(overrides)
    return row


def test_rejects_near_zero_liquidity_before_scoring():
    assert rank_anomalies([_row(liquidity_usd=1.81)],45)==[]


def test_rejects_active_collapse_before_scoring():
    assert rank_anomalies([_row(price_change_m5=-98.32)],45)==[]


def test_keeps_viable_early_candidate():
    rows=rank_anomalies([_row(liquidity_usd=12000,price_change_m5=11.28)],45)
    assert len(rows)==1
