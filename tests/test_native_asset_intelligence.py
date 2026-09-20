from scripts import native_asset_intelligence as mod


def _registry():
    return {
        "assets": {
            "harmony": {
                "symbol": "ONE",
                "chain": "harmony",
                "token_address": "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a",
                "representation_type": "CANONICAL_WRAPPED_NATIVE",
                "evidence_source": "HARMONY_OFFICIAL_DOCS_WRAPPED_ONE",
                "evidence_url": "https://docs.harmony.one/home/general/ecosystem/dapps/dexes/sushi",
            }
        }
    }


def _identity(change=37.8, coherent=3):
    return {
        "candidates": [{
            "symbol": "ONEUSDT",
            "base_symbol": "ONE",
            "coingecko_id": "harmony",
            "current_change_24h_max_pct": change,
            "current_coherent_confirmations": coherent,
            "markets": [{
                "exchange": "gate",
                "market_id": "ONE_USDT",
                "price": 0.0027884,
            }],
            "milestones": {
                "first_watch": {
                    "observed_at": "2026-09-06T02:15:44+00:00",
                    "reference_price": 0.000736,
                },
                "first_alert": {
                    "observed_at": "2026-09-13T00:24:06+00:00",
                    "reference_price": 0.000655,
                },
            },
        }]
    }


def _handoff(multiple=1.05, rank=2, ref=0.0027884):
    return {
        "rows": [{
            "symbol": "ONE",
            "coingecko_id": "harmony",
            "cex_reference_price_usd": ref,
            "cex_sensor": {
                "cex_led": True,
                "baseline_multiple": multiple,
                "current_rank": rank,
                "triggers": ["CEX_TOP3_BREAKOUT", "CEX_RANK_ACCELERATION"],
            },
        }]
    }


def _healthy_book(ref=0.0027884):
    # Keep the fixture price-coherent with the replayed CEX reference. This
    # validates execution depth/spread without weakening the production gate.
    return {
        "bids": [[f"{ref * 0.9975:.10f}", "6500000"], [f"{ref * 0.99:.10f}", "3000000"]],
        "asks": [[f"{ref * 1.0025:.10f}", "6500000"], [f"{ref * 1.01:.10f}", "3000000"]],
    }


def test_one_native_asset_close_watch_no_longer_requires_dex_pair(monkeypatch):
    monkeypatch.setattr(mod, "_get_json", lambda url, timeout=12: _healthy_book())
    out = mod.build(_handoff(), _identity(), _registry())
    assert out["count"] == 1
    row = out["candidates"][0]
    assert row["symbol"] == "ONE"
    assert row["asset_identity_verified"] is True
    assert row["asset_identity_scope"] == "CURATED_NATIVE_ASSET_PLUS_CANONICAL_WRAPPER"
    assert row["execution_identity_type"] == "CEX_SPOT_ORDERBOOK"
    assert row["execution_identity_verified"] is True
    assert row["stage"] == "CEX_NATIVE_ASSET_CLOSE_WATCH"
    assert row["buy_eligible"] is False
    assert row["telegram_delivery_enabled"] is False
    assert out["truth_contract"]["asset_identity_never_satisfies_buy_execution_identity"] is True


def test_one_stronger_cex_state_reaches_prebuy_research_but_never_buy(monkeypatch):
    monkeypatch.setattr(mod, "_get_json", lambda url, timeout=12: _healthy_book(0.0041537))
    out = mod.build(
        _handoff(multiple=2.4264, rank=1, ref=0.0041537),
        _identity(change=97.36, coherent=4),
        _registry(),
    )
    row = out["candidates"][0]
    assert row["score"] >= 70
    assert row["stage"] == "CEX_NATIVE_PREBUY_RESEARCH"
    assert row["execution_identity_verified"] is True
    assert row["buy_eligible"] is False
    assert row["actionable"] is False
    assert row["production_buy_blocker"] == "CEX_NATIVE_PREBUY_REQUIRES_FORWARD_VALIDATION_AND_DECISION_ENGINE_SUPPORT"


def test_native_asset_execution_fails_closed_when_orderbook_is_thin(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_get_json",
        lambda url, timeout=12: {
            "bids": [["0.00278", "10000"]],
            "asks": [["0.00280", "10000"]],
        },
    )
    out = mod.build(_handoff(multiple=3.0), _identity(change=60, coherent=5), _registry())
    row = out["candidates"][0]
    assert row["execution_identity_verified"] is False
    assert "CEX_DEPTH_BELOW_15K_PER_SIDE" in row["execution"]["blockers"]
    assert row["stage"] == "CEX_NATIVE_ASSET_CLOSE_WATCH"
