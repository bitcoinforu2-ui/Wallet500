import json

import wallet500.telegram_first_seen as first_seen


def _row(token="0xABC", chain="bsc"):
    return {
        "chain": chain,
        "token": token,
        "symbol": "TEST",
        "pair_address": "0xPAIR",
    }


def _reset(monkeypatch, tmp_path, sent=None):
    (tmp_path / "telegram-alert-state.json").write_text(
        json.dumps({"sent": sent or {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WALLET500_OUTPUT_DIR", str(tmp_path))
    first_seen._seen_tokens_cache = None
    first_seen._claimed_this_run.clear()


def test_new_marker_is_added_only_on_first_telegram_appearance(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    row = _row()
    first = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: TEST", row)
    second = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: TEST", row)
    assert first_seen.NEW_MARKER in first
    assert first_seen.LEGACY_ALWAYS_NEW_MARKER not in first
    assert first_seen.NEW_MARKER not in second
    assert first_seen.LEGACY_ALWAYS_NEW_MARKER not in second


def test_historical_real_alert_token_does_not_get_new_marker(tmp_path, monkeypatch):
    _reset(
        monkeypatch,
        tmp_path,
        {"bsc:0xabc:0xpair": {"symbol": "OLD"}},
    )
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: OLD", _row())
    assert first_seen.NEW_MARKER not in text
    assert first_seen.LEGACY_ALWAYS_NEW_MARKER not in text


def test_historical_pre_wave_also_prevents_second_new_marker(tmp_path, monkeypatch):
    _reset(
        monkeypatch,
        tmp_path,
        {"PRE_WAVE:ethereum:0xabc:0xpair": {"symbol": "OLD"}},
    )
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT\nToken: OLD", _row(chain="ethereum"))
    assert first_seen.NEW_MARKER not in text


def test_bnb_and_bsc_share_same_token_identity(tmp_path, monkeypatch):
    _reset(
        monkeypatch,
        tmp_path,
        {"bsc:0xabc:0xpair": {"symbol": "OLD"}},
    )
    text = first_seen._mark_first_seen("🚨 BUY REVIEW — WALLET500\n🆕 NEW REAL ALERT", _row(chain="bnb"))
    assert first_seen.NEW_MARKER not in text
