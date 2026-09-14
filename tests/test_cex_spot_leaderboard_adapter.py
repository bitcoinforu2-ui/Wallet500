from wallet500 import cex_spot_leaderboard_adapter as mod


def test_state_key_parser_keeps_market_id_out_of_symbol_and_drops_leverage():
    state = {
        "markets": {
            "spot:gate:MLPUSDT:MLP_USDT": [{"price": 0.1, "change_24h_pct": 20, "volume_24h": 100000}],
            "spot:gate:FIL5LUSDT:FIL5L_USDT": [{"price": 1, "change_24h_pct": 80, "volume_24h": 1000000}],
        }
    }
    rows = mod._latest_market_rows_fixed(state)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "MLPUSDT"
    assert rows[0]["market_id"] == "MLP_USDT"
