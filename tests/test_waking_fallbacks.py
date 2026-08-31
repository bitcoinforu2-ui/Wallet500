from datetime import datetime, timezone

from wallet500.waking_fallbacks import (
    concentration_risk,
    conservative_confirmation_status,
    extract_rugcheck_metrics,
    parse_telegram_messages,
    telegram_catalyst_score,
    telegram_handle,
)


def test_rugcheck_metric_extraction_camel_case():
    report = {
        "totalHolders": 1234,
        "topHolders": [
            {"pct": 12.0},
            {"pct": 8.0},
            {"pct": 7.0},
            {"pct": 6.0},
        ],
    }
    m = extract_rugcheck_metrics(report)
    assert m["holder_count"] == 1234
    assert m["top1_pct"] == 12.0
    assert m["top10_pct"] == 33.0


def test_rugcheck_metric_extraction_snake_case_nested():
    report = {"data": {"holder_count": 500, "top_holders": [{"percentage": 21}, {"percentage": 19}]}}
    m = extract_rugcheck_metrics(report)
    assert m["holder_count"] == 500
    risk, signals = concentration_risk(m["top1_pct"], m["top10_pct"])
    assert risk >= 35
    assert "TOP1_TOKEN_ACCOUNT_GE_20PCT" in signals


def test_telegram_handle_only_public_channels():
    assert telegram_handle("https://t.me/mychannel") == "mychannel"
    assert telegram_handle("https://t.me/s/mychannel") == "mychannel"
    assert telegram_handle("https://t.me/+privateinvite") is None


def test_parse_telegram_only_last_24h():
    page = '''
    <div class="tgme_widget_message" data-post="testchan/12">
      <div class="tgme_widget_message_text">Major <b>partnership</b> and mainnet launch</div>
      <time datetime="2026-08-31T12:00:00+00:00"></time>
    </div>
    <div class="tgme_widget_message" data-post="testchan/11">
      <div class="tgme_widget_message_text">old post</div>
      <time datetime="2026-08-28T12:00:00+00:00"></time>
    </div>
    '''
    now = datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc)
    rows = parse_telegram_messages(page, "testchan", now=now)
    assert len(rows) == 1
    assert rows[0]["id"] == "testchan/12"
    assert "partnership" in rows[0]["text"]


def test_telegram_catalyst_needs_real_activity():
    score, signals = telegram_catalyst_score([
        {"text": "partnership and mainnet launch"},
        {"text": "new release and staking upgrade"},
    ], previous_count=1)
    assert score >= 55
    assert any("CATALYST_KEYWORDS" in x for x in signals)


def test_rugcheck_distribution_not_double_counted_as_positive_family():
    channels = {
        "holders": {"verified": True, "score": 80},
        "wallets": {"verified": False, "score": 0},
        "social": {"verified": False, "score": 0},
        "news": {"verified": False, "score": 0},
    }
    distribution = {"source": "RUGCHECK_EXACT_MINT_TOP_TOKEN_ACCOUNTS", "risk_score": 0}
    status, score, strong = conservative_confirmation_status(channels, distribution)
    assert status == "WAKING_UNCONFIRMED_RESEARCH"
    assert strong == ["holders"]
    assert score == 20.0


def test_rugcheck_extreme_concentration_can_trigger_risk():
    channels = {
        "holders": {"verified": True, "score": 100},
        "wallets": {"verified": True, "score": 100},
        "social": {"verified": True, "score": 100},
        "news": {"verified": True, "score": 100},
    }
    distribution = {"source": "RUGCHECK_EXACT_MINT_TOP_TOKEN_ACCOUNTS", "risk_score": 65}
    status, _, _ = conservative_confirmation_status(channels, distribution)
    assert status == "WAKING_RISK_RESEARCH"
