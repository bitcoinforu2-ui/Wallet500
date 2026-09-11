import json
from pathlib import Path

from wallet500 import cex_spot_identity as mod


def _pending_rows(n=100):
    return [
        {
            "symbol": f"OLD{i}USDT",
            "persistent_until_exact_identity_resolution": True,
            "timing_quality": "EARLY_BREAKOUT_EVIDENCE",
            "first_alert_score": 100 - (i % 50),
            "first_alert_coherent_confirmations": 4,
            "first_watch_score": 50,
            "first_watch_price_acceleration_max_pct": 3.0,
            "first_watch_volume_acceleration_max_pct": 10.0,
        }
        for i in range(n)
    ]


def _fresh_rows(n=40):
    return [
        {
            "symbol": f"NEW{i}USDT",
            "spot_revival_score": 50 - (i % 20),
            "coherent_confirmations": 2,
        }
        for i in range(n)
    ]


def test_1_capacity_100_backlog_40_fresh_is_bounded_and_fresh_protected():
    selected, report = mod._build_identity_queue(
        {"watchlist": _fresh_rows(40)},
        {"candidates": _pending_rows(100)},
        {},
    )
    symbols = {mod._base_symbol(r.get("symbol")) for r in selected}
    assert len(selected) == mod.MAX_WATCH_CANDIDATES == 60
    assert report["persistent_priority_slot_cap"] == 30
    assert report["selected_persistent_count"] == 30
    assert report["selected_current_count"] == 30
    assert len(symbols & {f"NEW{i}" for i in range(40)}) == 30
    assert report["fresh_watch_capacity_protected"] is True
    assert report["production_effect"] is False
    assert report["no_hindsight"] is True


def test_2_rotation_changes_backlog_members_across_three_cycles():
    spot = {"watchlist": _fresh_rows(10)}
    pending = {"candidates": _pending_rows(90)}

    s1, r1 = mod._build_identity_queue(spot, pending, {})
    p1 = {mod._base_symbol(r.get("symbol")) for r in s1 if mod._base_symbol(r.get("symbol")).startswith("OLD")}
    prev1 = {"candidates": [{"symbol": f"{s}USDT"} for s in p1], "rejections": []}

    s2, r2 = mod._build_identity_queue(spot, pending, prev1)
    p2 = {mod._base_symbol(r.get("symbol")) for r in s2 if mod._base_symbol(r.get("symbol")).startswith("OLD")}
    prev2 = {"candidates": [{"symbol": f"{s}USDT"} for s in p2], "rejections": []}

    s3, r3 = mod._build_identity_queue(spot, pending, prev2)
    p3 = {mod._base_symbol(r.get("symbol")) for r in s3 if mod._base_symbol(r.get("symbol")).startswith("OLD")}

    assert len(p1) >= 30 and len(p2) >= 30 and len(p3) >= 30
    assert len(p1 - p2) >= 20
    assert len(p2 - p3) >= 20
    assert r2["pending_not_attempted_previous_run"] > 0
    assert r3["pending_not_attempted_previous_run"] > 0
    assert r2["one_cycle_backlog_rotation"] is True
    assert r3["one_cycle_backlog_rotation"] is True


def test_3_storj_style_persistent_candidate_survives_watchlist_exit():
    storj = {
        "symbol": "STORJUSDT",
        "persistent_until_exact_identity_resolution": True,
        "timing_quality": "EARLY_BREAKOUT_EVIDENCE",
        "first_watch_observed_at": "2026-09-06T09:41:49+00:00",
        "first_watch_reference_price": 0.03035,
        "first_alert_observed_at": "2026-09-06T09:41:49+00:00",
        "first_alert_reference_price": 0.03035,
        "first_alert_score": 35,
        "first_alert_coherent_confirmations": 2,
    }
    selected, report = mod._build_identity_queue(
        {"watchlist": []},
        {"candidates": [storj]},
        {},
    )
    assert [mod._base_symbol(r.get("symbol")) for r in selected] == ["STORJ"]
    assert selected[0]["first_alert_observed_at"] == "2026-09-06T09:41:49+00:00"
    assert selected[0]["first_alert_reference_price"] == 0.03035
    assert report["persistent_carried_when_absent_from_current_watch"] == 1
    assert report["ordering_only"] is True


def test_4_score_99_without_exact_pair_remains_fail_closed(monkeypatch, tmp_path: Path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-11T18:00:00+00:00",
        "watchlist": [{"symbol": "HARDUSDT", "spot_revival_score": 99, "coherent_confirmations": 10}],
    }))
    (tmp_path / "cex-early-revival-pending.json").write_text(json.dumps({"candidates": []}))

    def fake_age(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "coingecko_id": "hard-token",
            "market_age_verified": True,
            "market_age_evidence_at": "2024-01-01T00:00:00+00:00",
        })
        path.write_text(json.dumps(p))
        return {"accepted": 1, "rejected": 0, "rejections": []}

    def fake_exact(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "identity_status": "IDENTITY_RESOLVED_PAIR_PENDING",
            "identity_verified": False,
            "chain": "ethereum",
            "token_address": "0xabc",
            "pair_address": None,
        })
        path.write_text(json.dumps(p))
        return {"dex_verified": 0}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)
    row = out["candidates"][0]
    assert row["status"] == "CEX_SPOT_IDENTITY_RESOLVED_PAIR_PENDING_RESEARCH"
    assert row["identity_verified"] is False
    assert row["pair_address"] is None
    assert row["research_only"] is True
    assert row["actionable"] is False
    assert row["automatic_buy"] is False
    assert out["truth_contract"]["exact_dex_pair_required_before_registry_learning"] is True
    assert out["truth_contract"]["persistent_pending_never_satisfies_identity"] is True


def test_5_truth_contract_keeps_production_gates_unchanged(monkeypatch, tmp_path: Path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({"watchlist": []}))
    (tmp_path / "cex-early-revival-pending.json").write_text(json.dumps({"candidates": []}))
    out = mod.run(tmp_path)
    truth = out["truth_contract"]
    assert out["production_portfolio_impact"] == "NONE"
    assert out["automatic_buy"] is False
    assert out["symbol_only_actionable"] is False
    assert truth["hard_liquidity_and_survival_gates_unchanged"] is True
    assert truth["no_hindsight"] is True
    assert truth["priority_uses_only_preexisting_evidence"] is True
