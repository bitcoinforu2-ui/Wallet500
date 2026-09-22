from wallet500.post_buy_guardian import (
    MODE,
    _source_positions,
    build,
    evaluate_position,
)


KEY = "ethereum:0xaaaaaa20d9e0e2461697782ef11675f668207961:0x629d22e6eeac46a11dbc96be93b90aee9309be4c"
NOW = "2026-09-22T18:30:00+00:00"


def source():
    return {
        "key": KEY,
        "symbol": "AURORAUSDT",
        "chain": "ethereum",
        "token_address": "0xaaaaaa20d9e0e2461697782ef11675f668207961",
        "pair_address": "0x629d22e6eeac46a11dbc96be93b90aee9309be4c",
        "entry_price_usd": 0.10,
        "entry_time": "2026-09-22T18:19:00+00:00",
        "entry_liquidity_hint_usd": 600_000,
        "source": "UNIFIED_WATCH_FINAL_BUY_DELIVERED",
    }


def candles(prices):
    return [
        {
            "ts": i,
            "open": p,
            "high": p * 1.002,
            "low": p * 0.998,
            "close": p,
            "volume": 10000,
        }
        for i, p in enumerate(prices)
    ]


def market(
    price=0.103,
    liq=590_000,
    buys5=30,
    sells5=20,
    prices=None,
):
    if prices is None:
        prices = [0.098 + i * 0.00025 for i in range(25)]
        prices[-1] = price
    return {
        "price_usd": price,
        "liquidity_usd": liq,
        "volume_m5_usd": 20_000,
        "volume_h1_usd": 150_000,
        "buys_m5": buys5,
        "sells_m5": sells5,
        "buys_m15": 80,
        "sells_m15": 60,
        "buys_h1": 200,
        "sells_h1": 150,
        "candles_5m": candles(prices),
        "source": "TEST",
    }


def test_delivered_final_buy_is_imported_as_exact_pair():
    user_state = {
        "targets": {
            KEY: {
                "identity_key": KEY,
                "symbol": "AURORAUSDT",
                "last_delivery_status": "DELIVERED",
                "last_alert_at": "2026-09-22T18:19:00+00:00",
                "last_alert_price": 0.09784,
                "last_liquidity": 572_928,
            }
        }
    }
    out = _source_positions(user_state, {}, __import__("datetime").datetime.fromisoformat(NOW))
    assert KEY in out
    assert out[KEY]["entry_price_usd"] == 0.09784
    assert out[KEY]["pair_address"].lower().startswith("0x629d22")


def test_healthy_post_buy_state():
    row = evaluate_position(source(), market(), {}, NOW)
    assert row["risk_state"] == "HEALTHY"
    assert row["automatic_sell"] is False


def test_two_warning_signals_become_caution():
    prices = [0.104] * 20 + [0.102, 0.100, 0.098, 0.097, 0.096]
    row = evaluate_position(
        source(),
        market(price=0.096, liq=500_000, buys5=9, sells5=15, prices=prices),
        {"peak_price_usd": 0.104, "baseline_liquidity_usd": 600_000},
        NOW,
    )
    assert row["risk_state"] in {"CAUTION", "EXIT_REVIEW"}
    assert row["automatic_sell"] is False


def test_hard_stop_from_buy_becomes_exit_review():
    prices = [0.102] * 20 + [0.099, 0.097, 0.095, 0.093, 0.091]
    row = evaluate_position(
        source(),
        market(price=0.091, liq=580_000, buys5=20, sells5=30, prices=prices),
        {"peak_price_usd": 0.108, "baseline_liquidity_usd": 600_000},
        NOW,
    )
    assert row["risk_state"] == "EXIT_REVIEW"
    assert "PRICE_BELOW_BUY_BY_8PCT" in row["reasons"]


def test_liquidity_collapse_invalidates():
    row = evaluate_position(
        source(),
        market(price=0.101, liq=250_000),
        {"peak_price_usd": 0.104, "baseline_liquidity_usd": 600_000},
        NOW,
    )
    assert row["risk_state"] == "INVALIDATED"
    assert "LIQUIDITY_COLLAPSE_GE_40PCT" in row["reasons"]


def test_data_failure_never_becomes_sell_signal():
    row = evaluate_position(source(), None, {}, NOW)
    assert row["risk_state"] == "DATA_DEGRADED"
    assert row["automatic_sell"] is False


def test_telegram_is_transition_only_not_spam():
    user_state = {
        "targets": {
            KEY: {
                "identity_key": KEY,
                "symbol": "AURORAUSDT",
                "last_delivery_status": "DELIVERED",
                "last_alert_at": "2026-09-22T18:19:00+00:00",
                "last_alert_price": 0.10,
                "last_liquidity": 600_000,
            }
        }
    }
    sent = []

    def bad_market(_):
        return market(
            price=0.091,
            liq=580_000,
            buys5=10,
            sells5=30,
            prices=[0.104] * 20 + [0.100, 0.097, 0.095, 0.093, 0.091],
        )

    def sender(text):
        sent.append(text)
        return True, 123, None

    s1, r1 = build(user_state, {}, {}, fetcher=bad_market, observed_at=NOW, send_func=sender)
    assert r1["mode"] == MODE
    assert r1["delivered_count"] == 1
    assert len(sent) == 1

    later = "2026-09-22T18:35:00+00:00"
    s2, r2 = build(user_state, {}, s1, fetcher=bad_market, observed_at=later, send_func=sender)
    assert r2["delivered_count"] == 0
    assert len(sent) == 1
    assert s2["positions"][KEY]["risk_state"] == "EXIT_REVIEW"


def test_recovery_emits_once():
    user_state = {
        "targets": {
            KEY: {
                "identity_key": KEY,
                "symbol": "AURORAUSDT",
                "last_delivery_status": "DELIVERED",
                "last_alert_at": "2026-09-22T18:19:00+00:00",
                "last_alert_price": 0.10,
                "last_liquidity": 600_000,
            }
        }
    }
    prior = {
        "positions": {
            KEY: {
                **source(),
                "risk_state": "CAUTION",
                "peak_price_usd": 0.104,
                "baseline_liquidity_usd": 600_000,
                "last_telegram_at": "2026-09-22T18:10:00+00:00",
            }
        }
    }
    sent = []

    def sender(text):
        sent.append(text)
        return True, 456, None

    _, report = build(
        user_state,
        {},
        prior,
        fetcher=lambda _: market(price=0.103, liq=610_000, buys5=35, sells5=15),
        observed_at=NOW,
        send_func=sender,
    )
    assert report["delivered_count"] == 1
    assert report["deliveries"][0]["event"] == "RECOVERED"
