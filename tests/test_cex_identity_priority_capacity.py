from wallet500 import cex_spot_identity as mod


def test_persistent_backlog_cannot_starve_fresh_watch_capacity():
    pending = {
        "candidates": [
            {
                "symbol": f"OLD{i}USDT",
                "persistent_until_exact_identity_resolution": True,
                "timing_quality": "EARLY_BREAKOUT_EVIDENCE",
                "first_alert_score": 100 - i,
                "first_alert_coherent_confirmations": 4,
            }
            for i in range(100)
        ]
    }
    spot = {
        "watchlist": [
            {
                "symbol": f"NEW{i}USDT",
                "spot_revival_score": 50 - i,
                "coherent_confirmations": 2,
            }
            for i in range(40)
        ]
    }

    selected, report = mod._build_identity_queue(spot, pending)
    symbols = {mod._base_symbol(row.get("symbol")) for row in selected}

    assert len(selected) == mod.MAX_WATCH_CANDIDATES
    assert report["selected_persistent_count"] == mod.MAX_PERSISTENT_PRIORITY_SLOTS
    assert report["selected_current_count"] == mod.MAX_WATCH_CANDIDATES - mod.MAX_PERSISTENT_PRIORITY_SLOTS
    assert report["fresh_watch_capacity_protected"] is True
    assert len({f"NEW{i}" for i in range(40)} & symbols) == 30
    assert report["ordering_only"] is True
    assert report["production_effect"] is False
    assert report["no_hindsight"] is True


def test_previous_attempts_rotate_behind_untried_persistent_candidates():
    pending = {
        "candidates": [
            {
                "symbol": f"OLD{i}USDT",
                "persistent_until_exact_identity_resolution": True,
                "timing_quality": "EARLY_BREAKOUT_EVIDENCE",
                "first_alert_score": 100 - i,
                "first_alert_coherent_confirmations": 4,
            }
            for i in range(60)
        ]
    }
    previous_identity = {
        "candidates": [{"symbol": f"OLD{i}USDT"} for i in range(30)],
        "rejections": [],
    }

    selected, report = mod._build_identity_queue({"watchlist": []}, pending, previous_identity)
    first_reserve = [mod._base_symbol(row.get("symbol")) for row in selected[:mod.MAX_PERSISTENT_PRIORITY_SLOTS]]

    assert all(symbol in {f"OLD{i}" for i in range(30, 60)} for symbol in first_reserve)
    assert report["previous_attempted_symbol_count"] == 30
    assert report["pending_not_attempted_previous_run"] == 30
    assert report["one_cycle_backlog_rotation"] is True
    assert report["production_effect"] is False
    assert report["no_hindsight"] is True
