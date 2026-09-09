from datetime import datetime, timezone

from wallet500 import moonshot_verification_watch as mw


def _html(handle: str, post: int, when: str, text: str) -> str:
    return (
        f'<div class="tgme_widget_message" data-post="{handle}/{post}">'
        f'<time datetime="{when}"></time>'
        f'<div class="tgme_widget_message_text">{text}</div></div>'
    )


def test_parser_requires_verification_language_and_exact_mint():
    mint = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
    page = _html("moonshotlistings", 1, "2026-09-09T10:00:00+00:00", f"🚀 New coin verified on moonshot! Bobo ($BOBO) {mint}")
    rows = mw.parse_telegram_verifications(page, "moonshotlistings", datetime(2026, 9, 9, 11, tzinfo=timezone.utc))
    assert len(rows) == 1
    assert rows[0]["token"] == mint
    assert rows[0]["symbol"] == "BOBO"


def test_single_mirror_is_provisional_and_cannot_enter_alpha():
    mint = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
    rows = mw.correlate_observations([], [{"token": mint, "source_handle": "moonshotlistings", "published_at": "2026-09-09T10:00:00+00:00"}], datetime(2026, 9, 9, 11, tzinfo=timezone.utc))
    assert rows[0]["verification_confidence"] == "SINGLE_MIRROR_PROVISIONAL"
    assert rows[0]["eligible_for_external_alpha"] is False
    assert rows[0]["catalyst_priority_score"] == 70


def test_two_mirrors_promote_one_moonshot_source_not_two_independent_sources():
    mint = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
    mirrors = [
        {"token": mint, "source_handle": "moonshotlistings", "published_at": "2026-09-09T10:00:00+00:00"},
        {"token": mint, "source_handle": "moonshotnews", "published_at": "2026-09-09T10:03:00+00:00"},
    ]
    row = mw.correlate_observations([], mirrors, datetime(2026, 9, 9, 11, tzinfo=timezone.utc))[0]
    assert row["verification_confidence"] == "DOUBLE_MIRROR_CONSENSUS"
    assert row["source_owner"] == "moonshot"
    assert row["mirror_surface_count"] == 2
    assert row["catalyst_priority_score"] == 94
    assert row["eligible_for_external_alpha"] is True


def test_official_exact_contract_is_98_priority():
    mint = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
    official = [{"token": mint, "source_handle": "moonshot", "published_at": "2026-09-09T10:00:00+00:00", "url": "https://x.com/moonshot/status/1"}]
    row = mw.correlate_observations(official, [], datetime(2026, 9, 9, 11, tzinfo=timezone.utc))[0]
    assert row["verification_confidence"] == "OFFICIAL_X_EXACT_CONTRACT"
    assert row["catalyst_priority_score"] == 98
    assert row["eligible_for_external_alpha"] is True


def test_young_asset_is_research_exception_not_core_veteran(monkeypatch):
    token = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
    monkeypatch.setattr(mw, "_market", lambda t: ({"pair_identity_locked": True, "liquidity_usd": 250000.0, "market_age_days": 48.0, "pair_address": "PAIR"}, "OK"))
    out = mw._decorate_market({"token": token, "eligible_for_external_alpha": True})
    assert out["age_policy"] == "AGE_EXCEPTION_RESEARCH_ONLY"
    assert out["veteran_gate_pass"] is False
    assert out["alert_eligible"] is True
    assert out["automatic_buy"] is False
    assert out["never_bypass_wallet500_gates"] is True


def test_official_x_requires_contract_and_verification_context(monkeypatch):
    mint = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    payload = {
        "data": [
            {"id": "1", "author_id": "42", "created_at": "2026-09-09T10:00:00Z", "text": f"Contract Address: {mint} Verification is neither an endorsement nor a recommendation."},
            {"id": "2", "author_id": "42", "created_at": "2026-09-09T10:01:00Z", "text": "ABC ($ABC) is now verified on Moonshot."},
        ],
        "includes": {"users": [{"id": "42", "username": "moonshot", "verified": True}]},
    }
    monkeypatch.setattr(mw, "_get", lambda *a, **k: ("json", payload))
    rows, health = mw.collect_official_x(datetime(2026, 9, 9, 11, tzinfo=timezone.utc))
    assert health["status"] == "OK_DIRECT"
    assert len(rows) == 1
    assert rows[0]["token"] == mint
