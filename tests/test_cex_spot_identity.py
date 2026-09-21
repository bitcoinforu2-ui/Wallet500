import json
from pathlib import Path

from wallet500 import cex_spot_identity as mod


def _seed(tmp_path: Path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-05T18:00:00+00:00",
        "watchlist": [{
            "symbol": "GXEUSDT",
            "spot_revival_score": 55,
            "exchanges": ["gate"],
            "markets": [{"exchange": "gate", "symbol": "GXEUSDT", "price": 0.0001}],
        }],
    }), encoding="utf-8")


def test_dynamic_spot_identity_stays_research_only(monkeypatch, tmp_path):
    _seed(tmp_path)

    def fake_age(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "coingecko_id": "project-xeno",
            "market_age_verified": True,
            "market_age_min_days": 1000,
            "market_age_evidence_at": "2023-01-01T00:00:00+00:00",
            "market_age_evidence_source": "TEST",
        })
        path.write_text(json.dumps(p))
        return {"accepted": 1, "rejected": 0, "rejections": []}

    def fake_exact(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "ethereum",
            "token_address": "0x510975eda48a97e0ca228dd04d1217292487bea6",
            "pair_address": "0xpair",
            "dex_price_usd": 0.000102,
            "dex_liquidity_usd": 1200,
        })
        p["platform_catalog"] = {"status": "OK"}
        p["identity_contract"] = {"exact_dex_pair_required": True}
        path.write_text(json.dumps(p))
        return {"dex_verified": 1}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)
    row = out["candidates"][0]
    assert out["status"] == "OK"
    assert out["counts"]["dex_verified"] == 1
    assert row["token_address"].lower() == "0x510975eda48a97e0ca228dd04d1217292487bea6"
    assert row["research_only"] is True
    assert row["actionable"] is False
    assert row["automatic_buy"] is False
    assert row["identity_attempted_at"]
    assert row["execution_pair_price_coherent"] is True
    assert out["truth_contract"]["cex_only_never_real_alert"] is True
    assert out["truth_contract"]["persistent_pending_priority_is_ordering_only"] is True
    assert out["truth_contract"]["dynamic_exact_pair_requires_current_cex_dex_price_coherence"] is True
    assert out["truth_contract"]["no_hindsight"] is True


def test_incoherent_exact_pair_fails_closed_and_quarantines_auto_registry(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-14T10:19:52+00:00",
        "watchlist": [{
            "symbol": "CPOOLUSDT",
            "spot_revival_score": 36,
            "markets": [
                {"exchange": "kucoin", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "USDT", "price": 0.03029, "volume_comparable_usd_like": True},
                {"exchange": "mexc", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "USDT", "price": 0.03034, "volume_comparable_usd_like": True},
                {"exchange": "gate", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "USDT", "price": 0.03019, "volume_comparable_usd_like": True},
                {"exchange": "upbit", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "KRW", "price": 41.1, "volume_comparable_usd_like": False, "regional_market": True},
            ],
        }],
    }), encoding="utf-8")
    (tmp_path / "cex-identity-registry.json").write_text(json.dumps({
        "version": 3,
        "symbols": {
            "CPOOL": {
                "coingecko_id": "clearpool",
                "chain": "solana",
                "token_address": "AeXrLftu8chuY4ctc6oDeG4dUx6Yr4aqeakUMFNvACdg",
                "market_age_evidence_at": "2024-01-01T00:00:00+00:00",
                "evidence_source": "AUTO_STRICT_CEX_SPOT_CGID_AGE_PLUS_EXACT_DEX_PAIR",
                "auto_verified_pair_address": "HxErbEaAT8wYAkyxXqmQcdUshgi7VuwmSEXkixkFvnF1",
                "auto_verified_at": "2026-09-10T11:44:24+00:00"
            }
        }
    }), encoding="utf-8")

    def fake_age(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "coingecko_id": "clearpool",
            "market_age_verified": True,
            "market_age_evidence_at": "2024-01-01T00:00:00+00:00",
        })
        path.write_text(json.dumps(p))
        return {"accepted": 1, "rejected": 0, "rejections": []}

    def fake_exact(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "solana",
            "token_address": "AeXrLftu8chuY4ctc6oDeG4dUx6Yr4aqeakUMFNvACdg",
            "pair_address": "HxErbEaAT8wYAkyxXqmQcdUshgi7VuwmSEXkixkFvnF1",
            "dex_price_usd": 0.1629,
            "dex_liquidity_usd": 202579.48,
            "dex_volume_h24": 0,
        })
        p["platform_catalog"] = {"status": "OK"}
        p["identity_contract"] = {"exact_dex_pair_required": True}
        path.write_text(json.dumps(p))
        return {"dex_verified": 1}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)
    row = out["candidates"][0]
    assert row["identity_status"] == "IDENTITY_RESOLVED_PAIR_PENDING"
    assert row["identity_verified"] is False
    assert row["identity_blocker"] == "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT"
    assert row["execution_pair_price_coherent"] is False
    assert row["cex_reference_price_sample_count"] == 3
    assert row["cex_reference_price_usd"] == 0.03029
    assert row["cex_dex_price_ratio"] > 5
    assert out["counts"]["dex_verified"] == 0
    assert out["counts"]["price_incoherent"] == 1
    assert out["auto_registry"]["quarantine"]["quarantined"] == ["CPOOL"]

    registry = json.loads((tmp_path / "cex-identity-registry.json").read_text())
    assert "CPOOL" not in registry["symbols"]
    assert registry["quarantined_symbols"]["CPOOL"]["quarantine_reason"] == "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT"
    assert registry["quarantined_symbols"]["CPOOL"]["immutable_detection_history_untouched"] is True


