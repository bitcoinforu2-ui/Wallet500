from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.run_telegram_with_intelligence_shadow import _buy_message
from wallet500 import stage_transition_telegram as stage
from wallet500.telegram_buy_policy import filter_buy_only_payload


MODE = "SHADOW_DECISION_ONLY_NO_REAL_MONEY_NO_PRODUCTION_GATE_CHANGE"
NOW = datetime(2026, 9, 18, 0, 45, tzinfo=timezone.utc)


def _real_payload(pair: str = "0xpair") -> dict:
    return {
        "alerts": [
            {
                "status": "REAL_ALERT",
                "chain": "ethereum",
                "token_address": "0xabc",
                "pair_address": pair,
                "symbol": "TEST",
            }
        ],
        "pre_wave_alerts": [
            {
                "status": "PRE_WAVE",
                "chain": "ethereum",
                "token_address": "0xabc",
                "pair_address": pair,
                "symbol": "TEST",
            }
        ],
        "counts": {},
    }


def _decision_payload(
    *,
    action: str = "BUY",
    pair: str = "0xpair",
    generated_at: datetime = NOW,
) -> dict:
    is_buy = action == "BUY"
    return {
        "mode": MODE,
        "production_change": False,
        "generated_at": generated_at.isoformat(),
        "truth_contract": {
            "exact_pair_required": True,
            "holder_cluster_fail_closed_for_buy": True,
            "lp_protection_fail_closed_for_buy": True,
            "executable_exit_depth_fail_closed_for_buy": True,
        },
        "decisions": [
            {
                "key": f"ethereum:0xabc:{pair}",
                "chain": "ethereum",
                "token": "0xabc",
                "pair_address": pair,
                "recommended_action": action,
                "state": "BUY_ZONE" if is_buy else "WAIT",
                "model_signal": "BUY" if is_buy else "HOLD",
                "hard_safety_failures": [],
                "evidence_gaps": [],
                "scores": {"composite": 88.0, "confidence": 82.0},
            }
        ],
    }


def test_generic_real_alert_and_pre_wave_are_suppressed_without_final_buy():
    filtered, audit = filter_buy_only_payload(
        _real_payload(),
        _decision_payload(action="HOLD"),
        now=NOW,
    )

    assert filtered["alerts"] == []
    assert filtered["pre_wave_alerts"] == []
    assert audit["suppressed_generic_real_alert_count"] == 1
    assert audit["suppressed_pre_wave_count"] == 1
    assert audit["matched_buy_alert_count"] == 0


def test_final_buy_requires_exact_pair_and_adds_buy_metadata():
    filtered, audit = filter_buy_only_payload(
        _real_payload(),
        _decision_payload(),
        now=NOW,
    )

    assert audit["decision_snapshot_status"] == "VALID"
    assert audit["matched_buy_alert_count"] == 1
    assert len(filtered["alerts"]) == 1
    decision = filtered["alerts"][0]["telegram_buy_decision"]
    assert decision["recommended_action"] == "BUY"
    assert decision["state"] == "BUY_ZONE"

    wrong_pair, wrong_audit = filter_buy_only_payload(
        _real_payload(),
        _decision_payload(pair="0xother"),
        now=NOW,
    )
    assert wrong_pair["alerts"] == []
    assert wrong_audit["matched_buy_alert_count"] == 0


def test_stale_decision_snapshot_fails_closed():
    filtered, audit = filter_buy_only_payload(
        _real_payload(),
        _decision_payload(generated_at=NOW - timedelta(minutes=36)),
        now=NOW,
    )

    assert filtered["alerts"] == []
    assert audit["decision_snapshot_status"] == "DECISION_SNAPSHOT_STALE"


def test_buy_message_is_explicit_and_not_a_research_review():
    baseline = "\n".join(
        [
            "🚨 BUY REVIEW — WALLET500",
            "🆕 NEW REAL ALERT",
            "⚠️ MANUAL DECISION ONLY — NO AUTOMATIC TRADE",
            "Promotion: VERIFIED → ACTIONABLE ✅",
            "Actionable research alert: YES ✅",
        ]
    )
    row = {
        "telegram_buy_decision": {
            "recommended_action": "BUY",
            "state": "BUY_ZONE",
            "model_signal": "BUY",
            "scores": {"composite": 88.0, "confidence": 82.0},
        }
    }

    message = _buy_message(baseline, row)

    assert message.startswith("🟢 קנייה / BUY — WALLET500")
    assert "🆕 NEW BUY SIGNAL" in message
    assert "Decision Engine: BUY ✅" in message
    assert "Decision state: BUY_ZONE ✅" in message
    assert "Actionable research alert" not in message
    assert "MANUAL DECISION ONLY — NO AUTOMATIC TRADE" in message


def test_stage_lane_is_silent_even_for_paper_buy_candidate(monkeypatch, tmp_path):
    source_path = tmp_path / stage.SOURCE
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    base = {
        "token_address": "mint1",
        "pair_address": "0xpair",
        "symbol": "TEST",
        "status": "PAPER_BUY_CANDIDATE",
        "market": {"liquidity_usd": 100000},
        "coverage": {"verified_independent_count": 4, "positive_independent_count": 3},
        "pending_confirmations": [],
        "blockers": [],
    }
    source_path.write_text(json.dumps({"candidates": [base]}), encoding="utf-8")

    sent: list[str] = []

    def sender(_token, _chat_id, message):
        sent.append(message)
        return "1", 1

    first = stage.run(str(tmp_path), now=NOW, sender=sender)
    assert first["baseline_only"] is True
    assert first["delivered_count"] == 0

    weaker = dict(base)
    weaker["status"] = "EVIDENCE_READY"
    source_path.write_text(json.dumps({"candidates": [weaker]}), encoding="utf-8")
    stage.run(str(tmp_path), now=NOW + timedelta(minutes=1), sender=sender)

    source_path.write_text(json.dumps({"candidates": [base]}), encoding="utf-8")
    second = stage.run(str(tmp_path), now=NOW + timedelta(minutes=2), sender=sender)

    assert second["eligible_count"] == 0
    assert second["delivered_count"] == 0
    assert second["policy"]["telegram_delivery_enabled"] is False
    assert second["policy"]["final_buy_only"] is True
    assert sent == []
