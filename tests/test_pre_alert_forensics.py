from datetime import datetime, timedelta, timezone

from wallet500.pre_alert_forensics import (
    MODE_ENFORCE,
    MODE_SHADOW,
    _market_from_row,
    build_delivery_payload,
    evaluate_candidate,
    gate_allows_send,
    pair_key,
)


NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def _row():
    return {
        "status": "REAL_ALERT",
        "actionable_research_alert": True,
        "chain": "solana",
        "token_address": "TokenMint111",
        "pair_address": "Pair111",
        "exact_pair_verified": True,
        "price_usd": 1.0,
        "execution_pool_liquidity_usd": 100000,
    }


def _holder(status="PASS", complete=True):
    return {
        "chain": "solana",
        "token": "TokenMint111",
        "pair_address": "Pair111",
        "checked_at": NOW.isoformat(),
        "status": status,
        "verification_complete": complete,
        "gross_top10_pct": 42.0,
        "adjusted_real_top1_pct": 8.0,
        "adjusted_real_top5_pct": 24.0,
        "adjusted_real_top10_pct": 38.0,
        "known_infrastructure_pct": 12.0,
        "cex_custody_pct": 7.0,
        "unknown_holder_pct_observed": 20.0,
        "blockable_cluster_risks": [],
        "corroborated_cluster_risks": [],
        "linked_cluster_candidates": [],
        "verified_native_funding_edges": [],
        "reasons": [],
        "holders": [
            {"owner": "w1", "pct": 8.0, "excluded_from_whale_concentration": False},
            {"owner": "w2", "pct": 7.0, "excluded_from_whale_concentration": False},
        ],
    }


def _market(**overrides):
    row = {
        "source": "DEXSCREENER_EXACT_PAIR_LIVE",
        "checked_at": NOW.isoformat(),
        "complete": True,
        "price_usd": 1.0,
        "liquidity_usd": 100000.0,
        "volume_h1_usd": 25000.0,
        "price_change_h1_pct": 4.0,
        "price_change_h6_pct": 9.0,
        "price_change_h24_pct": 20.0,
        "buys_h1": 80,
        "sells_h1": 40,
    }
    row.update(overrides)
    return row


def _smart():
    return {
        "status": "QUALIFIED_RECENT_PAIR_TOUCH",
        "confidence": 0.8,
        "qualified_recent_signers": [{"wallet": "smart1", "tier": "STRONG"}],
        "side_inference": "NOT_CLAIMED_FROM_SIGNER_TOUCH_ALONE",
    }



def test_canonical_snapshot_preserves_explicit_zero_liquidity_and_volume():
    row = _row()
    row.update({
        "execution_pool_liquidity_usd": 0,
        "liquidity_usd": 100000,
        "dex_volume_h1": 0,
        "volume_h1": 25000,
        "price_change_h1_pct": 0,
        "price_change_h1": 8,
    })
    market = _market_from_row(row, checked_at=NOW.isoformat())
    assert market["liquidity_usd"] == 0.0
    assert market["volume_h1_usd"] == 0.0
    assert market["price_change_h1_pct"] == 0.0


def test_arc_pair_key_uses_evm_case_insensitive_identity():
    row = {
        "chain": "arc",
        "token_address": "0xAbCd",
        "pair_address": "0xDeF0",
    }
    assert pair_key(row) == "arc:0xabcd:0xdef0"


def test_complete_strong_evidence_is_actionable_in_enforce():
    result = evaluate_candidate(
        _row(),
        _holder(),
        _market(),
        [],
        _smart(),
        mode=MODE_ENFORCE,
        now=NOW,
    )
    assert result["decision"] == "ACTIONABLE"
    assert result["send_allowed"] is True
    assert result["critical_evidence_complete"] is True
    assert result["wallet_forensics_score"] >= 75
    assert result["entry_timing_score"] >= 75


def test_late_move_becomes_wait_for_retest():
    result = evaluate_candidate(
        _row(),
        _holder(),
        _market(price_change_h1_pct=36.0, price_change_h6_pct=70.0),
        [],
        _smart(),
        mode=MODE_ENFORCE,
        now=NOW,
    )
    assert result["decision"] == "WAIT_FOR_RETEST"
    assert result["send_allowed"] is False
    assert result["entry_timing"]["state"] == "WAIT_FOR_RETEST"


