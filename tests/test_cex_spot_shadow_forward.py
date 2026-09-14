import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wallet500.cex_spot_shadow_forward import MODE, _sample_maturity, run


def _write(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _radar(event_at: datetime, entry_price: float = 1.0):
    return {
        "mode": "RESEARCH_ONLY_CEX_SPOT_REVIVAL_V4",
        "generated_at": event_at.isoformat(),
        "shadow_watchlist": [
            {
                "symbol": "TESTUSDT",
                "spot_revival_score": 20,
                "confirmations": 2,
                "coherent_confirmations": 0,
                "shadow_features": ["PERSISTENT_SPOT_PRESSURE_SHADOW"],
                "shadow_reasons": ["synthetic forward-only test"],
                "slow_ignition": {
                    "status": "CROSS_VENUE_PERSISTENT",
                    "confirmations": 2,
                    "exchanges": ["gate", "okx"],
                    "multi_horizon_confirmations": 2,
                    "multi_horizon_exchanges": ["gate", "okx"],
                },
                "regional_spot_lead": {"status": "NONE"},
                "source_coverage": {"confidence": "HIGH"},
                "milestones": {
                    "first_shadow_watch": {
                        "kind": "FIRST_SHADOW_WATCH",
                        "observed_at": event_at.isoformat(),
                        "reference_price": entry_price,
                        "reference_quote_symbol": "USDT",
                    }
                },
            }
        ],
    }


def _state(observed_at: datetime, price: float):
    return {
        "version": 3,
        "updated_at": observed_at.isoformat(),
        "markets": {
            "spot:gate:TESTUSDT:TEST_USDT": [
                {
                    "observed_at": observed_at.isoformat(),
                    "price": price,
                    "change_24h_pct": 0,
                    "volume_24h": 100000,
                    "quote_symbol": "USDT",
                }
            ],
            "spot:okx:TESTUSDT:TEST-USDT": [
                {
                    "observed_at": observed_at.isoformat(),
                    "price": price,
                    "change_24h_pct": 0,
                    "volume_24h": 100000,
                    "quote_symbol": "USDT",
                }
            ],
            "spot:upbit:TESTUSDT:KRW-TEST": [
                {
                    "observed_at": observed_at.isoformat(),
                    "price": 999999,
                    "change_24h_pct": 0,
                    "volume_24h": 100000000,
                    "quote_symbol": "KRW",
                }
            ],
        },
        "signal_milestones": {},
    }


def test_pre_activation_shadow_candidate_is_not_backfilled(tmp_path: Path):
    activation = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    old_event = activation - timedelta(hours=1)
    _write(tmp_path / "cex-spot-revival-radar.json", _radar(old_event))
    _write(tmp_path / "cex-spot-state.json", _state(activation, 1.1))
    _write(
        tmp_path / "cex-spot-shadow-forward-ledger.json",
        {
            "version": 1,
            "mode": MODE,
            "activation_at": activation.isoformat(),
            "updated_at": activation.isoformat(),
            "entries": {},
        },
    )

    report = run(tmp_path, now=activation)
    ledger = json.loads((tmp_path / "cex-spot-shadow-forward-ledger.json").read_text())

    assert report["entry_count"] == 0
    assert report["pre_activation_shadow_rows_skipped_this_run"] == 1
    assert ledger["entries"] == {}
    assert report["truth_contract"]["pre_activation_shadow_candidates_not_backfilled"] is True


def test_forward_entry_is_immutable_and_24h_label_uses_future_observation(tmp_path: Path):
    t0 = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    _write(tmp_path / "cex-spot-revival-radar.json", _radar(t0, entry_price=1.0))
    _write(tmp_path / "cex-spot-state.json", _state(t0, 1.0))

    first = run(tmp_path, now=t0)
    assert first["entry_count"] == 1

    later = t0 + timedelta(hours=24, minutes=15)
    _write(tmp_path / "cex-spot-state.json", _state(later, 1.25))
    second = run(tmp_path, now=later)
    ledger = json.loads((tmp_path / "cex-spot-shadow-forward-ledger.json").read_text())
    entry = next(iter(ledger["entries"].values()))

    assert entry["entry_price_usd_like"] == 1.0
    assert entry["entry_immutable"] is True
    assert entry["latest_price_usd_like"] == 1.25
    assert entry["checkpoints"]["24h"]["timely"] is True
    assert entry["checkpoints"]["24h"]["directional_label"] == "POSITIVE"
    assert entry["checkpoints"]["24h"]["meaningful_wave_20pct"] is True
    assert second["sample_maturity"]["labeled_24h"] == 1
    assert second["sample_maturity"]["status"] == "INSUFFICIENT_SAMPLE_FOR_STATISTICAL_CLAIM"


def test_krw_native_price_is_never_mixed_into_usd_like_forward_price(tmp_path: Path):
    t0 = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    _write(tmp_path / "cex-spot-revival-radar.json", _radar(t0, entry_price=1.0))
    _write(tmp_path / "cex-spot-state.json", _state(t0, 1.2))

    run(tmp_path, now=t0)
    ledger = json.loads((tmp_path / "cex-spot-shadow-forward-ledger.json").read_text())
    entry = next(iter(ledger["entries"].values()))

    assert entry["latest_price_usd_like"] == 1.2
    assert entry["latest_exchange_count"] == 2
    assert "upbit" not in entry["latest_exchanges"]


def test_sample_gate_requires_30_labeled_with_10_positive_and_10_negative():
    entries = {}
    for i in range(30):
        label = "POSITIVE" if i < 20 else "NEGATIVE"
        entries[str(i)] = {
            "checkpoints": {
                "24h": {
                    "label_eligible": True,
                    "directional_label": label,
                    "meaningful_wave_20pct": i < 5,
                }
            }
        }

    maturity = _sample_maturity(entries)
    assert maturity["labeled_24h"] == 30
    assert maturity["positive_24h"] == 20
    assert maturity["negative_24h"] == 10
    assert maturity["descriptive_evaluation_allowed"] is True
    assert maturity["status"] == "SAMPLE_MATURE_FOR_MATCHED_REPLAY"
    assert maturity["statistical_claim_allowed"] is False
    assert maturity["production_promotion_allowed"] is False
