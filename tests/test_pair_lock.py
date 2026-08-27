from wallet500 import market_data


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
