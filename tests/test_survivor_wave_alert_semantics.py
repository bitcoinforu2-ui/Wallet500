from wallet500.survivor_wave_watch import (
    classify_dna_event,
    dna_event_label,
    format_alert,
    pct_change,
)


def test_first_match_requires_no_prior_alert():
    event = classify_dna_event("LOW", "MEDIUM", had_prior_alert=False)
    assert event == "FIRST_DNA_MATCH"
    assert dna_event_label(event, "LOW", "MEDIUM") == "FIRST DNA MATCH"


def test_low_to_medium_after_prior_alert_is_reentry_not_first_match():
    event = classify_dna_event("LOW", "MEDIUM", had_prior_alert=True)
    assert event == "DNA_REENTRY_REACCELERATION"
    assert dna_event_label(event, "LOW", "MEDIUM") == "DNA RE-ENTRY / REACCELERATION"


def test_medium_to_high_after_prior_alert_is_upgrade():
    event = classify_dna_event("MEDIUM", "HIGH", had_prior_alert=True)
    assert event == "DNA_UPGRADE_MEDIUM_TO_HIGH"
    assert dna_event_label(event, "MEDIUM", "HIGH") == "DNA UPGRADE MEDIUM → HIGH"


def test_reentry_alert_shows_discovery_first_alert_current_and_returns():
    row = {
        "chain": "bsc",
        "token": "0x87ae267002cd1ea0ec86bf3601d4a8ad76a47777",
        "pair_address": "0xd4ae7DD719ec71594f13d0e3B17E65E9085f1Ca1",
        "winner_dna_match": "MEDIUM",
        "dna_event_type": "DNA_REENTRY_REACCELERATION",
        "dna_alert_count": 2,
        "wave_status": "EARLY_REACCELERATION",
        "wave_score": 45,
        "discovery_price_usd": 0.002607,
        "first_dna_alert_price_usd": 0.007249,
        "first_dna_alerted_at": "2026-09-15T08:33:29.243784+00:00",
        "price_usd": 0.01958,
        "discovered_at": "2026-09-03T07:46:54.155332+00:00",
        "liquidity_usd": 493285,
        "volume_h1_usd": 127366,
        "turnover_h1": 0.258199,
        "buy_sell_ratio_h1": 2.0044,
        "holder_delta_since_prior_hourly_snapshot": None,
        "winner_dna_hits": ["TURNOVER>=0.25", "BUY_SELL_RATIO>=1.25"],
        "wave_reasons": ["H1_TURNOVER", "BUY_PRESSURE", "PRICE_H6"],
    }
    text = format_alert(row, "LOW")
    assert "Event: DNA RE-ENTRY / REACCELERATION" in text
    assert "DNA transition: LOW → MEDIUM" in text
    assert "DNA alert #: 2" in text
    assert "Discovery: $0.002607" in text
    assert "First DNA alert: $0.007249" in text
    assert "Current: $0.01958" in text
    assert "Since discovery: +651.05%" in text
    assert "Since first DNA alert: +" in text
    assert "Buy/Sell 1H: 2.0044 (transaction count ratio)" in text
    assert "Holders Δ: n/a (no timestamp-safe comparison)" in text
    assert "FIRST DNA MATCH" not in text


def test_return_math_for_skyai_like_history_is_stable():
    assert round(pct_change(0.01958, 0.002607), 2) == 651.05
    assert round(pct_change(0.01958, 0.007249), 2) == 170.11
