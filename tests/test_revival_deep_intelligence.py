from __future__ import annotations

from datetime import datetime, timezone

from wallet500 import revival_deep_intelligence as deep


def _candidate():
    row = {
        "chain": "solana",
        "token_address": "Token1111111111111111111111111111111111111",
        "base_token_symbol": "FIRE",
        "pair_address": "Pair11111111111111111111111111111111111111",
    }
    meta = {
        "chain": "solana",
        "token_address": row["token_address"],
        "pair_address": row["pair_address"],
        "revival_score": 78.0,
    }
    return row, meta


def _install_good_evidence(monkeypatch, now):
    monkeypatch.setattr(
        deep.forensics,
        "fetch_exact_pair_market",
        lambda row: {
            "complete": True,
            "checked_at": now.isoformat(),
            "price_usd": 0.01,
            "liquidity_usd": 60_000,
            "volume_h1_usd": 30_000,
            "buys_h1": 60,
            "sells_h1": 40,
        },
    )
    monkeypatch.setattr(
        deep.forensics,
        "refresh_holder_evidence",
        lambda row: {
            "verification_complete": True,
            "checked_at": now.isoformat(),
            "status": "PASS",
        },
    )
    monkeypatch.setattr(deep.forensics, "refresh_wallet_evidence", lambda row: {"wallets": []})
    monkeypatch.setattr(
        deep.forensics,
        "smart_money_snapshot",
        lambda row, wallet, registry: {"status": "RECENT_SIGNERS_NO_QUALIFIED_SMART_MONEY_MATCH", "confidence": 0.35},
    )
    monkeypatch.setattr(
        deep.forensics,
        "evaluate_candidate",
        lambda *args, **kwargs: {
            "decision": "ACTIONABLE",
            "wallet_forensics_score": 88,
            "entry_timing_score": 84,
            "blockers": [],
            "holder_cluster": {"status": "PASS"},
            "smart_money_persistence": {"status": "RECENT_SIGNERS_NO_QUALIFIED_SMART_MONEY_MATCH"},
            "bundle_analysis": {"level": "LOW"},
            "entry_timing": {"state": "EARLY_VALID", "score": 84},
            "evidence_snapshot": {"at": now.isoformat(), "price_usd": 0.01, "liquidity_usd": 60_000},
        },
    )
    monkeypatch.setattr(
        deep.binance_web3,
        "fetch_audit",
        lambda chain, token: {
            "available": True,
            "risk_level_enum": "LOW",
            "risk_level": 1,
            "risk_flags": [],
            "buy_tax": 0,
            "sell_tax": 0,
            "is_verified": True,
        },
    )



def test_arc_deep_intelligence_key_is_case_insensitive():
    assert deep._key({
        "chain": "arc",
        "token_address": "0xAbCd",
        "pair_address": "0xDeF0",
    }) == "arc:0xabcd:0xdef0"


def test_deep_check_passes_only_after_critical_evidence(tmp_path, monkeypatch):
    now = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    _install_good_evidence(monkeypatch, now)
    report = deep.investigate_candidates([_candidate()], tmp_path, now)
    result = report["results"][0]
    assert result["status"] == "PASS"
    assert result["actionable"] is True
    assert result["revival_score"] == 78.0
    assert result["confirmation_score"] >= deep.PASS_SCORE
    assert result["hard_blockers"] == []
    assert result["critical_missing"] == []
    assert (tmp_path / deep.REPORT).exists()
    assert (tmp_path / deep.STATE).exists()


def test_missing_contract_security_can_never_pass(tmp_path, monkeypatch):
    now = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    _install_good_evidence(monkeypatch, now)
    monkeypatch.setattr(
        deep.binance_web3,
        "fetch_audit",
        lambda chain, token: {"available": False, "risk_level": None, "risk_flags": []},
    )
    result = deep.investigate_candidates([_candidate()], tmp_path, now)["results"][0]
    assert result["status"] == "WATCH"
    assert result["actionable"] is False
    assert "CONTRACT_SECURITY_EVIDENCE_UNAVAILABLE" in result["critical_missing"]
    assert result["confirmation_score"] <= 69.0


def test_hard_blocker_overrides_high_scores(tmp_path, monkeypatch):
    now = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    _install_good_evidence(monkeypatch, now)
    monkeypatch.setattr(
        deep.binance_web3,
        "fetch_audit",
        lambda chain, token: {
            "available": True,
            "risk_level_enum": "HIGH",
            "risk_level": 3,
            "risk_flags": ["BINANCE_AUDIT_RISK:Honeypot"],
        },
    )
    result = deep.investigate_candidates([_candidate()], tmp_path, now)["results"][0]
    assert result["status"] == "REJECT"
    assert result["actionable"] is False
    assert "CONTRACT_SECURITY_HIGH" in result["hard_blockers"]
    assert "CONTRACT_SECURITY_RISK_FLAG" in result["hard_blockers"]
    assert result["confirmation_score"] <= 39.0


def test_learning_state_is_forward_only_and_no_auto_tuning(tmp_path, monkeypatch):
    now = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    _install_good_evidence(monkeypatch, now)
    deep.investigate_candidates([_candidate()], tmp_path, now)
    import json

    state = json.loads((tmp_path / deep.STATE).read_text(encoding="utf-8"))
    contract = state["learning_contract"]
    assert contract["forward_snapshots_only"] is True
    assert contract["no_hindsight"] is True
    assert contract["no_single_token_auto_tuning"] is True
    assert contract["automatic_threshold_changes"] is False
    assert contract["intended_outcomes"] == ["1h", "6h", "24h", "72h", "max_upside", "drawdown", "liquidity_delta"]