def test_provider_failure_is_fail_closed(monkeypatch, tmp_path):
    _seed(tmp_path)

    def boom(path):
        raise RuntimeError("provider down")

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", boom)
    out = mod.run(tmp_path)
    assert out["status"] == "DEGRADED_FAIL_CLOSED"
    assert out["candidates"] == []
    assert out["counts"]["dex_verified"] == 0
    assert not (tmp_path / ".cex-spot-identity-work.json").exists()


def test_empty_spot_watch_is_healthy_empty(tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        json.dumps({"generated_at": "2026-09-05T18:00:00+00:00", "watchlist": []}),
        encoding="utf-8",
    )
    out = mod.run(tmp_path)
    assert out["status"] == "HEALTHY_EMPTY"
    assert out["candidates"] == []


def test_persistent_unresolved_candidate_is_prioritized_even_after_leaving_current_watch(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-11T10:00:00+00:00",
        "watchlist": [{"symbol": "LOWUSDT", "spot_revival_score": 20, "coherent_confirmations": 1}],
    }), encoding="utf-8")
    (tmp_path / "cex-early-revival-pending.json").write_text(json.dumps({
        "candidates": [{
            "symbol": "STORJUSDT",
            "persistent_until_exact_identity_resolution": True,
            "timing_quality": "EARLY_BREAKOUT_EVIDENCE",
            "first_alert_score": 35,
            "first_alert_coherent_confirmations": 2,
            "first_alert_observed_at": "2026-09-06T09:41:49+00:00",
            "first_watch_price_acceleration_max_pct": 3.0,
            "first_watch_volume_acceleration_max_pct": 10.0,
        }],
    }), encoding="utf-8")

    seen = []

    def fake_age(path):
        p = json.loads(path.read_text())
        seen.extend(x["symbol"] for x in p["alerts"])
        for row in p["alerts"]:
            row.update({
                "coingecko_id": row["symbol"].lower(),
                "market_age_verified": True,
                "market_age_evidence_at": "2024-01-01T00:00:00+00:00",
            })
        path.write_text(json.dumps(p))
        return {"accepted": len(p["alerts"]), "rejected": 0, "rejections": []}

    def fake_exact(path):
        p = json.loads(path.read_text())
        for idx, row in enumerate(p["alerts"]):
            row.update({
                "identity_status": "DEX_VERIFIED",
                "identity_verified": True,
                "chain": "ethereum",
                "token_address": f"0xtoken{idx}",
                "pair_address": f"0xpair{idx}",
            })
        path.write_text(json.dumps(p))
        return {"dex_verified": len(p["alerts"])}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)

    assert seen[0] == "STORJUSDT"
    assert out["identity_queue"]["persistent_carried_when_absent_from_current_watch"] == 1
    assert out["identity_queue"]["selected_persistent_count"] == 1
    assert out["identity_queue"]["ordering_only"] is True
    assert out["production_portfolio_impact"] == "NONE"
    assert out["automatic_buy"] is False


