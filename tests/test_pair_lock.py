from wallet500 import market_data
from wallet500 import main


def _pair(address, base="TOKEN", quote="USDC", price="1", native="1", liquidity=1000, fdv=None, market_cap=None):
    out = {
        "pairAddress": address,
        "baseToken": {"address": base, "symbol": base},
        "quoteToken": {"address": quote, "symbol": quote},
        "liquidity": {"usd": liquidity, "base": 100, "quote": 100},
        "priceUsd": price,
        "priceNative": native,
        "txns": {},
        "volume": {},
        "priceChange": {},
    }
    if fdv is not None:
        out["fdv"] = fdv
    if market_cap is not None:
        out["marketCap"] = market_cap
    return out


def test_snapshot_uses_requested_pair(monkeypatch):
    pairs=[
        _pair("PAIR_A", price="1", liquidity=1000),
        _pair("PAIR_B", price="9", liquidity=5000),
    ]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    s=market_data.snapshot("solana","TOKEN","PAIR_A")
    assert s["pair_address"]=="PAIR_A"
    assert s["price_usd"]==1.0
    assert s["token_identity_verified"] is True
    assert s["target_token_side"]=="BASE"


def test_snapshot_does_not_fallback_when_locked_pair_missing(monkeypatch):
    pairs=[_pair("PAIR_B", price="9", liquidity=5000)]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    monkeypatch.setattr(market_data,"pair_lookup",lambda chain,pair:None)
    assert market_data.snapshot("solana","TOKEN","PAIR_A") is None


def test_snapshot_rejects_pair_that_does_not_contain_target_token(monkeypatch):
    pairs=[_pair("PAIR_A", base="OTHER", quote="USDC", price="100")]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    assert market_data.snapshot("solana","TOKEN","PAIR_A") is None


def test_quote_side_price_is_derived_not_base_price(monkeypatch):
    # Base is worth $100 and 2 QUOTE per BASE => QUOTE is worth $50.
    pairs=[_pair("PAIR_A", base="BASE", quote="QUOTE", price="100", native="2")]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    s=market_data.snapshot("solana","QUOTE","PAIR_A")
    assert s["target_token_side"]=="QUOTE"
    assert s["price_usd"]==50.0
    assert s["market_cap"] is None
    assert s["fdv"] is None
    assert s["supply_valuation_verified"] is False
    assert s["supply_valuation_status"] == "UNAVAILABLE_QUOTE_SIDE"


def test_impossible_supply_valuation_is_quarantined_not_used(monkeypatch):
    # Regression case: $2.9M exact-pair liquidity cannot coexist credibly with
    # a $29K provider FDV/market cap. Preserve raw evidence; trusted fields become UNKNOWN.
    pairs=[_pair("PAIR_Z", price="1196.28", liquidity=2_900_000, fdv=29_000, market_cap=29_000)]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    s=market_data.snapshot("solana","TOKEN","PAIR_Z")
    assert s["pair_address"] == "PAIR_Z"
    assert s["raw_provider_fdv"] == 29_000
    assert s["raw_provider_market_cap"] == 29_000
    assert s["fdv"] is None
    assert s["market_cap"] is None
    assert s["supply_valuation_verified"] is False
    assert s["supply_valuation_status"] == "QUARANTINED_IMPOSSIBLE_VS_EXACT_POOL_LIQUIDITY"
    assert "EXACT_POOL_LIQUIDITY_GT_20X_PROVIDER_VALUATION" in s["supply_valuation_reasons"]


def test_plausible_supply_valuation_remains_available(monkeypatch):
    pairs=[_pair("PAIR_OK", price="1", liquidity=500_000, fdv=10_000_000, market_cap=8_000_000)]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    s=market_data.snapshot("solana","TOKEN","PAIR_OK")
    assert s["supply_valuation_verified"] is True
    assert s["fdv"] == 10_000_000
    assert s["market_cap"] == 8_000_000


def test_solana_pair_identity_is_case_sensitive(monkeypatch):
    pairs=[_pair("PairAbC", price="1")]
    monkeypatch.setattr(market_data,"token_pairs",lambda chain,token:pairs)
    monkeypatch.setattr(market_data,"pair_lookup",lambda chain,pair:None)
    assert market_data.snapshot("solana","TOKEN","pairabc") is None


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
