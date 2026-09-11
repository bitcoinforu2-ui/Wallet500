import json

import wallet500.telegram_alerts as telegram_alerts


def _canonical_real_alert():
    return {
        "status": "REAL_ALERT",
        "radar_tier": "REAL_ALERT",
        "actionable_research_alert": True,
        "automatic_buy": False,
        "symbol": "LOBSTER",
        "chain": "bsc",
        "token_address": "0xeccbb861c0dda7efd964010085488b69317e4444",
        "pair_address": "0x22af7297243c4eef12e2d5a4f888b92e56bf127c",
        "dex": "pancakeswap",
        "dex_url": "https://dexscreener.com/bsc/0x22af7297243c4eef12e2d5a4f888b92e56bf127c",
        "price_usd": 0.05912,
        "execution_pool_liquidity_usd": 2_054_714.75,
        "market_age_days": 190,
        "market_age_verified": True,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "score": 88.0,
        "dex_volume_h1": 25_000.0,
        "buys_h1": 70,
        "sells_h1": 49,
        "readiness_gates": {
            "EXACT_IDENTITY": True,
            "EXACT_DEX_PAIR": True,
            "VETERAN_AGE_180D": True,
            "EXECUTION_LIQUIDITY": True,
            "RISK_CLEAR": True,
            "STRONG_DECISION_LANE": True,
            "INDEPENDENT_CONFIRMATION": True,
        },
        "readiness_passed": 7,
        "readiness_total": 7,
        "missing_gates": [],
        "blockers": [],
        "risk_level": "CLEAR",
        "risk_reasons": [],
        "concentrated_liquidity_pool": False,
        "execution_depth_verified": False,
        "dex_activity_truth": {"blockers": []},
        "source_lanes": ["MULTICHAIN_VETERAN_STRONG", "CEX_SPOT_BREADTH"],
        "source_lane_count": 2,
        "first_alert_at": "2026-09-11T16:32:43+00:00",
    }


def test_canonical_real_alert_is_independently_fail_closed():
    row = _canonical_real_alert()
    assert telegram_alerts._canonical_real_tier(row) == "QUALIFIED"

    blocked = dict(row)
    blocked["blockers"] = ["SOMETHING_UNRESOLVED"]
    assert telegram_alerts._canonical_real_tier(blocked) is None

    low_liquidity = dict(row)
    low_liquidity["execution_pool_liquidity_usd"] = 49_999
    assert telegram_alerts._canonical_real_tier(low_liquidity) is None

    incomplete = dict(row)
    incomplete["readiness_passed"] = 6
    assert telegram_alerts._canonical_real_tier(incomplete) is None

    concentrated = dict(row)
    concentrated["concentrated_liquidity_pool"] = True
    concentrated["execution_depth_verified"] = False
    assert telegram_alerts._canonical_real_tier(concentrated) is None


def test_real_alert_delivers_when_legacy_candidate_file_is_empty(tmp_path, monkeypatch):
    real = _canonical_real_alert()
    (tmp_path / "active-qualified-candidates.json").write_text("[]", encoding="utf-8")
    (tmp_path / "real-alerts.json").write_text(
        json.dumps({"alerts": [real], "pre_wave_alerts": []}), encoding="utf-8"
    )
    (tmp_path / "telegram-alert-state.json").write_text('{"sent": {}}', encoding="utf-8")
    (tmp_path / "telegram-alert-report.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("WALLET500_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(telegram_alerts, "_send", lambda *args, **kwargs: (999, 1))

    report = telegram_alerts.run()
    key = telegram_alerts._pair_key(real)
    state = json.loads((tmp_path / "telegram-alert-state.json").read_text(encoding="utf-8"))

    assert report["version"] == 13
    assert report["candidate_count"] == 0
    assert report["real_alert_count"] == 1
    assert report["eligible_count"] == 1
    assert report["delivered_count"] == 1
    assert report["error_count"] == 0
    assert report["delivered"][0]["key"] == key
    assert report["delivered"][0]["delivery_truth_source"] == "CANONICAL_REAL_ALERT"
    assert state["sent"][key]["actionable"] is True
    assert state["sent"][key]["telegram_message_id"] == 999


def test_existing_actionable_state_dedupes_but_remains_active(tmp_path, monkeypatch):
    real = _canonical_real_alert()
    key = telegram_alerts._pair_key(real)
    (tmp_path / "active-qualified-candidates.json").write_text("[]", encoding="utf-8")
    (tmp_path / "real-alerts.json").write_text(
        json.dumps({"alerts": [real], "pre_wave_alerts": []}), encoding="utf-8"
    )
    (tmp_path / "telegram-alert-state.json").write_text(
        json.dumps({"sent": {key: {"actionable": True, "telegram_message_id": 777}}}), encoding="utf-8"
    )
    (tmp_path / "telegram-alert-report.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("WALLET500_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    def fail_send(*args, **kwargs):
        raise AssertionError("deduped REAL ALERT must not be sent twice")

    monkeypatch.setattr(telegram_alerts, "_send", fail_send)
    report = telegram_alerts.run()
    state = json.loads((tmp_path / "telegram-alert-state.json").read_text(encoding="utf-8"))

    assert report["eligible_count"] == 1
    assert report["delivered_count"] == 0
    assert state["sent"][key]["actionable"] is True
