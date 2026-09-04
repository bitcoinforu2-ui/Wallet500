from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

DATA = Path("data")
LEDGER = DATA / "alpha-proof-ledger.json"
OUTCOMES = DATA / "outcome-tracker.json"
ARCHIVE = DATA / "outcome-archive"
HORIZONS = (
    (5, "5m"),
    (15, "15m"),
    (60, "1h"),
    (360, "6h"),
    (1440, "24h"),
    (10080, "7d"),
)
ROUND_TRIP_FRICTION_BPS = 200.0
EVM_CHAINS = {
    "bsc", "bnb", "ethereum", "eth", "base", "arbitrum",
    "polygon", "optimism", "avalanche",
}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dt(value: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _num(value: Any) -> float | None:
    try:
        out = float(value)
        return out if out == out and out not in (float("inf"), float("-inf")) else None
    except Exception:
        return None


def _norm(chain: Any, value: Any) -> str:
    chain_s = str(chain or "").lower()
    text = str(value or "")
    return text.lower() if chain_s in EVM_CHAINS else text


def _identity(chain: Any, token: Any, pair: Any) -> tuple[str, str, str]:
    c = str(chain or "").lower()
    return c, _norm(c, token), _norm(c, pair)


def _observation_is_verified(record: dict[str, Any], obs: dict[str, Any]) -> bool:
    if obs.get("measurement_eligible") is not True:
        return False
    if obs.get("token_identity_verified") is not True:
        return False
    version = _num(obs.get("price_identity_contract_version"))
    if version is None or version < 2:
        return False
    if _norm(record.get("chain"), obs.get("pair_address")) != _norm(record.get("chain"), record.get("pair_address")):
        return False
    price = _num(obs.get("price_usd"))
    return price is not None and price > 0 and _dt(obs.get("observed_at")) is not None


def _outcome_observations(payload: Any, record: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("tokens") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return []
    wanted = _identity(record.get("chain"), record.get("token"), record.get("pair_address"))
    out: list[dict[str, Any]] = []
    for row in records.values():
        if not isinstance(row, dict):
            continue
        got = _identity(
            row.get("chain"),
            row.get("token"),
            row.get("entry_pair_address") or row.get("pair_address"),
        )
        if got != wanted:
            continue
        for obs in row.get("history") or []:
            if isinstance(obs, dict) and _observation_is_verified(record, obs):
                out.append(obs)
    return out


def _archive_observations(archive_dir: Path, record: dict[str, Any]) -> Iterable[dict[str, Any]]:
    wanted = _identity(record.get("chain"), record.get("token"), record.get("pair_address"))
    if not archive_dir.is_dir():
        return
    for path in sorted(archive_dir.glob("*.jsonl.gz")):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(row, dict):
                        continue
                    got = _identity(
                        row.get("chain"),
                        row.get("token"),
                        row.get("entry_pair_address"),
                    )
                    if got != wanted:
                        continue
                    for obs in row.get("observations") or []:
                        if isinstance(obs, dict) and _observation_is_verified(record, obs):
                            yield obs
        except (OSError, EOFError):
            continue


def _return_pct(current: Any, entry: Any) -> float | None:
    cur = _num(current)
    base = _num(entry)
    if cur is None or base is None or cur <= 0 or base <= 0:
        return None
    return round((cur / base - 1.0) * 100.0, 6)


def _checkpoint(record: dict[str, Any], obs: dict[str, Any], event: datetime) -> dict[str, Any] | None:
    seen = _dt(obs.get("observed_at"))
    ret = _return_pct(obs.get("price_usd"), record.get("entry_price_usd"))
    if seen is None or ret is None or seen < event:
        return None
    return {
        "captured_at": seen.isoformat(),
        "captured_age_minutes": round((seen - event).total_seconds() / 60.0, 3),
        "price_usd": _num(obs.get("price_usd")),
        "liquidity_usd": _num(obs.get("liquidity_usd")),
        "gross_return_pct": ret,
        "friction_adjusted_return_pct": round(ret - ROUND_TRIP_FRICTION_BPS / 100.0, 6),
        "recovery_provenance": "IMMUTABLE_EXACT_PAIR_OUTCOME_HISTORY_V1",
    }


def _recover_record(
    record: dict[str, Any],
    outcome_payload: Any,
    archive_dir: Path,
) -> int:
    event = _dt(record.get("event_at"))
    if event is None:
        return 0
    checkpoints = record.setdefault("checkpoints", {})
    missing = [(minutes, label) for minutes, label in HORIZONS if label not in checkpoints]
    if not missing:
        return 0

    observations = _outcome_observations(outcome_payload, record)
    observations.extend(_archive_observations(archive_dir, record))
    observations.sort(key=lambda row: _dt(row.get("observed_at")) or datetime.max.replace(tzinfo=timezone.utc))

    recovered = 0
    for minutes, label in missing:
        target = event + timedelta(minutes=minutes)
        chosen = next((obs for obs in observations if (_dt(obs.get("observed_at")) or event) >= target), None)
        if chosen is None:
            continue
        cp = _checkpoint(record, chosen, event)
        if cp is None:
            continue
        checkpoints[label] = cp
        recovered += 1
    return recovered


def recover(data_dir: Path = DATA) -> dict[str, Any]:
    ledger_path = data_dir / LEDGER.name
    outcome_path = data_dir / OUTCOMES.name
    archive_dir = data_dir / ARCHIVE.name

    ledger = _load(ledger_path, {})
    if not isinstance(ledger, dict) or ledger.get("mode") != "FORWARD_ONLY_ALPHA_PROOF_V1":
        return {"status": "SKIPPED", "reason": "ALPHA_LEDGER_MISSING_OR_WRONG_MODE", "recovered": 0}

    outcomes = _load(outcome_path, {})
    recovered_signals = 0
    recovered_controls = 0

    for record in (ledger.get("signals") or {}).values():
        if isinstance(record, dict):
            recovered_signals += _recover_record(record, outcomes, archive_dir)
    for record in (ledger.get("controls") or {}).values():
        if isinstance(record, dict):
            recovered_controls += _recover_record(record, outcomes, archive_dir)

    recovered = recovered_signals + recovered_controls
    if recovered:
        ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
        ledger["checkpoint_recovery"] = {
            "mode": "IMMUTABLE_EXACT_PAIR_OUTCOME_HISTORY_V1",
            "recovered_this_run": recovered,
            "signals_recovered_this_run": recovered_signals,
            "controls_recovered_this_run": recovered_controls,
            "existing_checkpoints_never_rewritten": True,
            "requires_measurement_eligible": True,
            "requires_token_identity_verified": True,
            "requires_price_identity_contract_version_gte": 2,
        }
        _write(ledger_path, ledger)

    return {
        "status": "RECOVERED" if recovered else "NO_RECOVERABLE_GAPS",
        "recovered": recovered,
        "signals_recovered": recovered_signals,
        "controls_recovered": recovered_controls,
    }


def main() -> None:
    print(json.dumps(recover(), indent=2))


if __name__ == "__main__":
    main()