def test_priority_never_marks_symbol_only_candidate_actionable(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({"watchlist": []}), encoding="utf-8")
    (tmp_path / "cex-early-revival-pending.json").write_text(json.dumps({
        "candidates": [{
            "symbol": "PENDINGUSDT",
            "persistent_until_exact_identity_resolution": True,
            "first_alert_score": 99,
            "first_alert_coherent_confirmations": 9,
        }],
    }), encoding="utf-8")

    def fake_age(path):
        return {"accepted": 0, "rejected": 1, "rejections": [{"symbol": "PENDINGUSDT", "reason": "AMBIGUOUS"}]}

    def fake_exact(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({"identity_status": "IDENTITY_PENDING", "identity_verified": False})
        path.write_text(json.dumps(p))
        return {"dex_verified": 0}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)
    row = out["candidates"][0]
    assert row["identity_verified"] is False
    assert row["actionable"] is False
    assert row["automatic_buy"] is False
    assert out["truth_contract"]["persistent_pending_never_satisfies_identity"] is True

def test_inconclusive_coingecko_extrema_uses_strict_exact_pair_age_fallback(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-19T05:00:00+00:00",
        "watchlist": [{
            "symbol": "AKEUSDT",
            "spot_revival_score": 38,
            "coherent_confirmations": 3,
            "exchanges": ["gate", "mexc", "okx"],
            "markets": [
                {"exchange": "gate", "market_type": "spot", "symbol": "AKEUSDT", "quote_symbol": "USDT", "price": 0.0144, "volume_comparable_usd_like": True},
                {"exchange": "mexc", "market_type": "spot", "symbol": "AKEUSDT", "quote_symbol": "USDT", "price": 0.0143, "volume_comparable_usd_like": True},
            ],
        }],
    }), encoding="utf-8")

    def fake_age(path):
        p = json.loads(path.read_text())
        p["alerts"] = []
        path.write_text(json.dumps(p))
        return {
            "accepted": 0,
            "rejected": 1,
            "rejections": [{
                "symbol": "AKEUSDT",
                "base_symbol": "AKE",
                "reason": "AGE_MINIMUM_NOT_PROVEN_BY_COINGECKO_EXTREMA",
                "coingecko_id": "akedo",
            }],
        }

    def fake_exact(path):
        return {"dex_verified": 0}

    seen = {}

    def fake_fallback(row):
        seen.update(row)
        return {
            **row,
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "bsc",
            "token_address": "0x2c3a8ee94ddd97244a93bc48298f97d2c412f7db",
            "pair_address": "0xpair",
            "dex_price_usd": 0.01435,
            "dex_liquidity_usd": 3_000_000,
            "market_age_verified": True,
            "market_age_min_days": 341,
            "market_age_evidence_at": "2025-09-28T09:00:00+00:00",
            "market_age_evidence_source": "DEXSCREENER_EXACT_SYMBOL_PRICE_PAIR_AGE_FALLBACK",
        }

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    monkeypatch.setattr(mod, "resolve_dex_fallback", fake_fallback)

    out = mod.run(tmp_path)
    row = out["candidates"][0]

    assert seen["coingecko_id"] == "akedo"
    assert row["identity_status"] == "DEX_VERIFIED"
    assert row["identity_verified"] is True
    assert row["market_age_verified"] is True
    assert row["age_preflight_rejection_reason"] == "AGE_MINIMUM_NOT_PROVEN_BY_COINGECKO_EXTREMA"
    assert row["research_only"] is True
    assert row["actionable"] is False
    assert out["counts"]["dex_fallback_verified"] == 1
    assert out["counts"]["age_inconclusive_fallback_verified"] == 1
    assert out["truth_contract"]["dex_fallback_for_missing_or_inconclusive_age_evidence"] is True
    assert out["truth_contract"]["dex_fallback_never_waives_ambiguous_coin_identity"] is True


