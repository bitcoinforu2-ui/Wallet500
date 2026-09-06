from datetime import datetime, timezone

from wallet500.genesis_live import _mark_entry, _open_paper_entry, _shadow_ready, _shadow_score
from wallet500.genesis_radar import PAPER_ENTRY_USD, genesis_score


def candidate():
    return {
        "candidate_key": "solana:mint:pair",
        "chain": "solana",
        "token": "mint",
        "symbol": "TEST",
        "pair_address": "pair",
        "url": "https://dexscreener.com/solana/pair",
        "price_usd": 0.01,
        "liquidity_usd": 150_000,
        "holders": 700,
        "top10_ex_system_pct": 28,
        "largest_non_system_wallet_pct": 5,
        "mint_authority_safe": True,
        "freeze_authority_safe": True,
        "transfer_restrictions_safe": True,
        "lp_integrity_safe": None,
        "volume_15m_usd": 120_000,
        "prev_volume_15m_usd": 40_000,
        "volume_30m_usd": 180_000,
        "baseline_volume_30m_usd": 60_000,
        "unique_buyers_15m": 0,
        "prev_unique_buyers_15m": 0,
        "buys_15m": 220,
        "sells_15m": 120,
        "holder_growth_30m_pct": 14,
        "holder_growth_2h_pct": 25,
        "top10_concentration_delta_pct": -1,
        "liquidity_growth_30m_pct": 18,
        "liquidity_growth_2h_pct": 30,
        "liquidity_drawdown_from_peak_pct": 4,
        "quality_wallet_buyers": 0,
        "high_confidence_wallet_buyers": 0,
        "organic_acceleration_confirmed": False,
        "organic_social_confirmed": False,
        "gain_from_baseline_pct": 180,
        "pair_age_minutes": 120,
        "source_confirmations": 2,
    }


def test_shadow_paper_can_learn_without_faking_lp_verification():
    c = candidate()
    scored = genesis_score(c)
    shadow = _shadow_score(c, scored)
    assert scored["status"] == "RESEARCH_ONLY"
    assert scored["safety"]["passed"] is False
    assert "UNKNOWN_LP_INTEGRITY" in scored["safety"]["research_only_reasons"]
    assert scored["acceleration"]["passed"] is True
    assert shadow >= 75
    assert _shadow_ready(c, scored, shadow) is True


def test_new_paper_entry_allocates_exactly_five_dollars():
    c = candidate()
    scored = genesis_score(c)
    c.update(scored)
    c["shadow_score"] = _shadow_score(c, scored)
    c["shadow_paper_ready"] = True
    entry = _open_paper_entry(c, datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc))
    assert entry["allocation_usd"] == PAPER_ENTRY_USD == 5.0
    assert entry["initial_quantity"] == 500.0
    assert entry["paper_mode"] == "SHADOW_PAPER_UNVERIFIED_LP"
    assert entry["verified_track_record"] is False


def test_half_take_profit_at_exact_two_x_keeps_remainder():
    c = candidate()
    scored = genesis_score(c)
    c.update(scored)
    c["shadow_score"] = _shadow_score(c, scored)
    c["shadow_paper_ready"] = True
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    entry = _open_paper_entry(c, now)
    marked = _mark_entry(entry, {"price_usd": 0.02, "liquidity_usd": 150_000}, now)
    assert marked["tp50_done"] is True
    assert marked["remaining_quantity"] == 250.0
    assert marked["realized_cash_usd"] == 5.0
    assert marked["current_value_usd"] == 10.0
    assert marked["pnl_pct"] == 100.0


def test_no_shadow_paper_after_five_thousand_percent():
    c = candidate()
    c["gain_from_baseline_pct"] = 6000
    scored = genesis_score(c)
    shadow = _shadow_score(c, scored)
    assert scored["extension_band"] == "LATE_NO_CHASE"
    assert _shadow_ready(c, scored, shadow) is False
