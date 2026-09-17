from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_telegram_with_intelligence_shadow.py"
SPEC = importlib.util.spec_from_file_location("wallet500_telegram_intelligence_shadow", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
shadow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shadow)


def _row(pair: str = "0xpair") -> dict:
    return {
        "symbol": "TEST",
        "chain": "ethereum",
        "token_address": "0xABC",
        "pair_address": pair,
    }


def _current_intel(pair: str = "0xpair") -> dict:
    return {
        "symbol": "TEST",
        "chain": "ethereum",
        "token_address": "0xabc",
        "pair_address": pair,
        "exact_identity_verified": True,
        "status": "CURRENT",
        "score": 72.5,
        "label": "CONFLUENCE",
        "independent_positive_families": 3,
        "current_evidence_count": 5,
        "family_scores": {"wallet_flow": 12.0, "attention_social": 4.5, "derivatives": -1.0},
        "freshest_event_at": "2026-09-17T10:00:00+00:00",
        "updated_at": "2026-09-17T10:02:00+00:00",
        "evidence_age_minutes": 2,
        "window_minutes": 180,
        "hard_risks": [],
    }


def test_shadow_missing_exact_pair_is_explicit_not_zero():
    lines = shadow.shadow_lines(_row(), {})
    text = "\n".join(lines)
    assert "NOT AVAILABLE (SHADOW)" in text
    assert "0.0/100" not in text
    assert "production eligibility is unchanged" in text


def test_shadow_wrong_pair_never_matches_same_symbol():
    intel = _current_intel("0xother")
    index = {shadow.identity_key(intel): intel}
    text = "\n".join(shadow.shadow_lines(_row("0xpair"), index))
    assert "NOT AVAILABLE (SHADOW)" in text
    assert "72.5/100" not in text


def test_shadow_unverified_identity_never_matches():
    intel = _current_intel()
    intel["exact_identity_verified"] = False
    index = {shadow.identity_key(intel): intel}
    text = "\n".join(shadow.shadow_lines(_row(), index))
    assert "NOT AVAILABLE (SHADOW)" in text
    assert "EXACT_IDENTITY_UNVERIFIED" in text
    assert "72.5/100" not in text


def test_load_index_excludes_unverified_identity(tmp_path):
    verified = _current_intel("0xverified")
    unverified = _current_intel("0xunverified")
    unverified["exact_identity_verified"] = False
    (tmp_path / "close-watch-intelligence.json").write_text(
        json.dumps({"tokens": [verified, unverified]}), encoding="utf-8"
    )
    index = shadow.load_index(tmp_path)
    assert shadow.identity_key(verified) in index
    assert shadow.identity_key(unverified) not in index


def test_shadow_stale_evidence_is_not_rendered_as_current_score():
    intel = _current_intel()
    intel.update({"status": "STALE_ONLY", "score": 0, "evidence_age_minutes": 240})
    index = {shadow.identity_key(intel): intel}
    text = "\n".join(shadow.shadow_lines(_row(), index))
    assert "STALE (SHADOW)" in text
    assert "0.0/100" not in text
    assert "240.0m" in text


def test_shadow_current_claim_with_stale_age_is_fail_closed():
    intel = _current_intel()
    intel["evidence_age_minutes"] = 240
    index = {shadow.identity_key(intel): intel}
    text = "\n".join(shadow.shadow_lines(_row(), index))
    assert "STALE (SHADOW)" in text
    assert "72.5/100" not in text


def test_shadow_current_without_verifiable_freshness_is_not_available():
    intel = _current_intel()
    intel["evidence_age_minutes"] = None
    index = {shadow.identity_key(intel): intel}
    text = "\n".join(shadow.shadow_lines(_row(), index))
    assert "NOT AVAILABLE (SHADOW)" in text
    assert "CURRENT_WITHOUT_VERIFIABLE_FRESHNESS" in text
    assert "72.5/100" not in text


def test_shadow_current_exact_pair_renders_fusion_metadata():
    intel = _current_intel()
    index = {shadow.identity_key(intel): intel}
    text = "\n".join(shadow.shadow_lines(_row(), index))
    assert "72.5/100 — CONFLUENCE (SHADOW)" in text
    assert "independent positive families: 3" in text
    assert "current evidence: 5" in text
    assert "wallet_flow 12.0" in text
    assert "derivatives" not in text
    assert "NOT USED TO PROMOTE/SUPPRESS THIS REAL_ALERT" in text


def test_safe_inject_never_blocks_alert_on_malformed_shadow():
    intel = _current_intel()
    intel["score"] = object()
    index = {shadow.identity_key(intel): intel}
    baseline = "MANUAL DECISION ONLY — NO AUTOMATIC TRADE\nVerified Intelligence. The Pure Truth."
    text = shadow.safe_inject(baseline, _row(), index)
    assert "MANUAL DECISION ONLY — NO AUTOMATIC TRADE" in text
    assert "NOT AVAILABLE (SHADOW)" in text
    assert "CURRENT_WITH_INVALID_SCORE" in text
    assert "Verified Intelligence. The Pure Truth." not in text


def test_main_restores_formatter_hooks_after_success(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET500_OUTPUT_DIR", str(tmp_path))
    (tmp_path / "close-watch-intelligence.json").write_text(json.dumps({"tokens": []}), encoding="utf-8")
    original_message = shadow.alerts._message
    original_pre_wave = shadow.alerts._pre_wave_message
    monkeypatch.setattr(shadow.alerts, "run", lambda: {"status": "TEST_OK"})

    assert shadow.main() == 0
    assert shadow.alerts._message is original_message
    assert shadow.alerts._pre_wave_message is original_pre_wave


def test_main_restores_formatter_hooks_after_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET500_OUTPUT_DIR", str(tmp_path))
    original_message = shadow.alerts._message
    original_pre_wave = shadow.alerts._pre_wave_message

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(shadow.alerts, "run", boom)
    with pytest.raises(RuntimeError, match="boom"):
        shadow.main()

    assert shadow.alerts._message is original_message
    assert shadow.alerts._pre_wave_message is original_pre_wave