def test_w3gg_like_absorption_shadow_enters_identity_queue_before_watch_threshold():
    spot_payload = {
        "watchlist": [],
        "shadow_watchlist": [{
            "symbol": "W3GGUSDT",
            "spot_revival_score": 20,
            "coherent_confirmations": 1,
            "change_24h_max_pct": 0.48,
            "volume_acceleration_max_pct": 178.1256,
            "volume_window_multiple_max": 1.4,
            "shadow_features": ["VOLUME_PRICE_ABSORPTION_SHADOW"],
            "slow_ignition": {"status": "NONE", "confirmations": 0},
            "markets": [{"exchange": "gate", "price": 0.0004948}],
        }],
    }

    selected, report = mod._build_identity_queue(
        spot_payload, {"candidates": []}, {}
    )

    assert [x["symbol"] for x in selected] == ["W3GGUSDT"]
    assert report["regular_watch_count"] == 0
    assert report["prewave_shadow_identity_priority_count"] == 1
    assert report["prewave_shadow_selected_count"] == 1
    assert report["prewave_shadow_is_identity_priority_only"] is True
    assert report["prewave_shadow_never_satisfies_identity"] is True
    assert report["production_effect"] is False


def test_island_like_cross_venue_slow_ignition_gets_prewave_identity_priority():
    spot_payload = {
        "watchlist": [],
        "shadow_watchlist": [{
            "symbol": "ISLANDUSDT",
            "spot_revival_score": 18,
            "coherent_confirmations": 2,
            "change_24h_max_pct": 12.73,
            "volume_acceleration_max_pct": -2.3531,
            "volume_window_multiple_max": 1.1,
            "shadow_features": ["PERSISTENT_SPOT_PRESSURE_SHADOW"],
            "slow_ignition": {
                "status": "CROSS_VENUE_PERSISTENT",
                "confirmations": 2,
                "exchanges": ["gate", "kucoin"],
            },
            "markets": [
                {"exchange": "gate", "price": 0.000239},
                {"exchange": "kucoin", "price": 0.000239},
            ],
        }],
    }

    selected, report = mod._build_identity_queue(
        spot_payload, {"candidates": []}, {}
    )

    assert [x["symbol"] for x in selected] == ["ISLANDUSDT"]
    assert report["prewave_shadow_identity_priority_count"] == 1
    assert report["prewave_shadow_selected_count"] == 1


def test_persistent_backlog_cannot_consume_reserved_current_capacity():
    watchlist = [
        {
            "symbol": f"CUR{i}USDT",
            "spot_revival_score": 40 + (i % 5),
            "coherent_confirmations": 2,
        }
        for i in range(40)
    ]
    pending = {
        "candidates": [
            {
                "symbol": f"OLD{i}USDT",
                "persistent_until_exact_identity_resolution": True,
                "first_alert_score": 35,
                "first_alert_coherent_confirmations": 1,
            }
            for i in range(100)
        ]
    }

    selected, report = mod._build_identity_queue(
        {"watchlist": watchlist, "shadow_watchlist": []},
        pending,
        {},
    )
    selected_symbols = {x["symbol"] for x in selected}

    assert len(selected) == mod.MAX_WATCH_CANDIDATES
    assert report["selected_persistent_backlog_only_count"] <= mod.MAX_PERSISTENT_PRIORITY_SLOTS
    assert report["persistent_backlog_cap_enforced"] is True
    assert report["persistent_backlog_target_slots"] == 30
    assert report["selected_current_count"] >= 30
    assert len({f"CUR{i}USDT" for i in range(40)} & selected_symbols) >= 30


