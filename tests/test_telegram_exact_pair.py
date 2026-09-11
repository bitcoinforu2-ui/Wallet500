import json

from wallet500.telegram_alerts import (
    MIN_LIQUIDITY_USD,
    MIN_MARKET_AGE_DAYS,
    _fmt_israel_time,
    _is_actionable_real_alert,
    _is_pre_wave_alert,
    _merge_display_context,
    _message,
    _pair_key,
    _pre_wave_message,
    _tier,
    run,
)
from wallet500.policy import (
    CANONICAL_MIN_EXECUTION_LIQUIDITY_USD,
    CANONICAL_MIN_MARKET_AGE_DAYS,
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


def _pre_wave():
    return {
        "status": "PRE_WAVE_ALERT",
        "radar_tier": "PRE_WAVE",
        "user_alert_eligible": True,
        "manual_decision_only": True,
        "automatic_buy": False,
        "research_only": False,
        "actionable_research_alert": False,
        "symbol": "STORJ",
        "chain": "ethereum",
        "token_address": "0xb64ef51c888972c908cfacf59b47c1afbc0ab8ac",
        "pair_address": "0xAEF16913b6C50EBCf627a394921F306985FC8604",
        "dex": "uniswap",
        "dex_url": "https://dexscreener.com/ethereum/0xaef16913b6c50ebcf627a394921f306985fc8604",
        "price_usd": 0.03276,
        "execution_pool_liquidity_usd": 79651.61,
        "dex_volume_h1": 4522.59,
        "market_age_days": 1993,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "market_age_verified": True,
        "risk_reasons": [],
        "source_lanes": ["CEX_REVIVAL", "CEX_SPOT_BREADTH"],
        "source_lane_count": 2,
        "full_real_alert_pending_gates": ["STRONG_DECISION_LANE"],
        "cex_spot_score": 38,
        "cex_spot_confirmations": 4,
        "cex_spot_exchanges": ["gate", "kucoin", "mexc", "okx"],
        "pre_wave_gates": {
            "cex_spot_breadth": True,
            "multichain_market_activity": True,
            "risk_clear": True,
        },
        "first_alert_at": "2026-09-06T09:41:49.288906+00:00",
    }


def test_telegram_production_thresholds_are_canonical():
    assert MIN_MARKET_AGE_DAYS == CANONICAL_MIN_MARKET_AGE_DAYS == 180
    assert MIN_LIQUIDITY_USD == CANONICAL_MIN_EXECUTION_LIQUIDITY_USD == 50_000.0


def test_exact_pair_is_required_for_alert():
    row = _row()
    assert _tier(row) == "HIGH_CONVICTION"
    row["locked_pair_address"] = "0xOTHER"
    assert _tier(row) is None


def test_verified_180_day_market_age_is_required_for_alert():
    row = _row()
    row["market_age_min_days"] = 179
    assert _tier(row) is None
    row["market_age_min_days"] = 180
    assert _tier(row) == "HIGH_CONVICTION"
    row = _row()
    row["market_age_verified"] = False
    assert _tier(row) is None
    row = _row()
    row.pop("market_age_min_days")
    assert _tier(row) is None


def test_verified_50k_execution_liquidity_boundary_is_required():
    row = _row()
    row["live_liquidity_usd"] = 49_999
    assert _tier(row) is None
    row["live_liquidity_usd"] = 50_000
    assert _tier(row) == "HIGH_CONVICTION"


def test_real_alert_must_be_explicitly_actionable():
    assert _is_actionable_real_alert(_real_alert()) is True
    research_only = _real_alert()
    research_only["status"] = "EVIDENCE_READY_NOT_REAL_ALERT"
    research_only["actionable_research_alert"] = False
    assert _is_actionable_real_alert(research_only) is False


def test_pre_wave_is_separate_manual_user_alert_not_research_only_or_auto_buy():
    row = _pre_wave()
    assert _is_pre_wave_alert(row) is True
    assert _is_actionable_real_alert(row) is False
    assert row["automatic_buy"] is False
    assert row["research_only"] is False
    msg = _pre_wave_message(row, sent_at="2026-09-11T11:30:00+00:00", alert_event_id="pre123")
    assert "🔥🔥🔥 PRE-WAVE ALERT" in msg
    assert "NOT A BUY ORDER" in msg
    assert "MANUAL REVIEW ONLY" in msg
    assert "Token: STORJ" in msg
    assert "Full REAL ALERT still pending: STRONG_DECISION_LANE" in msg
    assert "OPEN DEX: https://dexscreener.com/ethereum/0xaef16913b6c50ebcf627a394921f306985fc8604" in msg
    bad = dict(row)
    bad["research_only"] = True
    assert _is_pre_wave_alert(bad) is False
    bad = dict(row)
    bad["user_alert_eligible"] = False
    assert _is_pre_wave_alert(bad) is False


def test_israel_time_format_is_explicit_and_dst_aware():
    assert _fmt_israel_time("2026-09-05T14:30:00+00:00") == "05/09/2026 17:30:00"


def test_dedupe_key_contains_pair_and_message_exposes_manual_promotion_dex_and_time():
    row = _row()
    assert _pair_key(row) == "bsc:0xabc:0xpair"
    display = _merge_display_context(row, _real_alert())
    msg = _message(display, "HIGH_CONVICTION", sent_at="2026-09-05T14:30:00+00:00", alert_event_id="abc123")
    assert "HIGH-CONVICTION BUY REVIEW" in msg
    assert "🆕 NEW REAL ALERT" in msg
    assert "תאריך ושעת שליחת ההתראה (ישראל): 05/09/2026 17:30:00" in msg
    assert "T0 אות מקורי (ישראל): 01/09/2026 21:17:38" in msg
    assert "Alert ID: abc123" in msg
    assert "MANUAL DECISION ONLY" in msg
    assert "Promotion: EVIDENCE_READY → ACTIONABLE" in msg
    assert "Token: ARC" in msg
    assert "Contract: 0xABC" in msg
    assert "Pair: 0xPAIR" in msg
    assert "DEX: pancakeswap" in msg
    assert "Pair identity: EXACT VERIFIED" in msg
    assert "Market age: ≥420d" in msg
    assert "min $50K" in msg
    assert "Positive evidence: VERIFIED_SOCIAL" in msg
    assert "Verified evidence: SMART_MONEY, VERIFIED_SOCIAL" in msg
    assert "OPEN DEX: https://dexscreener.com/bsc/0xpair" in msg


def test_unconfigured_scan_lane_cannot_overwrite_production_telegram_truth(tmp_path, monkeypatch):
    existing_report = {"version": 10, "configured": True, "delivered_count": 1, "delivered": [{"alert_event_id": "keep-me"}]}
    existing_state = {"sent": {"bsc:0xabc:0xpair": {"actionable": True, "alert_event_id": "keep-me"}}}
    (tmp_path / "telegram-alert-report.json").write_text(json.dumps(existing_report), encoding="utf-8")
    (tmp_path / "telegram-alert-state.json").write_text(json.dumps(existing_state), encoding="utf-8")
    (tmp_path / "active-qualified-candidates.json").write_text("[]", encoding="utf-8")
    (tmp_path / "real-alerts.json").write_text('{"alerts": [], "pre_wave_alerts": []}', encoding="utf-8")
    monkeypatch.setenv("WALLET500_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    result = run()
    assert result == existing_report
    assert json.loads((tmp_path / "telegram-alert-report.json").read_text()) == existing_report
    assert json.loads((tmp_path / "telegram-alert-state.json").read_text()) == existing_state