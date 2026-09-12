from wallet500.trade_management_engine import MODE, analyze, build


def alert(price=1.0, liq=200_000):
    return {
        "symbol": "LSK", "chain": "ethereum", "token_address": "0xTOKEN", "pair_address": "0xPAIR",
        "price_usd": price, "execution_pool_liquidity_usd": liq,
        "readiness_passed": 7, "readiness_total": 7,
    }


def candles(start=1.0, step=0.002, n=40, spike=False):
    out=[]
    p=start
    for i in range(n):
        p += step
        if spike and i > n-8:
            p += 0.025
        out.append({"ts": i, "open": p*0.995, "high": p*1.01, "low": p*0.99, "close": p, "volume": 100_000+i*1000})
    return out


def market(cs, price=None, liq=190_000, buys=60, sells=40):
    return {"candles": cs, "price_usd": price or cs[-1]["close"], "liquidity_usd": liq,
            "volume_h1_usd": 150_000, "volume_h24_usd": 1_500_000,
            "buys_h1": buys, "sells_h1": sells, "source": "TEST"}


def test_extended_parabolic_7of7_waits_for_retest():
    cs=candles(spike=True)
    row=analyze(alert(1.0), market(cs), observed_at="2026-09-12T10:00:00+00:00")
    assert row["trade_state"] == "WAIT_FOR_RETEST"
    assert row["manual_review_only"] is True and row["automatic_buy"] is False
    assert row["entry_plan"]["zone_1"]["low"] is not None


def test_healthy_ema10_retest_becomes_buy_zone():
    cs=candles(start=1.0, step=0.004)
    # Put the exact live price onto the dynamic EMA10 support after the candles are built.
    probe=analyze(alert(1.0), market(cs), observed_at="2026-09-12T10:00:00+00:00")
    ema10=probe["technicals_1h"]["ema10"]
    row=analyze(alert(1.0), market(cs, price=ema10, liq=210_000, buys=70, sells=30), observed_at="2026-09-12T10:05:00+00:00")
    assert row["trade_state"] == "BUY_ZONE"
    assert row["market"]["liquidity_change_from_signal_pct"] > 0


def test_liquidity_collapse_invalidates_even_if_price_is_high():
    cs=candles(start=1.0, step=0.003)
    row=analyze(alert(1.0, 200_000), market(cs, price=1.15, liq=70_000), observed_at="2026-09-12T10:00:00+00:00")
    assert row["trade_state"] == "INVALIDATED"
    assert row["automatic_sell"] is False


def test_missing_ohlcv_fails_closed():
    row=analyze(alert(), {"candles": []}, observed_at="2026-09-12T10:00:00+00:00")
    assert row["trade_state"] == "DATA_INSUFFICIENT"
    assert row["entry_plan"] is None


def test_build_only_manages_7of7_exact_pair_rows():
    good=alert(); bad=alert(); bad["readiness_passed"]=6
    payload=build({"alerts":[good,bad]}, fetcher=lambda _: market(candles()), observed_at="2026-09-12T10:00:00+00:00")
    assert payload["mode"] == MODE
    assert payload["managed_count"] == 1
    assert payload["truth_contract"]["signal_gate_unchanged"] is True
    assert payload["automatic_trade"] is False
