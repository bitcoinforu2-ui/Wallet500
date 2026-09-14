from __future__ import annotations

import wallet500.cryptoyeezus_hardening as h
import wallet500.cryptoyeezus_live_watch as y


def test_rufus_multi_ticker_conviction_post_is_material_and_selects_rufus():
    text = (
        "Bottom on my $rufus overnight hopefully after 3X so far. "
        "Making around $1k a day in $AMZN stock profits anyways so I dont mind "
        "holding the moon bag on this either. There hasnt been an $AMZN pair "
        "runner yet. With $AI in the 100s of Ms this should reprice eventually."
    )
    refs = y.extract_refs(text)

    assert refs["tickers"] == ["RUFUS", "AMZN", "AI"]
    assert y.looks_like_call(text, refs) is True
    assert h.extended_primary_symbol(text, refs, None) == "RUFUS"
    assert h.extended_repeat_is_material(text, refs) is True


def test_plain_multi_ticker_comment_does_not_invent_primary_call():
    text = "$AAA compared with $BBB and $CCC today"
    refs = y.extract_refs(text)

    assert h.extended_primary_symbol(text, refs, None) is None
    assert h.extended_repeat_is_material(text, refs) is False


def test_multiplier_update_is_material():
    text = "$RUFUS is 3.5x so far"
    refs = y.extract_refs(text)
    assert h.extended_repeat_is_material(text, refs) is True


def test_fallback_depth_defaults_to_fifty(monkeypatch):
    monkeypatch.delenv("YEEZUS_X_FALLBACK_COUNT", raising=False)
    assert h._fallback_count() == 50
