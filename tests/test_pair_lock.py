from wallet500 import market_data
from wallet500 import main


def test_snapshot_uses_requested_pair(monkeypatch):
    pairs=[
        {"pairAddress":"PAIR_A","liquidity":{"usd":1000},"priceUsd":"1","txns":{},"volume":{},"priceChange":{}},
        {"pairAddress":"PAIR_B","liquidity":{"usd":5000},"priceUsd":"9","txns":{},"volume":{},"priceChange":{}},
    ]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    s=market_data.snapshot("solana","TOKEN","PAIR_A")
    assert s["pair_address"]=="PAIR_A"
    assert s["price_usd"]==1.0


def test_snapshot_does_not_fallback_when_locked_pair_missing(monkeypatch):
    pairs=[{"pairAddress":"PAIR_B","liquidity":{"usd":5000},"priceUsd":"9","txns":{},"volume":{},"priceChange":{}}]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    assert market_data.snapshot("solana","TOKEN","PAIR_A") is None


def test_outcomes_refetch_locked_pair(tmp_path,monkeypatch):
    state={"tokens":{"solana:TOKEN":{"chain":"solana","token":"TOKEN","first_seen":"2026-08-27T00:00:00+00:00","tracking_started_at":"2026-08-27T00:00:00+00:00","entry_price_usd":1.0,"entry_pair_address":"PAIR_A","entry_dex":"dex"}}}
    snapshots=[{"chain":"solana","token":"TOKEN","pair_address":"PAIR_B","price_usd":9.0}]
    locked={"chain":"solana","token":"TOKEN","pair_address":"PAIR_A","dex":"dex","price_usd":2.0,"liquidity_usd":1000,"volume_h1":100,"buys_h1":10,"sells_h1":5}
    monkeypatch.setattr(main,"market_snapshot",lambda chain,token,pair:locked)
    out=main._update_outcomes(tmp_path,state,snapshots,"2026-08-27T01:00:00+00:00")
    rec=out["tokens"]["solana:TOKEN"]
    assert rec["current_pair_address"]=="PAIR_A"
    assert rec["current_price_usd"]==2.0
    assert rec["current_return_pct"]==100.0
    assert out["pair_mismatch_refetched"]==1