def test_qualified_cross_lane_shadow_candidate_enters_identity_queue_before_spot_watch():
    spot_payload = {
        "watchlist": [],
        "shadow_watchlist": [{
            "symbol": "AKEUSDT",
            "spot_revival_score": 5,
            "coherent_confirmations": 0,
            "markets": [
                {
                    "exchange": "gate",
                    "market_type": "spot",
                    "symbol": "AKEUSDT",
                    "quote_symbol": "USDT",
                    "price": 0.0136977,
                    "volume_comparable_usd_like": True,
                },
                {
                    "exchange": "kucoin",
                    "market_type": "spot",
                    "symbol": "AKEUSDT",
                    "quote_symbol": "USDT",
                    "price": 0.01372,
                    "volume_comparable_usd_like": True,
                },
            ],
            "cross_lane_derivatives_precursor": {
                "status": "QUALIFIED_CEX_DERIVATIVES_SPOT_PRECURSOR",
                "identity_priority": True,
                "action_signal_score": 79,
                "derivatives_coherent_confirmations": 4,
                "eligible_for_action_score_fusion_after_exact_identity": True,
                "no_hindsight": True,
            },
        }],
    }

    selected, report = mod._build_identity_queue(spot_payload, {"candidates": []}, {})

    assert [x["symbol"] for x in selected] == ["AKEUSDT"]
    assert report["regular_watch_count"] == 0
    assert report["cross_lane_identity_priority_count"] == 1
    assert report["selected_current_count"] == 1
    assert report["cross_lane_derivatives_precursor_is_identity_priority_only"] is True
    assert report["cross_lane_derivatives_precursor_never_satisfies_identity"] is True
    assert report["production_effect"] is False
    assert report["no_hindsight"] is True


def test_previous_unresolved_persistent_identity_is_carried_forward_without_pending_file():
    previous_identity = {
        "candidates": [{
            "symbol": "ONEUSDT",
            "base_symbol": "ONE",
            "coingecko_id": "harmony",
            "identity_status": "IDENTITY_PENDING",
            "identity_blocker": "NO_EXACT_ONCHAIN_PLATFORM_IDENTITY",
            "persistent_until_exact_identity_resolution": True,
            "market_age_verified": True,
            "spot_revival_score": 38,
            "coherent_confirmations": 3,
            "identity_attempted_at": "2026-09-19T03:01:14+00:00",
        }]
    }
    selected, report = mod._build_identity_queue(
        {"watchlist": [], "shadow_watchlist": []},
        {"candidates": []},
        previous_identity,
    )
    assert [x["symbol"] for x in selected] == ["ONEUSDT"]
    assert report["previous_unresolved_persistent_carried_count"] == 1
    assert report["selected_persistent_backlog_only_count"] == 1
    assert report["ordering_only"] is True


