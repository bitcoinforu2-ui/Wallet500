import wallet500.social_telegram_truth_hardening as tg


IDENTITY = {
    "token_address": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump",
    "pair_address": "J3b6dvheS2Y1cbMtVz5TCWXNegSjJDbUKxdUVDPoqmS7",
    "official_x": "https://x.com/arcdotfun",
    "official_telegram": "https://t.me/arcfunportal",
}


def test_telegram_official_context_requires_exact_author_match():
    assert tg.attribution_v2(
        {"source": "telegram", "author": "arcfunportal", "text": "official update"},
        IDENTITY,
    ) == "OFFICIAL_CHANNEL_CONTEXT"
    assert tg.attribution_v2(
        {"source": "telegram", "author": "random_channel", "text": "official-looking update"},
        IDENTITY,
    ) == "NAME_SYMBOL_CONTEXT"
    assert tg.attribution_v2(
        {"source": "telegram", "author": "random_channel", "text": IDENTITY["token_address"]},
        IDENTITY,
    ) == "EXACT_CONTRACT"


def test_public_telegram_parser_requires_original_timestamp_and_stable_message_id():
    page = '''
      <div class="tgme_widget_message js-widget_message" data-post="arcfunportal/101">
        <div class="tgme_widget_message_text js-message_text">Fresh <b>message</b></div>
        <a class="tgme_widget_message_date"><time datetime="2026-09-06T02:30:00+00:00">02:30</time></a>
      </div>
      <div class="tgme_widget_message js-widget_message" data-post="arcfunportal/102">
        <div class="tgme_widget_message_text js-message_text">No timestamp</div>
      </div>
      <div class="tgme_widget_message js-widget_message" data-post="otherchannel/103">
        <div class="tgme_widget_message_text js-message_text">Wrong channel</div>
        <time datetime="2026-09-06T02:31:00+00:00">02:31</time>
      </div>
    '''
    rows, dropped = tg.parse_public_telegram_html(page, "arcfunportal")
    assert dropped == 1
    assert len(rows) == 1
    assert rows[0]["id"] == "arcfunportal:101"
    assert rows[0]["published_at"] == "2026-09-06T02:30:00+00:00"
    assert rows[0]["timestamp_provenance"] == "TELEGRAM_ORIGINAL_DATETIME"
    assert rows[0]["text"] == "Fresh message"


def test_public_telegram_scan_reports_timestamp_truth(monkeypatch):
    page = b'''<div data-post="arcfunportal/555"><div class="tgme_widget_message_text">CA update</div><time datetime="2026-09-06T01:00:00+00:00">01:00</time></div>'''

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return page

    monkeypatch.setattr(tg, "urlopen", lambda req, timeout=18: Resp())
    rows, status = tg.scan_public_telegram(IDENTITY)
    assert status["status"] == "OK"
    assert status["timestamp_required"] is True
    assert status["timestamped_count"] == 1
    assert status["dropped_untimestamped"] == 0
    assert status["freshness_source"] == "TELEGRAM_ORIGINAL_DATETIME"
    assert rows[0]["published_at"] == "2026-09-06T01:00:00+00:00"
