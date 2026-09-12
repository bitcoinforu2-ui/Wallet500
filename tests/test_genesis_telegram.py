from wallet500.genesis_telegram import _eligible_entry, _message


def verified_entry():
    return {
        "entry_id": "solana:mint:pair:1",
        "candidate_key": "solana:mint:pair",
        "chain": "solana",
        "token": "MintAddress123",
        "symbol": "TEST",
        "created_at": "2026-09-12T12:00:00+00:00",
        "paper_mode": "VERIFIED_PAPER",
        "verified_track_record": True,
        "entry_alert_stage": "REAL_ALERT",
        "entry_genesis_score": 88,
        "entry_shadow_score": 91,
        "entry_signal_summary": {"passed": 6, "total": 7},
        "entry_acceleration_signals": ["VOLUME_ACCELERATION", "HOLDER_ACCELERATION"],
        "entry_source_catalyst": {"reasons": ["MOONSHOT_NEW"]},
        "entry_age_minutes": 55,
        "entry_price_usd": 0.01,
        "entry_liquidity_usd": 150000,
        "entry_holders": 900,
        "entry_top10_pct": 25,
        "dex_url": "https://dexscreener.com/solana/pair",
    }


def test_only_verified_real_alert_is_telegram_eligible():
    entry = verified_entry()
    assert _eligible_entry(entry) is True

    shadow = dict(entry, paper_mode="SHADOW_PAPER_UNVERIFIED_LP", verified_track_record=False)
    assert _eligible_entry(shadow) is False

    hot_watch = dict(entry, entry_alert_stage="HOT_WATCH")
    assert _eligible_entry(hot_watch) is False


def test_message_contains_contract_dex_and_real_alert_label():
    text = _message(verified_entry(), {})
    assert "GENESIS REAL ALERT" in text
    assert "CA: MintAddress123" in text
    assert "https://dexscreener.com/solana/pair" in text
    assert "PAPER ONLY" in text