def test_high_cluster_risk_becomes_research_only():
    holder = _holder(status="BLOCK")
    holder["blockable_cluster_risks"] = [{"combined_pct": 28.0, "risk_corroborated": True}]
    result = evaluate_candidate(
        _row(),
        holder,
        _market(),
        [],
        _smart(),
        mode=MODE_ENFORCE,
        now=NOW,
    )
    assert result["decision"] == "RESEARCH_ONLY"
    assert "HIGH_CORROBORATED_BUNDLE_CLUSTER_RISK" in result["blockers"]
    assert result["send_allowed"] is False


def test_missing_or_stale_critical_evidence_fails_closed_in_enforce():
    stale = _holder()
    stale["checked_at"] = (NOW - timedelta(hours=2)).isoformat()
    result = evaluate_candidate(
        _row(),
        stale,
        _market(),
        [],
        _smart(),
        mode=MODE_ENFORCE,
        now=NOW,
        max_evidence_age_seconds=2400,
    )
    assert result["decision"] == "RESEARCH_ONLY"
    assert result["critical_evidence_complete"] is False
    assert result["send_allowed"] is False


def test_shadow_never_suppresses_current_real_alert_but_records_would_block():
    result = evaluate_candidate(
        _row(),
        None,
        None,
        [],
        None,
        mode=MODE_SHADOW,
        now=NOW,
    )
    assert result["would_block"] is True
    assert result["send_allowed"] is True
    report = {"mode": MODE_SHADOW, "results": [result]}
    allowed, evidence = gate_allows_send(_row(), report)
    assert allowed is True
    assert evidence["decision"] == "RESEARCH_ONLY"


def test_enforce_requires_matching_actionable_forensics_result():
    allowed, evidence = gate_allows_send(_row(), {"mode": MODE_ENFORCE, "results": []})
    assert allowed is False
    assert evidence is None
    result = evaluate_candidate(
        _row(), _holder(), _market(), [], _smart(), mode=MODE_ENFORCE, now=NOW
    )
    allowed, evidence = gate_allows_send(
        _row(), {"mode": MODE_ENFORCE, "results": [result]}
    )
    assert allowed is True
    assert evidence["decision"] == "ACTIONABLE"


def test_whale_flow_uses_snapshot_deltas_without_claiming_transaction_netflow():
    history = [
        {
            "at": (NOW - timedelta(hours=7)).isoformat(),
            "price_usd": 0.9,
            "adjusted_top10_pct": 30.0,
            "cex_custody_pct": 5.0,
            "real_holder_pct": {"w1": 5.0, "w2": 5.0},
        }
    ]
    result = evaluate_candidate(
        _row(), _holder(), _market(), history, _smart(), mode=MODE_ENFORCE, now=NOW
    )
    assert result["whale_flow"]["method"] == "SNAPSHOT_HOLDER_BALANCE_DELTA_NOT_TRANSACTION_NETFLOW"
    assert result["whale_flow"]["h6"]["status"] == "ACCUMULATION"


def test_pair_key_is_exact_pair_scoped():
    assert pair_key(_row()) == "solana:TokenMint111:Pair111"


def test_delivery_payload_is_non_suppressing_in_shadow_and_fail_closed_in_enforce():
    real_payload = {"alerts": [_row()], "pre_wave_alerts": [{"status": "PRE_WAVE_ALERT"}]}
    blocked = evaluate_candidate(_row(), None, None, [], None, mode=MODE_SHADOW, now=NOW)
    shadow = build_delivery_payload(real_payload, {"mode": MODE_SHADOW, "results": [blocked]})
    assert len(shadow["alerts"]) == 1
    assert shadow["pre_alert_forensics"]["shadow_only"] is True

    blocked_enforce = dict(blocked)
    blocked_enforce["mode"] = MODE_ENFORCE
    blocked_enforce["send_allowed"] = False
    enforce = build_delivery_payload(real_payload, {"mode": MODE_ENFORCE, "results": [blocked_enforce]})
    assert enforce["alerts"] == []
    assert enforce["pre_wave_alerts"] == [{"status": "PRE_WAVE_ALERT"}]
    assert enforce["pre_alert_forensics"]["suppressed_real_alert_count"] == 1
