from wallet500 import cex_verified_arbitrage as va


def _candidate():
    return {"symbol":"LSKUSDT","buy_exchange":"okx","sell_exchange":"kucoin","buy_market_id":"LSK-USDT","sell_market_id":"LSK-USDT"}


def _books():
    return {"buy":{"asks":[["0.300","5000"]],"bids":[["0.299","5000"]]},"sell":{"bids":[["0.430","5000"]],"asks":[["0.431","5000"]]}}


def test_large_gap_fails_closed_without_route():
    r=va.verify_candidate(_candidate(),None,1000.0,_books())
    assert r["stage"]=="ROUTE_BLOCKED"
    assert r["verified_arbitrage"] is False
    assert "TRANSFER_ROUTE_UNVERIFIED" in r["blockers"]
    assert r["net_profit_pct"]>40
    assert r["automatic_trade"] is False


def test_route_still_fails_closed_when_fees_or_time_unverified():
    route={"network":"ethereum","withdraw_enabled":True,"deposit_enabled":True,"same_asset_identity_verified":True}
    r=va.verify_candidate(_candidate(),route,1000.0,_books())
    assert r["verified_arbitrage"] is False
    assert "FEES_UNVERIFIED" in r["blockers"]
    assert "TRANSFER_TIME_UNVERIFIED" in r["blockers"]


def test_fully_verified_route_and_depth_can_reach_verified_stage():
    route={"network":"ethereum","withdraw_enabled":True,"deposit_enabled":True,"same_asset_identity_verified":True,"fees_verified":True,"transfer_time_verified":True,"trading_fee_pct":0.1,"withdrawal_fee_usd":2.0,"transfer_cost_usd":1.0}
    r=va.verify_candidate(_candidate(),route,1000.0,_books())
    assert r["stage"]=="VERIFIED_ARBITRAGE"
    assert r["verified_arbitrage"] is True
    assert r["blockers"]==[]
    assert r["net_profit_pct"]>30
    assert r["automatic_trade"] is False


def test_depth_shortage_blocks_execution():
    books={"buy":{"asks":[["0.300","10"]],"bids":[]},"sell":{"bids":[["0.430","5000"]],"asks":[]}}
    route={"network":"ethereum","withdraw_enabled":True,"deposit_enabled":True,"same_asset_identity_verified":True,"fees_verified":True,"transfer_time_verified":True}
    r=va.verify_candidate(_candidate(),route,1000.0,books)
    assert r["verified_arbitrage"] is False
    assert "BUY_DEPTH_INSUFFICIENT" in r["blockers"]
