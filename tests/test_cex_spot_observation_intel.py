import gzip
import json
from pathlib import Path

from wallet500.cex_spot_observation_intel import (
    build_observation_intel,
    classify_postmortem,
    leveraged_underlying,
)


def _write_state(out: Path, markets: dict, signal_milestones: dict | None = None):
    with gzip.open(out / "cex-spot-state.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"version": 3, "markets": markets, "signal_milestones": signal_milestones or {}}, fh)


def test_leveraged_underlying_is_research_mapping_only():
    assert leveraged_underlying("FIL5LUSDT") == "FIL"
    assert leveraged_underlying("FIL3LUSDT") == "FIL"
    assert leveraged_underlying("LAB3SUSDT") == "LAB"
    assert leveraged_underlying("CPOOLUSDT") is None


def test_miss_taxonomy_fail_closed_order():
    assert classify_postmortem(observed=False, promoted=False) == "DISCOVERY_MISS"
    assert classify_postmortem(observed=True, promoted=False) == "PROMOTION_MISS"
    assert classify_postmortem(observed=True, promoted=True, identity_verified=False) == "IDENTITY_BLOCKED"
    assert classify_postmortem(observed=True, promoted=True, identity_verified=True, liquidity_gate=False) == "LIQUIDITY_BLOCKED"
    assert classify_postmortem(observed=True, promoted=True, intentional_exclusion=True) == "INTENTIONAL_EXCLUSION"


def test_immutable_first_observation_and_shadow_do_not_touch_production(tmp_path):
    out = tmp_path
    _write_state(
        out,
        {
            "spot:gate:BRUSDT:BR_USDT": [
                {"observed_at": "2026-09-14T10:00:00+00:00", "price": 0.20, "change_24h_pct": 10, "volume_24h": 100000, "quote_symbol": "USDT"},
                {"observed_at": "2026-09-14T11:00:00+00:00", "price": 0.40, "change_24h_pct": 71, "volume_24h": 1600000, "quote_symbol": "USDT"},
            ],
            "spot:gate:FIL5LUSDT:FIL5L_USDT": [
                {"observed_at": "2026-09-14T11:00:00+00:00", "price": 0.7, "change_24h_pct": 167, "volume_24h": 2960000, "quote_symbol": "USDT"}
            ],
        },
    )
    (out / "cex-spot-revival-radar.json").write_text(json.dumps({"watchlist": [], "alerts": []}), encoding="utf-8")
    (out / "cex-spot-identity-radar.json").write_text(json.dumps({}), encoding="utf-8")

    first = build_observation_intel(out, "2026-09-14T12:00:00+00:00")
    ledger1 = json.loads((out / "cex-spot-observation-ledger.json").read_text(encoding="utf-8"))
    br_key = "spot:gate:BRUSDT:BR_USDT"
    assert ledger1["markets"][br_key]["first_observed_price"] == 0.20
    assert ledger1["markets"][br_key]["first_seen_exact"] is False
    assert ledger1["markets"][br_key]["source"] == "MIGRATED_RETAINED_HISTORY_LOWER_BOUND"
    assert first["production_effect"] is False
    assert first["production_thresholds_modified"] is False
    assert first["liquidity_minimum_modified"] is False
    assert first["identity_rules_modified"] is False
    assert any(x["underlying"] == "FIL" and x["affects_score"] is False for x in first["leveraged_underlying_shadow"])
    assert any(x["symbol"] == "BRUSDT" and x["class"] == "PROMOTION_MISS" for x in first["mover_diagnostics"])
    assert any(x["symbol"] == "FIL5LUSDT" and x["class"] == "INTENTIONAL_EXCLUSION" for x in first["mover_diagnostics"])

    # A later run cannot rewrite the first observation already persisted.
    _write_state(
        out,
        {
            br_key: [
                {"observed_at": "2026-09-14T13:00:00+00:00", "price": 0.50, "change_24h_pct": 80, "volume_24h": 2000000, "quote_symbol": "USDT"}
            ]
        },
    )
    build_observation_intel(out, "2026-09-14T13:05:00+00:00")
    ledger2 = json.loads((out / "cex-spot-observation-ledger.json").read_text(encoding="utf-8"))
    assert ledger2["markets"][br_key]["first_observed_price"] == 0.20
    assert ledger2["markets"][br_key]["first_observed_at"] == "2026-09-14T10:00:00+00:00"


def test_immutable_first_watch_prevents_false_promotion_miss_after_current_watch_rotates(tmp_path):
    out = tmp_path
    _write_state(
        out,
        {
            "spot:gate:TRIOUSDT:TRIO_USDT": [
                {
                    "observed_at": "2026-09-21T19:35:00+00:00",
                    "price": 0.02,
                    "change_24h_pct": 74.36,
                    "volume_24h": 54_363.54,
                    "quote_symbol": "USDT",
                }
            ]
        },
        signal_milestones={
            "TRIOUSDT": {
                "first_watch": {
                    "observed_at": "2026-09-21T19:20:00+00:00",
                    "reference_price": 0.015,
                    "score": 28,
                }
            }
        },
    )
    (out / "cex-spot-revival-radar.json").write_text(
        json.dumps({"watchlist": [], "alerts": []}),
        encoding="utf-8",
    )
    (out / "cex-spot-identity-radar.json").write_text(json.dumps({}), encoding="utf-8")

    payload = build_observation_intel(out, "2026-09-21T19:40:00+00:00")
    trio = next(x for x in payload["mover_diagnostics"] if x["symbol"] == "TRIOUSDT")

    assert trio["class"] == "PROMOTED_RESEARCH"
    assert trio["promoted_to_research_watch"] is True
    assert trio["current_watch_membership"] is False
    assert trio["immutable_promotion_milestone"] is True
