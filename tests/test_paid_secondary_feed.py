from datetime import datetime, timezone

from wallet500.paid_secondary_feed import classify, is_solana_address, parse_preview

SOL = "4SLntRxvdnLanZQQAwTPGTV3dGfsTGydRN1ig5vmpump"


def test_strict_solana_validation():
    assert is_solana_address(SOL)
    assert not is_solana_address("0x1032031e30DEF38Df4d570D17b184e08Fa434a95")
    assert not is_solana_address("d97F261b1e88845184f678e2d1e7a98D9FD38dE")


def test_source_phrases_are_recognized():
    assert "DEXSCREENER_PAID" in classify("Dexscreener 💵 PAID • 5' 28s")
    assert "DEXSCREENER_PAID" in classify("DEX PAID! Address: abc")
    assert "DEXSCREENER_BOOST" in classify("BOOSTED ⚡500 (in total ⚡500)")
    assert "DEXSCREENER_BOOST" in classify("Detected Boost 30⚡ DEXScreener")


def test_preview_extracts_only_strict_address():
    page = f'''<div class="tgme_widget_message" data-post="dexpaidalerts/1">
    <time datetime="2026-09-08T13:00:00+00:00"></time>
    <div class="tgme_widget_message_text">Official | solana `{SOL}` Dexscreener 💵 PAID • 1m 20s</div></div>'''
    rows = parse_preview(page, "dexpaidalerts", datetime(2026, 9, 8, 13, 5, tzinfo=timezone.utc))
    assert len(rows) == 1
    assert rows[0]["token_address"] == SOL
    assert rows[0]["event_types"] == ["DEXSCREENER_PAID"]
