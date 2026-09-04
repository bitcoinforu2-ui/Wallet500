from wallet500.revival_strict_t0 import empty_state, enrich_payload


def strict_coin(price=0.001, signal=True, pair="PAIR111"):
    return {
        "source": "revival_discovery_state+dexscreener_absorption_expansion",
        "network": "solana",
        "token_address": "Token1111111111111111111111111111111111111",
        "symbol": "TEST",
        "dex_pair_address": pair,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "price_usd": price,
        "absorption_candidate_proxy": True,
        "order_flow_absorption": {
            "signal": signal,
            "strict_grade": "STRICT-2",
            "strict_level": 2,
        },
    }


def payload(coin):
    return {
        "network": "solana",
        "production_portfolio_impact": "NONE",
        "counts": {},
        "coins": [coin],
    }


def test_first_green_strict_locks_discovery_price_and_time():
    state = empty_state()
    out, state = enrich_payload(payload(strict_coin(0.001)), state, "2026-09-04T12:00:00+00:00")
    d = out["coins"][0]["strict_discovery"]
    assert d["discovery_price_usd"] == 0.001
    assert d["snapshot_return_since_discovery_pct"] == 0.0
    assert d["strict_first_seen_at"] == "2026-09-04T12:00:00+00:00"
    assert d["immutable_t0"] is True
    assert out["counts"]["strict_green_t0_new"] == 1
    assert len(state["records"]) == 1


def test_discovery_price_never_resets_when_price_changes():
    state = empty_state()
    _, state = enrich_payload(payload(strict_coin(0.001)), state, "2026-09-04T12:00:00+00:00")
    out, state = enrich_payload(payload(strict_coin(0.0015)), state, "2026-09-04T13:00:00+00:00")
    d = out["coins"][0]["strict_discovery"]
    assert d["discovery_price_usd"] == 0.001
    assert d["snapshot_return_since_discovery_pct"] == 50.0
    assert d["strict_first_seen_at"] == "2026-09-04T12:00:00+00:00"
    assert out["counts"]["strict_green_t0_new"] == 0


def test_yellow_pre_move_does_not_get_strict_discovery_metric():
    state = empty_state()
    coin = strict_coin(0.001, signal=False)
    out, state = enrich_payload(payload(coin), state, "2026-09-04T12:00:00+00:00")
    assert "strict_discovery" not in out["coins"][0]
    assert len(state["records"]) == 0
    assert out["counts"]["strict_green_t0_current"] == 0


def test_pair_change_does_not_reuse_old_discovery_price():
    state = empty_state()
    _, state = enrich_payload(payload(strict_coin(0.001, pair="PAIR111")), state, "2026-09-04T12:00:00+00:00")
    out, state = enrich_payload(payload(strict_coin(0.002, pair="PAIR222")), state, "2026-09-04T13:00:00+00:00")
    d = out["coins"][0]["strict_discovery"]
    assert d["discovery_price_usd"] == 0.002
    assert d["snapshot_return_since_discovery_pct"] == 0.0
    assert len(state["records"]) == 2
