import json
from datetime import datetime, timedelta, timezone

from wallet500.social_runner_telegram import run


NOW = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)


def _social_row(state="CONFIRMED_RUNNER", chain="solana", contract="MintA"):
    return {
        "observed_at": NOW.isoformat(),
        "chain": chain,
        "contract": contract,
        "symbol": "AAA",
        "features": {
            "attention_jump_3h_vs_21d": 4.2,
            "velocity_3d_vs_21d": 2.7,
            "organic_share": 0.86,
            "unique_communities": 9,
            "first_time_communities": 4,
            "cross_platform_count": 2,
        },
        "classification": {
            "state": state,
            "market_confirmations": 2,
            "onchain_confirmations": 1,
            "late_attention_penalty": False,
            "distribution_risk": False,
            "false_social_risk": False,
            "reasons": ["ATTENTION_ACCELERATION", "ORGANIC_QUALITY"],
            "automatic_buy": False,
            "production_effect": False,
        },
    }


def _candidate(status="PAPER_BUY_CANDIDATE", chain="solana", token="MintA", pair="PairA"):
    return {
        "chain": chain,
        "token_address": token,
        "pair_address": pair,
        "symbol": "AAA",
        "status": status,
    }


def _write_sources(tmp_path, social_rows=None, candidates=None, generated_at=None):
    ts = generated_at or NOW.isoformat()
    (tmp_path / "social-runner-research.json").write_text(
        json.dumps(
            {
                "mode": "RESEARCH_ONLY_SOCIAL_RUNNER_INTELLIGENCE_V1",
                "generated_at": ts,
                "research_only": True,
                "production_effect": False,
                "automatic_buy": False,
                "rows": social_rows if social_rows is not None else [_social_row()],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate-evidence-envelope.json").write_text(
        json.dumps(
            {
                "mode": "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1",
                "generated_at": ts,
                "production_change": False,
                "automatic_buy": False,
                "candidates": candidates if candidates is not None else [_candidate()],
            }
        ),
        encoding="utf-8",
    )


def test_confirmed_runner_plus_prebuy_sends_once(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write_sources(tmp_path)
    sent = []
    report = run(str(tmp_path), NOW, sender=lambda *args: (sent.append(args) or (55, 1)))
    assert report["eligible_count"] == 1
    assert report["delivered_count"] == 1
    assert "קרוב מאוד לקנייה" in sent[0][2]
    assert "עדיין לא BUY" in sent[0][2]
    assert "https://dexscreener.com/solana/paira" in sent[0][2]

    again = run(
        str(tmp_path),
        NOW,
        sender=lambda *args: (_ for _ in ()).throw(AssertionError("duplicate")),
    )
    assert again["eligible_count"] == 0
    assert again["delivered_count"] == 0


def test_early_runner_stays_silent_even_when_candidate_is_prebuy(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write_sources(tmp_path, social_rows=[_social_row("EARLY_RUNNER")])
    report = run(
        str(tmp_path),
        NOW,
        sender=lambda *args: (_ for _ in ()).throw(AssertionError("EARLY_RUNNER must stay silent")),
    )
    assert report["eligible_count"] == 0
    assert report["policy"]["early_runner_notifications"] is False


def test_confirmed_social_stays_silent_until_engine_reaches_prebuy(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write_sources(tmp_path, candidates=[_candidate("EVIDENCE_READY")])
    report = run(
        str(tmp_path),
        NOW,
        sender=lambda *args: (_ for _ in ()).throw(AssertionError("not prebuy")),
    )
    assert report["eligible_count"] == 0


def test_exact_chain_contract_and_pair_are_required(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write_sources(tmp_path, candidates=[_candidate(chain="", pair="")])
    report = run(
        str(tmp_path),
        NOW,
        sender=lambda *args: (_ for _ in ()).throw(AssertionError("ambiguous identity")),
    )
    assert report["eligible_count"] == 0
    assert report["policy"]["exact_chain_contract_pair_required"] is True


def test_late_or_distribution_social_stays_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    row = _social_row()
    row["classification"]["late_attention_penalty"] = True
    _write_sources(tmp_path, social_rows=[row])
    report = run(
        str(tmp_path),
        NOW,
        sender=lambda *args: (_ for _ in ()).throw(AssertionError("late attention")),
    )
    assert report["eligible_count"] == 0


def test_stale_sources_do_not_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    stale = (NOW - timedelta(hours=3)).isoformat()
    _write_sources(tmp_path, generated_at=stale)
    report = run(
        str(tmp_path),
        NOW,
        sender=lambda *args: (_ for _ in ()).throw(AssertionError("stale source")),
    )
    assert report["eligible_count"] == 0
    assert report["social_source_valid"] is False
    assert report["candidate_source_valid"] is False


def test_delivery_failure_does_not_consume_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write_sources(tmp_path)
    failed = run(
        str(tmp_path),
        NOW,
        sender=lambda *args: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert failed["error_count"] == 1
    retry = run(str(tmp_path), NOW, sender=lambda *args: (77, 1))
    assert retry["delivered_count"] == 1


def test_joint_state_resets_after_candidate_leaves_prebuy_and_can_alert_again(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write_sources(tmp_path)
    first = run(str(tmp_path), NOW, sender=lambda *args: (1, 1))
    assert first["delivered_count"] == 1

    _write_sources(tmp_path, candidates=[_candidate("EVIDENCE_READY")])
    quiet = run(str(tmp_path), NOW, sender=lambda *args: (2, 1))
    assert quiet["delivered_count"] == 0

    _write_sources(tmp_path, candidates=[_candidate("PAPER_BUY_CANDIDATE")])
    second = run(str(tmp_path), NOW, sender=lambda *args: (3, 1))
    assert second["delivered_count"] == 1


def test_missing_candidate_source_is_neutral_and_preserves_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write_sources(tmp_path)
    run(str(tmp_path), NOW, sender=lambda *args: (1, 1))
    (tmp_path / "candidate-evidence-envelope.json").write_text("", encoding="utf-8")
    report = run(str(tmp_path), NOW, sender=lambda *args: (2, 1))
    assert report["candidate_source_present"] is False
    assert report["candidate_source_valid"] is False
    assert report["delivered_count"] == 0
