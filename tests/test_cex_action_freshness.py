from __future__ import annotations

import subprocess
import sys
import textwrap


def test_cex_action_freshness_and_reactivation_contract():
    code = r'''
from datetime import datetime, timedelta, timezone
from scripts import run_cex_action_guarded as guard


def row(observed_at, changes):
    return {
        "symbol": "TESTUSDT",
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "execution_pair_price_coherent": True,
        "market_age_verified": True,
        "market_age_min_days": 226,
        "chain": "bsc",
        "token_address": "0xc51a9250795c0186a6fb4a7d20a90330651e4444",
        "pair_address": "0xa651C8Deb3ff9F8D56a26E72042b7A8A1f433480",
        "execution_pool_liquidity_usd": 988_000,
        "spot_revival_score": 58,
        "coherent_confirmations": 2,
        "exchanges": ["gate", "mexc"],
        "leaderboard_best_rank": 2,
        "markets": [
            {
                "exchange": "gate",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST_USDT",
                "quote_symbol": "USDT",
                "price": 0.01282,
                "change_24h_pct": changes[0],
                "volume_24h": 1_770_000,
                "volume_comparable_usd_like": True,
            },
            {
                "exchange": "mexc",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TESTUSDT",
                "quote_symbol": "USDT",
                "price": 0.012827,
                "change_24h_pct": changes[1],
                "volume_24h": 800_000,
                "volume_comparable_usd_like": True,
            },
        ],
        "milestones": {
            "first_alert": {
                "observed_at": observed_at,
                "reference_price": 0.012974,
                "reference_change_24h_pct": 13.79,
                "score": 58,
            }
        },
    }

# Exact regression: a 12-day-old discovery with flat/negative current markets
# must NOT be presented as a current BUY_ZONE.
stale = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
ok, metrics = guard.action_eligibility(row(stale, (-0.1, -0.2)))
assert ok is False, metrics
assert "STALE_SIGNAL_NO_FRESH_REACTIVATION" in metrics["blockers"], metrics
assert metrics["action_state"] == "WAIT_FRESH_REACTIVATION", metrics
assert metrics["signal_age_hours"] > guard.MAX_FRESH_SIGNAL_AGE_HOURS, metrics
assert metrics["fresh_reactivation_confirmations"] == 0, metrics

# An old discovery may re-enter only when CURRENT independent CEX markets
# confirm new momentum now.
ok, metrics = guard.action_eligibility(row(stale, (7.0, 6.0)))
assert ok is True, metrics
assert metrics["blockers"] == [], metrics
assert metrics["action_state"] == "REENTRY_ZONE", metrics
assert metrics["action_basis"] == "FRESH_MULTI_CEX_REACTIVATION", metrics
assert metrics["fresh_reactivation_confirmations"] == 2, metrics
assert metrics["fresh_reactivation_exchanges"] == ["gate", "mexc"], metrics

# A genuinely recent signal retains the normal BUY_ZONE path.
fresh = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
ok, metrics = guard.action_eligibility(row(fresh, (4.0, 3.5)))
assert ok is True, metrics
assert metrics["action_state"] == "BUY_ZONE", metrics
assert metrics["action_basis"] == "FRESH_SIGNAL", metrics
assert metrics["signal_freshness"] == "FRESH", metrics

# AKE-like regression: spot lane alone is below action threshold (38), while an
# immutable derivatives FIRST_ALERT scored 79 at the same early spot price.
# Cross-lane fusion should make the already exact-identity candidate actionable
# without weakening identity/liquidity/no-chase/freshness gates.
ake_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
ake = row(ake_time, (8.0, 7.6))
ake["spot_revival_score"] = 38
ake["milestones"]["first_alert"].update({
    "observed_at": ake_time,
    "reference_price": 0.0143037,
    "reference_change_24h_pct": -3.49,
    "score": 38,
})
for market, price in zip(ake["markets"], (0.01410, 0.01412)):
    market["price"] = price
ake["cross_lane_derivatives_precursor"] = {
    "status": "QUALIFIED_CEX_DERIVATIVES_SPOT_PRECURSOR",
    "research_only": True,
    "actionable": False,
    "affects_spot_score": False,
    "identity_priority": True,
    "eligible_for_action_score_fusion_after_exact_identity": True,
    "no_hindsight": True,
    "action_signal_score": 79,
    "action_signal_at": ake_time,
    "action_signal_price": 0.0136977,
    "action_signal_change_24h_pct": 7.67,
    "derivatives_score": 79,
    "derivatives_coherent_confirmations": 4,
    "derivatives_dispersion_status": "COHERENT_RANGE",
    "spot_anchor_kind": "first_seen",
    "spot_anchor_price": 0.0136977,
}

without_fusion = dict(ake)
without_fusion.pop("cross_lane_derivatives_precursor")
ok, metrics = guard.action_eligibility(without_fusion)
assert ok is False, metrics
assert "ACTION_SCORE_LT_50" in metrics["blockers"], metrics

ok, metrics = guard.action_eligibility(ake)
assert ok is True, metrics
assert metrics["blockers"] == [], metrics
assert metrics["signal_score"] == 79, metrics
assert metrics["cross_lane_action_fusion_used"] is True, metrics
assert metrics["action_state"] == "BUY_ZONE", metrics
assert metrics["action_basis"] == "FRESH_CEX_DERIVATIVES_SPOT_FUSION", metrics
assert metrics["since_discovery_pct"] < guard.MAX_GAIN_SINCE_DISCOVERY_PCT, metrics
'''
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
