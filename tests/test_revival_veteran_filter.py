from __future__ import annotations

from datetime import datetime, timezone

from wallet500 import revival_veteran_filter as rvf


def _coin(symbol: str, ath_date: str | None) -> dict:
    return {
        "symbol": symbol,
        "ath_date": ath_date,
        "watch_status": "DEEP_WATCH",
        "pre_alpha_eligible": False,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "revival_score_components": {"same_pair_as_previous": False},
    }


def test_veteran_filter_is_fail_closed_and_keeps_only_proven_180d_assets() -> None:
    payload = {
        "mode": "RESEARCH_ONLY_REVIVAL_SOLANA_500_V4",
        "network": "solana",
        "universe_definition": "base",
        "production_portfolio_impact": "NONE",
        "coins": [
            _coin("OLD", "2026-01-01T00:00:00Z"),
            _coin("RECENT_ATH", "2026-08-01T00:00:00Z"),
            _coin("UNKNOWN", None),
        ],
    }
    out = rvf.apply_veteran_filter(
        payload,
        now=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )

    assert [x["symbol"] for x in out["coins"]] == ["OLD"]
    assert out["coins"][0]["veteran_verified"] is True
    assert out["counts"]["universe"] == 1
    gov = out["veteran_age_governance"]
    assert gov["minimum_market_age_days"] == 180
    assert gov["raw_before_age_filter"] == 3
    assert gov["accepted_verified_veterans"] == 1
    assert gov["excluded_age_unverified"] == 2
    assert gov["missing_age_never_imputed_as_old"] is True
    assert out["production_portfolio_impact"] == "NONE"


def test_recent_ath_is_not_mislabelled_as_proof_of_youth() -> None:
    payload = {
        "network": "solana",
        "coins": [_coin("MAYBE_OLD", "2026-08-01T00:00:00Z")],
    }
    out = rvf.apply_veteran_filter(
        payload,
        now=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    assert out["coins"] == []
    gov = out["veteran_age_governance"]
    assert gov["excluded_recent_ath_insufficient_to_prove_age"] == 1
    assert "cannot prove youth" in gov["interpretation"]
