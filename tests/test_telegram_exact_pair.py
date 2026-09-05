from wallet500.telegram_alerts import (
    _fmt_israel_time,
    _is_actionable_real_alert,
    _merge_display_context,
    _message,
    _pair_key,
    _tier,
)


def _row():
    return {
        "chain": "bsc",
        "token": "0xABC",
        "pair_address": "0xPAIR",
        "locked_pair_address": "0xPAIR",
        "pair_identity_locked": True,
        "qualification": "QUALIFIED",
        "live_survival_gate": "ACTIVE",
        "pump_dump_blocked": False,
        "holder_cluster_production_status": "PASS",
        "holder_cluster_verification_complete": True,
        "market_age_verified": True,
        "market_age_min_days": 420,
        "market_age_evidence_source": "DEXSCREENER_OLDEST_CURRENT_EXACT_TOKEN_PAIR_CREATED_AT",
        "anomaly_score": 92,
        "live_liquidity_usd": 80000,
        "live_volume_h1": 50000,
        "live_activity_h1": 120,
        "pump_dump_risk_level": "LOW",
        "dex": "pancakeswap",
        "price_usd": 0.01,
        "buys_h1": 80,
        "sells_h1": 40,
        "survival_checked_at": "2026-09-02T04:00:00+00:00",
        "url": "https://dexscreener.com/bsc/0xpair",
    }


def _real_alert():
    return {
        "status": "REAL_ALERT",
        "actionable_research_alert": True,
        "symbol": "ARC",
        "chain": "bsc",
        "token_address": "0xABC",
        "pair_address": "0xPAIR",
        "dex": "pancakeswap",
        "dex_url": "https://dexscreener.com/bsc/0xpair",
        "price_usd": 0.0101,
        "execution_pool_liquidity_usd": 81000,
        "market_age_days": 420,
        "score": 65.22,
        "source_lanes": ["ACTIVE_PRODUCTION_GATE", "REVIVAL_MARKET_STRUCTURE"],
        "source_lane_count": 2,
        "evidence_envelope_status": "EVIDENCE_READY",
        "evidence_ready": True,
        "evidence_positive_lanes": ["VERIFIED_SOCIAL"],
        "evidence_verified_lanes": ["SMART_MONEY", "VERIFIED_SOCIAL"],
        "first_alert_at": "2026-09-01T18:17:38+00:00",
    }


def test_exact_pair_is_required_for_alert():
    row = _row()
    assert _tier(row) == "HIGH_CONVICTION"
    row["locked_pair_address"] = "0xOTHER"
    assert _tier(row) is None


def test_verified_180_day_market_age_is_required_for_alert():
    row = _row()
    row["market_age_min_days"] = 179
    assert _tier(row) is None
    row = _row()
    row["market_age_verified"] = False
    assert _tier(row) is None
    row = _row()
    row.pop("market_age_min_days")
    assert _tier(row) is None


def test_real_alert_must_be_explicitly_actionable():
    assert _is_actionable_real_alert(_real_alert()) is True
    research_only = _real_alert()
    research_only["status"] = "EVIDENCE_READY_NOT_REAL_ALERT"
    research_only["actionable_research_alert"] = False
    assert _is_actionable_real_alert(research_only) is False


def test_israel_time_format_is_explicit_and_dst_aware():
    assert _fmt_israel_time("2026-09-05T14:30:00+00:00") == "05/09/2026 17:30:00"


def test_dedupe_key_contains_pair_and_message_exposes_manual_promotion_dex_and_time():
    row = _row()
    assert _pair_key(row) == "bsc:0xabc:0xpair"
    display = _merge_display_context(row, _real_alert())
    msg = _message(display, "HIGH_CONVICTION", sent_at="2026-09-05T14:30:00+00:00")
    assert "HIGH-CONVICTION BUY REVIEW" in msg
    assert "תאריך ושעת שליחת ההתראה (ישראל): 05/09/2026 17:30:00" in msg
    assert "T0 אות מקורי (ישראל): 01/09/2026 21:17:38" in msg
    assert "MANUAL DECISION ONLY" in msg
    assert "Promotion: EVIDENCE_READY → ACTIONABLE" in msg
    assert "Token: ARC" in msg
    assert "Contract: 0xABC" in msg
    assert "Pair: 0xPAIR" in msg
    assert "DEX: pancakeswap" in msg
    assert "Pair identity: EXACT LOCK" in msg
    assert "Market age: ≥420d" in msg
    assert "Positive evidence: VERIFIED_SOCIAL" in msg
    assert "Verified evidence: SMART_MONEY, VERIFIED_SOCIAL" in msg
    assert "OPEN DEX: https://dexscreener.com/bsc/0xpair" in msg
