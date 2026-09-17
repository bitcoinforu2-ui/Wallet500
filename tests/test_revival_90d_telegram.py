from __future__ import annotations

import json
from datetime import datetime, timezone

from wallet500 import revival_90d_telegram as mod


def _row(**overrides):
    row = {
        "chain": "bsc",
        "token": "0xabc",
        "base_token_address": "0xAbC",
        "base_token_symbol": "FIRE",
        "pair_address": "0xPair",
        "pair_created_at": int(datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp() * 1000),
        "liquidity_usd": 20_000,
        "revival_score": 72,
        "volume_h1": 22_000,
        "buys_h1": 40,
        "sells_h1": 30,
        "url": "https://dexscreener.com/bsc/0xpair",
    }
    row.update(overrides)
    return row


def _deep_report(candidates, out, now):
    results = []
    for row, meta in candidates:
        results.append({
            "key": mod._key(meta),
            "status": "PASS",
            "actionable": True,
            "decision": "BUY CANDIDATE — MANUAL",
            "confirmation_score": 82.0,
            "hard_blockers": [],
            "critical_missing": [],
            "wallet_intel": {"status": "PASS", "smart_money": "QUALIFIED_RECENT_PAIR_TOUCH"},
            "flow_quality": {"status": "BUYERS_LEADING"},
            "liquidity_quality": {"status": "ADEQUATE"},
            "contract_security": {"status": "PASS"},
            "intelligence_context": {"status": "CURRENT"},
        })
    return {
        "pass_count": len(results),
        "watch_count": 0,
        "reject_count": 0,
        "results": results,
    }


def test_gate_accepts_90d_15k_actionable_case():
    ok, meta = mod._eligibility(_row(), datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert ok is True
    assert meta["liquidity_usd"] == 20_000
    assert meta["market_age_days"] >= 90


def test_gate_accepts_expanded_verified_solana_identity():
    row = {
        "network": "solana",
        "network_verified": True,
        "token_address": "Token1111111111111111111111111111111111111",
        "dex_pair_address": "Pair11111111111111111111111111111111111111",
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "market_age_verified": True,
        "market_age_min_days": 120,
        "dex_pair_liquidity_usd": 25_000,
        "revival_score_verified": 70,
        "live_h1": {"volume_h1": 21_000, "buys_h1": 20, "sells_h1": 15},
        "active_display_gate": {"pass": True},
    }
    ok, meta = mod._eligibility(row, datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert ok is True
    assert meta["market_age_verified"] is True


def test_gate_accepts_30_txns_and_rejects_29():
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ok30, meta30 = mod._eligibility(_row(buys_h1=15, sells_h1=15), now)
    ok29, meta29 = mod._eligibility(_row(buys_h1=15, sells_h1=14), now)
    assert ok30 is True
    assert meta30["txns_h1"] == 30
    assert ok29 is False
    assert "TXNS_H1_LT_30" in meta29["blockers"]


def test_gate_rejects_under_15k_and_wrong_identity():
    ok, meta = mod._eligibility(
        _row(liquidity_usd=14_999, base_token_address="0xdef"),
        datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    assert ok is False
    assert "LIQUIDITY_LT_15K" in meta["blockers"]
    assert "BASE_TOKEN_IDENTITY_NOT_VERIFIED" in meta["blockers"]


def test_forward_only_baseline_then_three_fire_transition(tmp_path, monkeypatch):
    src = tmp_path / mod.SOURCE
    src.write_text(json.dumps([_row()]), encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("REVIVAL_90D_LIVE_REFRESH", "0")
    monkeypatch.setattr(mod.deep_intelligence, "investigate_candidates", _deep_report)
    messages = []

    def fake_send(token, chat_id, text):
        messages.append(text)
        return 123, 1

    monkeypatch.setattr(mod, "_send", fake_send)
    now = datetime(2026, 9, 7, 19, 0, tzinfo=timezone.utc)

    baseline = mod.run(str(tmp_path), now=now)
    assert baseline["baseline_count"] == 1
    assert baseline["delivered_count"] == 0
    assert messages == []

    src.write_text(json.dumps([]), encoding="utf-8")
    mod.run(str(tmp_path), now=now)
    src.write_text(json.dumps([_row()]), encoding="utf-8")
    fired = mod.run(str(tmp_path), now=now)
    again = mod.run(str(tmp_path), now=now)

    assert fired["delivered_count"] == 1
    assert again["delivered_count"] == 0
    assert len(messages) == 1
    assert messages[0].startswith("🔥🔥🔥 REAL ALERT — REVIVAL 90D / 15K")
    assert "Deep Check: PASS" in messages[0]
    assert "Revival score: 72.0/100" in messages[0]
    assert "Confirmation score: 82.0/100" in messages[0]
    assert "Decision: BUY CANDIDATE — MANUAL" in messages[0]
    assert "Activity H1: 70 tx ✅ min 30" in messages[0]
    assert "Canonical Revival lane: 90d / $15K ✅" in messages[0]
    assert "RESEARCH ONLY" not in messages[0]
    assert fired["truth_contract"]["research_only"] is False
    assert fired["truth_contract"]["actionable_only"] is True
    assert fired["truth_contract"]["automatic_buy"] is False
    assert fired["truth_contract"]["minimum_txns_h1"] == 30
    assert fired["truth_contract"]["automatic_deep_intelligence_before_delivery"] is True
    assert fired["truth_contract"]["deep_check_pass_required_for_actionable_alert"] is True
    assert fired["truth_contract"]["no_historical_backfill"] is True


def test_deep_watch_never_reaches_actionable_alert(tmp_path, monkeypatch):
    (tmp_path / mod.SOURCE).write_text(json.dumps([_row()]), encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("REVIVAL_90D_LIVE_REFRESH", "0")

    def watch_report(candidates, out, now):
        _, meta = candidates[0]
        return {
            "pass_count": 0,
            "watch_count": 1,
            "reject_count": 0,
            "results": [{
                "key": mod._key(meta),
                "status": "WATCH",
                "actionable": False,
                "hard_blockers": [],
                "critical_missing": ["CONTRACT_SECURITY_EVIDENCE_UNAVAILABLE"],
            }],
        }

    monkeypatch.setattr(mod.deep_intelligence, "investigate_candidates", watch_report)
    sent = []
    monkeypatch.setattr(mod, "_send", lambda *args: sent.append(args) or (123, 1))
    result = mod.run(str(tmp_path), now=datetime(2026, 9, 7, 19, 0, tzinfo=timezone.utc))
    assert result["baseline_eligible_before_deep_check"] == 1
    assert result["eligible_count"] == 0
    assert result["deep_check_watch_count"] == 1
    assert result["delivered_count"] == 0
    assert sent == []


def test_no_secrets_never_marks_sent(tmp_path, monkeypatch):
    (tmp_path / mod.SOURCE).write_text(json.dumps([_row()]), encoding="utf-8")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("REVIVAL_90D_LIVE_REFRESH", "0")
    monkeypatch.setattr(mod.deep_intelligence, "investigate_candidates", _deep_report)
    result = mod.run(str(tmp_path), now=datetime(2026, 9, 7, 19, 0, tzinfo=timezone.utc))
    assert result["configured"] is False
    assert result["delivered_count"] == 0
    assert not (tmp_path / mod.STATE).exists()