def test_one_learning_recovery_reenters_identity_queue_from_immutable_signal_and_current_cex():
    learning = {
        "top_candidates": [{
            "symbol": "ONEUSDT",
            "score": 46,
            "coherent_confirmations": 4,
            "change_24h_max_pct": 164.66,
            "milestones": {
                "first_seen": {
                    "observed_at": "2026-09-04T10:50:55+00:00",
                    "reference_price": 0.00071,
                },
                "first_watch": {
                    "observed_at": "2026-09-06T02:15:44+00:00",
                    "reference_price": 0.000736,
                    "score": 28,
                    "coherent_confirmations": 2,
                    "volume_acceleration_max_pct": 61.3879,
                },
                "first_alert": {
                    "observed_at": "2026-09-13T00:24:06+00:00",
                    "reference_price": 0.000655,
                    "score": 39,
                    "coherent_confirmations": 4,
                    "reference_exchange": "okx",
                },
            },
        }],
        "top_shadow_candidates": [],
    }
    leaderboard = {
        "leaderboard": [{
            "symbol": "ONEUSDT",
            "best_rank": 1,
            "exchanges": ["binance", "coinex", "gate", "kucoin", "okx"],
            "change_24h_max_pct": 101.24,
            "volume_24h_max": 34_533_903.7632,
        }]
    }
    discovery = {
        "candidates": [{
            "symbol": "ONE",
            "currency_pair": "ONE_USDT",
            "discovery_price": 0.0044948,
            "change_24h_pct": 122.14,
            "quote_volume_24h_usd": 4_088_611.11,
            "positive_gainer_rank": 2,
            "forced_cex_watch": True,
        }]
    }

    recovered = mod._learning_recovery_candidates(learning, leaderboard, discovery)
    assert len(recovered) == 1
    row = recovered[0]
    assert row["symbol"] == "ONEUSDT"
    assert row["persistent_until_exact_identity_resolution"] is True
    assert row["identity_recovery_source"] == "IMMUTABLE_LEARNING_PLUS_CURRENT_CEX_DISCOVERY"
    assert row["identity_recovery_never_actionable"] is True
    assert row["current_identity_reactivation_priority"] is True
    assert row["current_identity_reactivation_rank"] == 1
    assert row["leaderboard_best_rank"] == 1
    assert row["markets"][0]["price"] == 0.0044948
    assert row["markets"][0]["volume_24h"] == 4_088_611.11

    selected, report = mod._build_identity_queue(
        {"watchlist": [], "shadow_watchlist": []},
        {"candidates": recovered},
        {},
    )
    assert [x["symbol"] for x in selected] == ["ONEUSDT"]
    assert report["current_reactivation_recovery_count"] == 1
    assert report["selected_current_count"] == 1
    assert report["selected_persistent_backlog_only_count"] == 0
    assert report["current_reactivation_capacity_protected"] is True
    assert report["current_reactivation_selected_count"] == 1
    assert report["current_reactivation_priority_slot_cap"] == mod.CURRENT_REACTIVATION_PRIORITY_SLOTS
    assert report["current_reactivation_never_satisfies_identity_or_actionability"] is True
    assert report["ordering_only"] is True


def test_learning_recovery_refuses_stale_history_without_current_cex_price():
    learning = {
        "top_candidates": [{
            "symbol": "ONEUSDT",
            "milestones": {
                "first_watch": {
                    "observed_at": "2026-09-06T02:15:44+00:00",
                    "reference_price": 0.000736,
                    "score": 28,
                    "coherent_confirmations": 2,
                }
            },
        }]
    }
    leaderboard = {
        "leaderboard": [{
            "symbol": "ONEUSDT",
            "best_rank": 1,
            "exchanges": ["gate"],
        }]
    }
    assert mod._learning_recovery_candidates(learning, leaderboard, {"candidates": []}) == []


def test_current_learning_reactivation_cannot_be_starved_by_large_persistent_backlog():
    recovery = {
        "symbol": "ONEUSDT",
        "base_symbol": "ONE",
        "persistent_until_exact_identity_resolution": True,
        "timing_quality": "IMMUTABLE_LEARNING_RECOVERY",
        "identity_recovery_source": "IMMUTABLE_LEARNING_PLUS_CURRENT_CEX_DISCOVERY",
        "identity_recovery_research_only": True,
        "identity_recovery_never_actionable": True,
        "current_identity_reactivation_priority": True,
        "current_identity_reactivation_rank": 1,
        "leaderboard_best_rank": 1,
        "first_alert_score": 39,
        "first_alert_coherent_confirmations": 4,
        "markets": [{
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "ONEUSDT",
            "quote_symbol": "USDT",
            "price": 0.00449,
            "volume_24h": 4_000_000,
            "volume_comparable_usd_like": True,
            "regional_market": False,
        }],
    }
    backlog = [
        {
            "symbol": f"OLD{i}USDT",
            "persistent_until_exact_identity_resolution": True,
            "first_alert_score": 99,
            "first_alert_coherent_confirmations": 9,
        }
        for i in range(700)
    ]

    selected, report = mod._build_identity_queue(
        {"watchlist": [], "shadow_watchlist": []},
        {"candidates": [recovery, *backlog]},
        {},
    )

    symbols = [x["symbol"] for x in selected]
    assert "ONEUSDT" in symbols
    assert symbols.index("ONEUSDT") < mod.CURRENT_REACTIVATION_PRIORITY_SLOTS
    assert report["current_reactivation_recovery_count"] == 1
    assert report["selected_current_count"] >= 1
    assert report["selected_persistent_backlog_only_count"] <= mod.MAX_PERSISTENT_PRIORITY_SLOTS


