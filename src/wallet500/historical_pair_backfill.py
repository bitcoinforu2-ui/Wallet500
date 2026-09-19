from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from wallet500.decision_replay_lab import HORIZON_MINUTES, _dt, _identity, _immutable_key, _reliable_candidates

DATA = Path("data")
SOURCE = "research-sample-ledger.json"
STATE = "historical-pair-backfill-state.json"

MODE = "RESEARCH_ONLY_HISTORICAL_PAIR_BACKFILL_V1"
PROVIDER = "GECKOTERMINAL_PUBLIC_OHLCV_V2"
SOURCE_TAG = "GECKOTERMINAL_OHLCV_15M_BACKFILL_V1"
BASE_URL = "https://api.geckoterminal.com/api/v2"
ACCEPT = "application/json;version=20230203"
CANDLE_MINUTES = 15
CANDLE_SECONDS = CANDLE_MINUTES * 60
DEFAULT_LIMIT = 700
DEFAULT_MAX_RECORDS = 8
DEFAULT_REQUEST_INTERVAL_SECONDS = 7.0
MAX_ATTEMPTS_WITHOUT_DATA = 4
RETRY_NO_DATA_HOURS = 24

NETWORK_IDS = {
    "solana": "solana",
    "ethereum": "eth",
    "eth": "eth",
    "bnb": "bsc",
    "bsc": "bsc",
    "binance-smart-chain": "bsc",
    "base": "base",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon_pos",
    "polygon_pos": "polygon_pos",
    "matic": "polygon_pos",
}


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _network_id(chain: str) -> str | None:
    return NETWORK_IDS.get(str(chain or "").strip().lower())


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _records(source: dict) -> list[tuple[str, dict]]:
    raw = source.get("records")
    if isinstance(raw, dict):
        return [(str(key), value) for key, value in raw.items() if isinstance(value, dict)]
    if isinstance(raw, list):
        return [(str(index), value) for index, value in enumerate(raw) if isinstance(value, dict)]
    return []


def _state_records(state: dict) -> dict[str, dict]:
    raw = state.get("records")
    if isinstance(raw, dict):
        return raw
    raw = {}
    state["records"] = raw
    return raw


