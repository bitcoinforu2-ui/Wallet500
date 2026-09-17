import json

import wallet500.telegram_first_seen as first_seen


def _row(token="0xABC", chain="bsc", market_age_days=None, market_age_verified=None):
    row = {
        "chain": chain,
        "token": token,
        "symbol": "TEST",
        "pair_address": "0xPAIR",
    }
    if market_age_days is not None:
        row["market_age_days"] = market_age_days
    if market_age_verified is not None:
        row["market_age_verified"] = market_age_verified
    return row


def _reset(monkeypatch, tmp_path, sent=None):
    (tmp_path / "telegram-alert-state.json").write_text(
        json.dumps({"sent": sent or {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WALLET500_OUTPUT_DIR", str(tmp_path))
    first_seen._seen_tokens_cache = None
    first_seen._claimed_this_run.clear()


def test_new_to_engine_marker_is_added_only_on_first_telegram_appearance(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    row = _row()
    first = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: TEST", row)
    second = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: TEST", row)
    assert first_seen.NEW_TO_ENGINE_MARKER in first
    assert first_seen.LEGACY_ALWAYS_NEW_MARKER not in first
    assert first_seen.NEW_TO_ENGINE_MARKER not in second
    assert first_seen.LEGACY_ALWAYS_NEW_MARKER not in second


def test_verified_old_market_is_explicitly_not_a_new_launch(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    row = _row(market_age_days=359, market_age_verified=True)
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\nToken: 0G", row)
    assert first_seen.NEW_TO_ENGINE_MARKER in text
    assert first_seen.EXISTING_MARKET_MARKER in text
    assert "verified age 359d" in text
    assert first_seen.NEWLY_LAUNCHED_MARKER not in text


def test_verified_seven_day_token_gets_separate_newly_launched_label(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    row = _row(market_age_days=7, market_age_verified=True)
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\nToken: TEST", row)
    assert first_seen.NEW_TO_ENGINE_MARKER in text
    assert first_seen.NEWLY_LAUNCHED_MARKER in text
    assert first_seen.EXISTING_MARKET_MARKER not in text


def test_unverified_age_never_claims_newly_launched(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    row = _row(market_age_days=1, market_age_verified=False)
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\nToken: TEST", row)
    assert first_seen.NEW_TO_ENGINE_MARKER in text
    assert first_seen.NEWLY_LAUNCHED_MARKER not in text
    assert first_seen.EXISTING_MARKET_MARKER not in text


def test_pair_age_alone_cannot_claim_newly_launched(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    row = _row(market_age_days=359, market_age_verified=True)
    row["pair_age_minutes"] = 15
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\nToken: OLD", row)
    assert first_seen.EXISTING_MARKET_MARKER in text
    assert first_seen.NEWLY_LAUNCHED_MARKER not in text


def test_historical_real_alert_token_does_not_get_new_marker(tmp_path, monkeypatch):
    _reset(
        monkeypatch,
        tmp_path,
        {"bsc:0xabc:0xpair": {"symbol": "OLD"}},
    )
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: OLD", _row())
    assert first_seen.NEW_TO_ENGINE_MARKER not in text
    assert first_seen.LEGACY_ALWAYS_NEW_MARKER not in text


def test_historical_pre_wave_also_prevents_second_new_marker(tmp_path, monkeypatch):
    _reset(
        monkeypatch,
        tmp_path,
        {"PRE_WAVE:ethereum:0xabc:0xpair": {"symbol": "OLD"}},
    )
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: OLD", _row(chain="ethereum"))
    assert first_seen.NEW_TO_ENGINE_MARKER not in text


def test_bnb_and_bsc_share_same_token_identity(tmp_path, monkeypatch):
    _reset(
        monkeypatch,
        tmp_path,
        {"bsc:0xabc:0xpair": {"symbol": "OLD"}},
    )
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT", _row(chain="bnb"))
    assert first_seen.NEW_TO_ENGINE_MARKER not in text