def test_prewave_priority_survives_shadow_to_watch_transition_and_backlog():
    current_watch = {
        "symbol": "PHAUSDT",
        "spot_revival_score": 29,
        "coherent_confirmations": 5,
        "change_24h_max_pct": 10.2,
        "shadow_features": ["PERSISTENT_SPOT_PRESSURE_SHADOW"],
        "slow_ignition": {
            "status": "BUILDING",
            "confirmations": 1,
            "exchanges": ["okx"],
        },
        "markets": [
            {"exchange": "gate", "price": 0.03577},
            {"exchange": "okx", "price": 0.03592},
        ],
    }
    ordinary = [
        {
            "symbol": f"CUR{i}USDT",
            "spot_revival_score": 90,
            "coherent_confirmations": 9,
            "change_24h_max_pct": 15.0,
        }
        for i in range(80)
    ]
    pending = {
        "candidates": [{
            "symbol": "PHAUSDT",
            "persistent_until_exact_identity_resolution": True,
            "prewave_identity_priority": True,
            "prewave_observed_at": "2026-09-15T12:38:51+00:00",
            "prewave_change_24h_pct": 3.8871,
            "prewave_slow_ignition_status": "CROSS_VENUE_PERSISTENT",
            "prewave_shadow_features": ["PERSISTENT_SPOT_PRESSURE_SHADOW"],
            "timing_quality": "EARLY_BREAKOUT_EVIDENCE",
            "first_watch_score": 28,
            "first_watch_coherent_confirmations": 2,
        }]
    }

    selected, report = mod._build_identity_queue(
        {"watchlist": [current_watch, *ordinary], "shadow_watchlist": []},
        pending,
        {},
    )

    symbols = [x["symbol"] for x in selected]
    assert "PHAUSDT" in symbols
    assert symbols.index("PHAUSDT") < mod.PREWAVE_IDENTITY_PRIORITY_SLOTS
    selected_pha = next(x for x in selected if x["symbol"] == "PHAUSDT")
    assert selected_pha["prewave_identity_priority"] is True
    assert selected_pha["prewave_observed_at"] == "2026-09-15T12:38:51+00:00"
    assert selected_pha["prewave_slow_ignition_status"] == "CROSS_VENUE_PERSISTENT"
    assert report["prewave_pending_priority_symbol_count"] == 1
    assert report["prewave_watch_or_shadow_capacity_protected"] is True
    assert report["prewave_pending_priority_survives_watch_state_transition"] is True
    assert report["production_effect"] is False


def test_current_watch_cross_venue_prewave_gets_reserved_capacity_without_shadow_bucket():
    current_watch = {
        "symbol": "PHAUSDT",
        "spot_revival_score": 29,
        "coherent_confirmations": 5,
        "change_24h_max_pct": 9.79,
        "shadow_features": ["PERSISTENT_SPOT_PRESSURE_SHADOW"],
        "slow_ignition": {
            "status": "CROSS_VENUE_PERSISTENT",
            "confirmations": 2,
            "exchanges": ["kucoin", "okx"],
        },
        "markets": [
            {"exchange": "gate", "price": 0.03577},
            {"exchange": "okx", "price": 0.03592},
        ],
    }
    selected, report = mod._build_identity_queue(
        {"watchlist": [current_watch], "shadow_watchlist": []},
        {"candidates": []},
        {},
    )

    assert [x["symbol"] for x in selected] == ["PHAUSDT"]
    assert report["prewave_identity_priority_count"] == 1
    assert report["prewave_shadow_selected_count"] == 1
    assert report["prewave_watch_or_shadow_capacity_protected"] is True
    assert report["production_effect"] is False