def _parse_ohlcv(payload: dict) -> list[dict]:
    values = (((payload.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or [])
    candles: list[dict] = []
    for item in values:
        if not isinstance(item, (list, tuple)) or len(item) < 6:
            continue
        ts = _float(item[0])
        close = _float(item[4])
        if ts is None or close is None or close <= 0:
            continue
        open_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        known_dt = open_dt + timedelta(seconds=CANDLE_SECONDS)
        candles.append(
            {
                "open_at": open_dt,
                "known_at": known_dt,
                "open": _float(item[1]),
                "high": _float(item[2]),
                "low": _float(item[3]),
                "close": close,
                "volume_usd": _float(item[5]),
            }
        )
    candles.sort(key=lambda x: x["known_at"])
    return candles


def _select_horizon_points(candles: list[dict], first_dt: datetime, now: datetime) -> dict[str, dict]:
    points: dict[str, dict] = {}
    usable = [c for c in candles if first_dt < c["known_at"] <= now + timedelta(minutes=1)]
    for horizon, minutes in HORIZON_MINUTES.items():
        target = first_dt + timedelta(minutes=minutes)
        if target > now:
            continue
        selected = next((c for c in usable if c["known_at"] >= target), None)
        if selected is None:
            continue
        points[horizon] = {
            "target_at": target,
            "candle": selected,
            "lag_seconds": (selected["known_at"] - target).total_seconds(),
        }
    return points


def _existing_first_at_or_after(row: dict, identity: tuple[str, str, str, str], target: datetime) -> dict | None:
    candidates, _ = _reliable_candidates(row, identity)
    return next((c for c in candidates if c["observed_dt"] >= target), None)


def _append_checkpoint(row: dict, checkpoint: dict) -> None:
    history = row.get("checkpoint_history")
    if history is None:
        row["checkpoint_history"] = [checkpoint]
        return
    if isinstance(history, list):
        history.append(checkpoint)
        return
    if isinstance(history, dict):
        bucket = history.get("geckoterminal_backfill")
        if not isinstance(bucket, list):
            bucket = []
            history["geckoterminal_backfill"] = bucket
        bucket.append(checkpoint)
        return
    fallback = row.get("forward_observations")
    if not isinstance(fallback, list):
        fallback = []
        row["forward_observations"] = fallback
    fallback.append(checkpoint)


def _provider_checkpoint(identity: tuple[str, str, str, str], horizon: str, point: dict) -> dict:
    chain, token, pair, _ = identity
    candle = point["candle"]
    return {
        "horizon": horizon,
        "captured_at": _iso(candle["known_at"]),
        "price_usd": candle["close"],
        "chain": chain,
        "token_address": token,
        "pair_address": pair,
        "source": SOURCE_TAG,
        "reliable": True,
        "historical_backfill": True,
        "provider": PROVIDER,
        "provider_interval": "15m",
        "provider_candle_open_at": _iso(candle["open_at"]),
        "provider_open_usd": candle["open"],
        "provider_high_usd": candle["high"],
        "provider_low_usd": candle["low"],
        "provider_close_usd": candle["close"],
        "provider_volume_usd": candle["volume_usd"],
        "target_at": _iso(point["target_at"]),
        "target_lag_seconds": round(point["lag_seconds"], 3),
        "selection_contract": "FIRST_FULLY_CLOSED_15M_EXACT_POOL_CANDLE_AT_OR_AFTER_TARGET",
        "point_in_time_contract": "CLOSE_PRICE_BECOMES_KNOWN_AT_CANDLE_END_ONLY",
    }


def _coverage(row: dict, identity: tuple[str, str, str, str], now: datetime) -> tuple[list[str], list[str]]:
    candidates, _ = _reliable_candidates(row, identity)
    matured: list[str] = []
    observed: list[str] = []
    first_dt = _dt(identity[3])
    if first_dt is None:
        return matured, observed
    for horizon, minutes in HORIZON_MINUTES.items():
        target = first_dt + timedelta(minutes=minutes)
        if target > now:
            continue
        matured.append(horizon)
        if any(c["observed_dt"] >= target for c in candidates):
            observed.append(horizon)
    return matured, observed


def _next_due(first_dt: datetime, now: datetime, observed: set[str]) -> datetime | None:
    future_targets = []
    for horizon, minutes in HORIZON_MINUTES.items():
        if horizon in observed:
            continue
        target = first_dt + timedelta(minutes=minutes)
        if target > now:
            future_targets.append(target + timedelta(minutes=CANDLE_MINUTES))
    return min(future_targets) if future_targets else None


def _before_timestamp(first_dt: datetime, now: datetime) -> int:
    terminal = first_dt + timedelta(minutes=HORIZON_MINUTES["7d"] + (2 * CANDLE_MINUTES))
    return int(min(now, terminal).timestamp()) + 1


def geckoterminal_fetch(
    network: str,
    pair_address: str,
    token_address: str,
    before_timestamp: int,
    *,
    base_url: str = BASE_URL,
    timeout_seconds: float = 20.0,
) -> dict:
    query = urllib.parse.urlencode(
        {
            "aggregate": 15,
            "before_timestamp": before_timestamp,
            "limit": DEFAULT_LIMIT,
            "currency": "usd",
            "token": token_address,
            "include_empty_intervals": "false",
        }
    )
    url = (
        f"{base_url.rstrip('/')}/networks/{urllib.parse.quote(network, safe='')}"
        f"/pools/{urllib.parse.quote(pair_address, safe='')}/ohlcv/minute?{query}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": ACCEPT,
            "User-Agent": "Wallet500-Historical-Outcome-Research/1.0",
        },
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 or 500 <= exc.code <= 599:
                time.sleep(min(10.0, 2.0 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(min(10.0, 2.0 ** attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("GECKOTERMINAL_FETCH_FAILED")


Fetcher = Callable[[str, str, str, int], dict]


def _eligible(row: dict, record_state: dict, now: datetime) -> tuple[tuple[str, str, str, str] | None, str | None]:
    identity = _identity(row)
    if identity is None:
        return None, "INVALID_EXACT_IDENTITY"
    chain, _, _, first_at = identity
    if _network_id(chain) is None:
        return identity, "UNSUPPORTED_NETWORK"
    first_dt = _dt(first_at)
    if first_dt is None:
        return identity, "INVALID_T0"
    if first_dt + timedelta(minutes=CANDLE_MINUTES) > now:
        return identity, "WAITING_FIRST_CANDLE"
    if record_state.get("terminal_complete") is True:
        return identity, "TERMINAL_COMPLETE"
    due = _dt(record_state.get("next_due_at"))
    if due is not None and due > now:
        return identity, "WAITING_NEXT_HORIZON"
    if record_state.get("status") == "NO_DATA_EXHAUSTED" and int(record_state.get("attempts") or 0) >= MAX_ATTEMPTS_WITHOUT_DATA:
        return identity, "NO_DATA_EXHAUSTED"
    return identity, None


def backfill(
    source: dict,
    state: dict | None = None,
    *,
    fetcher: Fetcher = geckoterminal_fetch,
    now: datetime | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    request_interval_seconds: float = 0.0,
) -> tuple[dict, dict, dict]:
    state = state if isinstance(state, dict) else {}
    state.setdefault("version", 1)
    state["mode"] = MODE
    state["research_only"] = True
    state["production_effect"] = False
    state["t0_mutation_forbidden"] = True
    state["provider"] = PROVIDER
    state["source_ledger"] = SOURCE
    records_state = _state_records(state)

    now = now or _now_utc()
    processed = 0
    changed_rows = 0
    checkpoints_added = 0
    errors: list[dict] = []
    statuses: dict[str, int] = {}

    candidates: list[tuple[datetime, str, dict, tuple[str, str, str, str], dict]] = []
    for source_key, row in _records(source):
        provisional_identity = _identity(row)
        provisional_key = _immutable_key(provisional_identity) if provisional_identity is not None else f"SOURCE:{source_key}"
        rec_state = records_state.setdefault(provisional_key, {})
        identity, reason = _eligible(row, rec_state, now)
        if reason is not None:
            rec_state["status"] = reason
            statuses[reason] = statuses.get(reason, 0) + 1
            continue
        assert identity is not None
        key = _immutable_key(identity)
        if key != provisional_key:
            rec_state = records_state.setdefault(key, rec_state)
        first_dt = _dt(identity[3])
        assert first_dt is not None
        candidates.append((first_dt, key, row, identity, rec_state))

    candidates.sort(key=lambda item: (int(item[4].get("attempts") or 0), item[0], item[1]))

    for _, key, row, identity, rec_state in candidates[: max(0, max_records)]:
        chain, token, pair, first_at = identity
        first_dt = _dt(first_at)
        assert first_dt is not None
        network = _network_id(chain)
        assert network is not None
        processed += 1
        rec_state["attempts"] = int(rec_state.get("attempts") or 0) + 1
        rec_state["last_attempt_at"] = _iso(now)
        rec_state["network"] = network
        rec_state["chain"] = chain
        rec_state["token_address"] = token
        rec_state["pair_address"] = pair

        try:
            payload = fetcher(network, pair, token, _before_timestamp(first_dt, now))
            candles = _parse_ohlcv(payload)
            points = _select_horizon_points(candles, first_dt, now)
            added_here = 0
            for horizon, point in points.items():
                target = point["target_at"]
                existing = _existing_first_at_or_after(row, identity, target)
                new_known_at = point["candle"]["known_at"]
                if existing is not None and existing["observed_dt"] <= new_known_at:
                    continue
                _append_checkpoint(row, _provider_checkpoint(identity, horizon, point))
                added_here += 1

            if added_here:
                changed_rows += 1
                checkpoints_added += added_here

            matured, observed = _coverage(row, identity, now)
            observed_set = set(observed)
            terminal_complete = "7d" in observed_set
            rec_state.update(
                {
                    "status": "TERMINAL_COMPLETE" if terminal_complete else ("PARTIAL" if observed else "NO_DATA"),
                    "terminal_complete": terminal_complete,
                    "candles_returned": len(candles),
                    "matured_horizons": matured,
                    "observed_horizons": observed,
                    "checkpoints_added_last_attempt": added_here,
                    "last_success_at": _iso(now) if candles else rec_state.get("last_success_at"),
                }
            )
            next_due = _next_due(first_dt, now, observed_set)
            if next_due is not None:
                rec_state["next_due_at"] = _iso(next_due)
            elif not terminal_complete:
                rec_state["next_due_at"] = _iso(now + timedelta(hours=RETRY_NO_DATA_HOURS))
                if not candles and int(rec_state.get("attempts") or 0) >= MAX_ATTEMPTS_WITHOUT_DATA:
                    rec_state["status"] = "NO_DATA_EXHAUSTED"
            else:
                rec_state.pop("next_due_at", None)
            statuses[rec_state["status"]] = statuses.get(rec_state["status"], 0) + 1
        except Exception as exc:
            error_name = type(exc).__name__
            rec_state["status"] = "PROVIDER_ERROR"
            rec_state["last_error"] = f"{error_name}:{str(exc)[:240]}"
            rec_state["next_due_at"] = _iso(now + timedelta(hours=1))
            statuses["PROVIDER_ERROR"] = statuses.get("PROVIDER_ERROR", 0) + 1
            errors.append({"key": key, "error": rec_state["last_error"]})

        if request_interval_seconds > 0 and processed < min(len(candidates), max(0, max_records)):
            time.sleep(request_interval_seconds)

    state["updated_at"] = _iso(now)
    state["summary"] = {
        "source_records": len(_records(source)),
        "eligible_due": len(candidates),
        "processed": processed,
        "changed_rows": changed_rows,
        "checkpoints_added": checkpoints_added,
        "statuses": statuses,
        "errors": errors[:20],
        "guardrails": {
            "exact_pair_endpoint_required": True,
            "token_orientation_explicit": True,
            "closed_candle_only": True,
            "candle_close_known_at_end_only": True,
            "t0_mutation": False,
            "production_changes": False,
            "telegram_changes": False,
        },
    }
    return source, state, state["summary"]


def main() -> None:
    source = _load(DATA / SOURCE, {})
    state = _load(DATA / STATE, {})
    max_records = int(os.getenv("WALLET500_BACKFILL_MAX_RECORDS", str(DEFAULT_MAX_RECORDS)))
    interval = float(os.getenv("WALLET500_BACKFILL_REQUEST_INTERVAL_SECONDS", str(DEFAULT_REQUEST_INTERVAL_SECONDS)))
    source, state, summary = backfill(
        source,
        state,
        max_records=max_records,
        request_interval_seconds=interval,
    )
    if summary.get("changed_rows", 0) > 0:
        (DATA / SOURCE).write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("HISTORICAL_PAIR_BACKFILL_OK", summary)


if __name__ == "__main__":
    main()
