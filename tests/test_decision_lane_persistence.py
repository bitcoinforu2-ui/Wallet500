import json
from pathlib import Path

from wallet500.decision_lane_persistence import build


def _row(*, readiness=6, strong=False, pair="PAIR1", score=50, lanes=None, blockers=None):
    missing = [] if strong else ["STRONG_DECISION_LANE"]
    if blockers is None:
        blockers = [] if strong else ["NO_STRONG_DECISION_LANE"]
    return {
        "symbol": "TEST",
        "chain": "solana",
        "token_address": "TOKEN1",
        "pair_address": pair,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "execution_pool_liquidity_usd": 100000,
        "readiness_passed": readiness,
        "readiness_total": 7,
        "readiness_gates": {
            "EXACT_IDENTITY": True,
            "EXACT_DEX_PAIR": True,
            "VETERAN_AGE_180D": True,
            "EXECUTION_LIQUIDITY": True,
            "RISK_CLEAR": True,
            "STRONG_DECISION_LANE": strong,
            "INDEPENDENT_CONFIRMATION": True,
        },
        "missing_gates": missing,
        "blockers": blockers,
        "source_lanes": lanes or ["CEX_REVIVAL", "MULTICHAIN_VETERAN_REVIVAL"],
        "source_lane_count": len(lanes or ["CEX_REVIVAL", "MULTICHAIN_VETERAN_REVIVAL"]),
        "signal_score": score,
        "radar_tier": "REAL_ALERT" if strong and readiness == 7 else "NEAR_ALERT",
        "status": "REAL_ALERT" if strong and readiness == 7 else "VERIFIED_WATCH_NOT_REAL_ALERT",
    }


def _write_real(tmp_path: Path, row: dict, stamp: str):
    payload = {
        "generated_at": stamp,
        "alerts": [row] if row.get("status") == "REAL_ALERT" else [],
        "verified_watch": [] if row.get("status") == "REAL_ALERT" else [row],
    }
    (tmp_path / "real-alerts.json").write_text(json.dumps(payload), encoding="utf-8")


def test_six_of_seven_is_building_and_never_actionable(tmp_path):
    _write_real(tmp_path, _row(), "2026-09-12T10:00:00+00:00")
    out = build(tmp_path)
    candidate = out["candidates"][0]
    assert candidate["strong_lane_streak"] == 0
    assert candidate["shadow_persistence_status"] == "STRONG_LANE_BUILDING"
    assert candidate["automatic_buy"] is False
    assert out["truth_contract"]["real_alert_gate_changed"] is False
    assert out["truth_contract"]["telegram_alerts_changed"] is False


def test_first_seven_of_seven_is_transient(tmp_path):
    _write_real(tmp_path, _row(readiness=7, strong=True), "2026-09-12T10:05:00+00:00")
    out = build(tmp_path)
    candidate = out["candidates"][0]
    assert candidate["strong_lane_streak"] == 1
    assert candidate["shadow_persistence_status"] == "7_OF_7_TRANSIENT"


def test_second_consecutive_seven_of_seven_is_confirmed(tmp_path):
    _write_real(tmp_path, _row(readiness=7, strong=True), "2026-09-12T10:05:00+00:00")
    first = build(tmp_path)
    assert first["candidates"][0]["strong_lane_streak"] == 1
    _write_real(tmp_path, _row(readiness=7, strong=True, score=55), "2026-09-12T10:10:00+00:00")
    second = build(tmp_path)
    candidate = second["candidates"][0]
    assert candidate["strong_lane_streak"] == 2
    assert candidate["shadow_persistence_status"] == "7_OF_7_CONFIRMED"
    assert candidate["strong_lane_first_seen_at"] == "2026-09-12T10:05:00+00:00"
    assert second["new_transition_count"] == 1


def test_regression_resets_streak_and_records_exact_transition(tmp_path):
    _write_real(tmp_path, _row(readiness=7, strong=True, lanes=["CEX_REVIVAL", "MULTICHAIN_VETERAN_REVIVAL", "REVIVAL_MARKET_STRUCTURE"]), "2026-09-12T10:05:00+00:00")
    build(tmp_path)
    _write_real(tmp_path, _row(readiness=7, strong=True, lanes=["CEX_REVIVAL", "MULTICHAIN_VETERAN_REVIVAL", "REVIVAL_MARKET_STRUCTURE"]), "2026-09-12T10:10:00+00:00")
    build(tmp_path)
    _write_real(tmp_path, _row(readiness=6, strong=False, score=40, lanes=["CEX_REVIVAL", "MULTICHAIN_VETERAN_REVIVAL"]), "2026-09-12T10:15:00+00:00")
    out = build(tmp_path)
    candidate = out["candidates"][0]
    assert candidate["strong_lane_streak"] == 0
    event = out["transition_ledger"][-1]
    assert "READINESS_7_TO_6" in event["reason_codes"]
    assert "STRONG_DECISION_LANE_LOST" in event["reason_codes"]
    assert "NO_STRONG_DECISION_LANE_BLOCKER_RETURNED" in event["reason_codes"]
    assert event["removed_source_lanes"] == ["REVIVAL_MARKET_STRUCTURE"]
    assert event["source_lane_count_delta"] == -1


def test_pair_identity_isolation_prevents_pool_mixing(tmp_path):
    first = _row(readiness=7, strong=True, pair="PAIR1")
    _write_real(tmp_path, first, "2026-09-12T10:05:00+00:00")
    build(tmp_path)
    second = _row(readiness=7, strong=True, pair="PAIR2")
    _write_real(tmp_path, second, "2026-09-12T10:10:00+00:00")
    out = build(tmp_path)
    candidate = out["candidates"][0]
    assert candidate["pair_address"] == "PAIR2"
    assert candidate["strong_lane_streak"] == 1
    assert candidate["shadow_persistence_status"] == "7_OF_7_TRANSIENT"


def test_candidate_states_are_isolated(tmp_path):
    payload = {
        "generated_at": "2026-09-12T10:00:00+00:00",
        "alerts": [_row(readiness=7, strong=True, pair="PAIR1")],
        "verified_watch": [{**_row(pair="PAIR2"), "token_address": "TOKEN2"}],
    }
    (tmp_path / "real-alerts.json").write_text(json.dumps(payload), encoding="utf-8")
    first = build(tmp_path)
    assert len(first["candidates"]) == 2
    payload["generated_at"] = "2026-09-12T10:05:00+00:00"
    (tmp_path / "real-alerts.json").write_text(json.dumps(payload), encoding="utf-8")
    second = build(tmp_path)
    by_token = {x["token_address"]: x for x in second["candidates"]}
    assert by_token["TOKEN1"]["strong_lane_streak"] == 2
    assert by_token["TOKEN2"]["strong_lane_streak"] == 0
