from copy import deepcopy
from datetime import datetime, timedelta, timezone

from wallet500.decision_replay_lab import HORIZON_MINUTES
from wallet500.historical_pair_backfill import (
    SOURCE_TAG,
    _parse_ohlcv,
    _select_horizon_points,
    backfill,
)


def _source(first_at: str = "2026-09-01T00:00:00+00:00") -> dict:
    return {
        "records": {
            "x": {
                "chain": "solana",
                "token_address": "TOKEN",
                "pair_address": "PAIR",
                "event_at": first_at,
                "decision_snapshot": {
                    "identity": {"chain": "solana", "token": "TOKEN", "pair_address": "PAIR"},
                    "entry": {
                        "observed_at": first_at,
                        "entry_price_usd": 1.0,
                        "verified_execution_liquidity_usd": 100000.0,
                        "actionable": False,
                    },
                },
            }
        }
    }


def _payload(first: datetime) -> dict:
    rows = []
    for index, minutes in enumerate(HORIZON_MINUTES.values(), start=1):
        known_at = first + timedelta(minutes=minutes)
        open_at = known_at - timedelta(minutes=15)
        close = 1.0 + index / 10.0
        rows.append([int(open_at.timestamp()), close - 0.05, close + 0.05, close - 0.1, close, 1000.0 * index])
    return {"data": {"attributes": {"ohlcv_list": list(reversed(rows))}}}


def test_candle_close_is_not_known_at_candle_open():
    first = datetime(2026, 9, 1, 0, 10, tzinfo=timezone.utc)
    payload = {
        "data": {
            "attributes": {
                "ohlcv_list": [
                    [int(datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc).timestamp()), 1, 1, 1, 1.1, 10],
                    [int(datetime(2026, 9, 1, 0, 15, tzinfo=timezone.utc).timestamp()), 1, 1, 1, 1.2, 10],
                ]
            }
        }
    }
    candles = _parse_ohlcv(payload)
    points = _select_horizon_points(candles, first, datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc))
    assert points["15m"]["candle"]["known_at"] == datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)
    assert points["15m"]["candle"]["close"] == 1.2


def test_backfill_adds_exact_pair_horizon_observations_without_mutating_t0():
    source = _source()
    before = deepcopy(source["records"]["x"]["decision_snapshot"])
    first = datetime(2026, 9, 1, tzinfo=timezone.utc)
    captured_args = []

    def fetcher(network, pair, token, before_timestamp):
        captured_args.append((network, pair, token, before_timestamp))
        return _payload(first)

    source, state, summary = backfill(
        source,
        {},
        fetcher=fetcher,
        now=first + timedelta(days=8),
        max_records=1,
    )

    assert captured_args[0][:3] == ("solana", "PAIR", "TOKEN")
    assert summary["processed"] == 1
    assert summary["checkpoints_added"] == len(HORIZON_MINUTES)
    assert source["records"]["x"]["decision_snapshot"] == before

    checkpoints = source["records"]["x"]["checkpoint_history"]
    assert {cp["horizon"] for cp in checkpoints if cp["source"] == SOURCE_TAG} == set(HORIZON_MINUTES)
    assert all(cp["pair_address"] == "PAIR" and cp["token_address"] == "TOKEN" for cp in checkpoints)
    rec_state = next(iter(state["records"].values()))
    assert rec_state["terminal_complete"] is True
    assert rec_state["status"] == "TERMINAL_COMPLETE"


def test_backfill_does_not_displace_an_earlier_reliable_live_observation():
    source = _source()
    first = datetime(2026, 9, 1, tzinfo=timezone.utc)
    source["records"]["x"]["checkpoint_history"] = [
        {
            "captured_at": (first + timedelta(hours=24, minutes=1)).isoformat(),
            "price_usd": 1.25,
            "pair_address": "PAIR",
            "token_address": "TOKEN",
            "chain": "solana",
            "source": "LIVE_EXACT_PAIR",
            "reliable": True,
        }
    ]

    source, _, _ = backfill(
        source,
        {},
        fetcher=lambda *_: _payload(first),
        now=first + timedelta(days=8),
        max_records=1,
    )
    checkpoints = source["records"]["x"]["checkpoint_history"]
    backfilled_24h = [cp for cp in checkpoints if cp.get("source") == SOURCE_TAG and cp.get("horizon") == "24h"]
    assert backfilled_24h == []
    assert any(cp.get("source") == "LIVE_EXACT_PAIR" for cp in checkpoints)


def test_unsupported_network_never_calls_provider():
    source = _source()
    row = source["records"]["x"]
    row["chain"] = "unknown-chain"
    row["decision_snapshot"]["identity"]["chain"] = "unknown-chain"
    called = False

    def fetcher(*_):
        nonlocal called
        called = True
        return {}

    _, state, summary = backfill(
        source,
        {},
        fetcher=fetcher,
        now=datetime(2026, 9, 20, tzinfo=timezone.utc),
        max_records=1,
    )
    assert called is False
    assert summary["processed"] == 0
    assert "UNSUPPORTED_NETWORK" in summary["statuses"]
    assert next(iter(state["records"].values()))["status"] == "UNSUPPORTED_NETWORK"
