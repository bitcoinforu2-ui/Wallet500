from __future__ import annotations

from wallet500.cex_fast_current_bypass import _milestone_score, _priority_candidates


def _row(**overrides):
    row = {
        "symbol": "TESTUSDT",
        "spot_revival_score": 28,
        "coherent_confirmations": 2,
        "change_24h_max_pct": 8.0,
        "leveraged_product": False,
        "milestones": {
            "first_alert": {
                "score": 45,
                "reference_price": 0.01,
                "reference_change_24h_pct": 4.0,
            }
        },
        "markets": [
            {"exchange": "gate", "price": 0.011, "volume_24h": 300_000},
            {"exchange": "kucoin", "price": 0.0111, "volume_24h": 250_000},
        ],
    }
    row.update(overrides)
    return row


def test_immutable_first_alert_can_prioritize_current_watch_even_if_current_score_falls():
    row = _row(spot_revival_score=28)
    assert _milestone_score(row) == 45
    chosen = _priority_candidates({"watchlist": [row]})
    assert len(chosen) == 1
    assert chosen[0]["symbol"] == "TESTUSDT"


def test_late_current_move_is_not_spent_on_identity_resolution():
    row = _row(change_24h_max_pct=72.0)
    assert _priority_candidates({"watchlist": [row]}) == []


def test_leveraged_product_never_enters_bypass():
    row = _row(leveraged_product=True)
    assert _priority_candidates({"watchlist": [row]}) == []


def test_missing_live_cex_price_never_enters_bypass():
    row = _row(markets=[])
    assert _priority_candidates({"watchlist": [row]}) == []
