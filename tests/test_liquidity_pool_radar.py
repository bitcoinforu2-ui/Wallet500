from pathlib import Path
from wallet500.liquidity_pool_radar import analyze_liquidity_pools


def _snap(liq):
    return [{"chain":"solana","token":"TOKEN","pair_address":"PAIR","liquidity_usd":liq,"pools":[{"chain":"solana","token":"TOKEN","pair_address":"PAIR","dex":"pumpswap","liquidity_usd":liq,"volume_h1":30000,"buys_h1":100,"sells_h1":20,"pair_created_at":0}]}]


def test_liquidity_surge_requires_real_change(tmp_path:Path):
    first=analyze_liquidity_pools(_snap(10000),tmp_path,"2026-08-27T10:00:00+00:00")
    assert first["signals"]==[]
    second=analyze_liquidity_pools(_snap(30000),tmp_path,"2026-08-27T10:15:00+00:00")
    assert len(second["signals"])==1
    sig=second["signals"][0]
    assert sig["pair_address"]=="PAIR"
    assert sig["liquidity_delta_usd"]==20000
    assert "LIQUIDITY_SURGE_50PCT_PLUS" in sig["reasons"]
    assert "LIQUIDITY_THRESHOLD_BREAKOUT_20K" in sig["reasons"]
