"""Regression: identify early high-quality CEX momentum without auto-BUY."""
from datetime import datetime, timedelta, timezone

from scripts import user_watch_final_buy as gate


NOW = datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc)


def sample():
    row = {
        "candidate_type": "GATE_SPOT_DISCOVERY",
        "symbol": "EARLY",
        "network": "ethereum",
        "contract": "0x1111111111111111111111111111111111111111",
        "pair": "0x2222222222222222222222222222222222222222",
        "discovery_momentum_change_pct": 12.0,
        "change_24h_pct": 12.0,
        "gain_from_first_seen_pct": 12.0,
        "positive_gainer_rank": 6,
    }
    live = {
        **row,
        "identity_key": gate.identity_key(row),
        "observed_at": NOW.isoformat(),
        "cex_quote_volume_24h_usd": 350000.0,
        "cex_relative_volume_multiple": 5.0,
        "positive_gainer_rank": 6,
        "dynamic_spot_candidate": True,
    }
    return row, live


def test_early_momentum_enters_final_buy_evaluation_before_25_percent(monkeypatch):
    monkeypatch.setattr(gate, "now_utc", lambda: NOW)
    row, live = sample()
    assert gate.early_cex_momentum_watch(row, live, now=NOW) is True
    targets = gate.eligible_targets(
        {"tokens": []},
        {"candidates": [row]},
        {"tokens": {"SPOT:EARLY": live}},
    )
    assert len(targets) == 1
    assert targets[0]["early_cex_momentum_lane"] is True
    assert targets[0]["quarter_wave_revalidation_lane"] is False
    assert targets[0]["telegram_policy"] == "FINAL_BUY_ONLY"
    assert targets[0]["exact_identity_required"] is True


def test_only_current_exact_identity_can_enter_early_lane():
    row, live = sample()
    assert gate.early_cex_momentum_watch(row, {**live, "pair": "0x3333333333333333333333333333333333333333"}, now=NOW) is False
    assert gate.early_cex_momentum_watch(row, {**live, "observed_at": (NOW - timedelta(hours=2)).isoformat()}, now=NOW) is False
    assert gate.early_cex_momentum_watch({**row, "pair": ""}, live, now=NOW) is False


def test_low_volume_weak_relative_volume_or_low_rank_cannot_enter():
    row, live = sample()
    assert gate.early_cex_momentum_watch(row, {**live, "cex_quote_volume_24h_usd": 99999}, now=NOW) is False
    assert gate.early_cex_momentum_watch(row, {**live, "cex_relative_volume_multiple": 3.9}, now=NOW) is False
    assert gate.early_cex_momentum_watch(row, {**live, "positive_gainer_rank": 22}, now=NOW) is False


def test_early_lane_never_becomes_late_chase_or_cex_only_promotion():
    row, live = sample()
    late = {**row, "gain_from_first_seen_pct": 45.0}
    assert gate.early_cex_momentum_watch(late, live, now=NOW) is False
    cex_only = {
        **row,
        "candidate_type": "CEX_MARKET_DISCOVERY",
        "execution_identity_scope": "EXACT_CEX_MARKET",
        "exchange": "gate",
        "currency_pair": "EARLY_USDT",
    }
    assert gate.early_cex_momentum_watch(cex_only, live, now=NOW) is False


def test_early_discovery_without_market_observations_does_not_notify():
    row, _ = sample()
    assert gate.eligible_targets({"tokens": []}, {"candidates": [row]}, {"tokens": {}}) == []
