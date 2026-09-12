from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .precision_pre_wave import build as build_v1

DATA = Path("data")
OUT = DATA / "precision-pre-wave.json"
LEDGER = DATA / "precision-pre-wave-early-signal-ledger.json"
MODE = "MANUAL_REVIEW_PRECISION_PRE_WAVE_6OF7_V2_PERSISTENT_EARLY_SIGNAL"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _base_symbol(v: Any) -> str:
    s = str(v or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()
    return s[:-4] if s.endswith("USDT") else s


def _dt(v: Any) -> datetime | None:
    raw = str(v or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        value = datetime.fromisoformat(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except Exception:
        return None


def _milestone_from_spot(row: dict) -> dict:
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    alert = milestones.get("first_alert") if isinstance(milestones.get("first_alert"), dict) else {}
    return {
        "first_alert_observed_at": alert.get("observed_at"),
        "first_alert_reference_price": alert.get("reference_price"),
        "first_alert_score": alert.get("score"),
        "first_alert_coherent_confirmations": alert.get("coherent_confirmations"),
        "first_alert_reference_exchange": alert.get("reference_exchange"),
    }


def _milestone_from_pending(row: dict) -> dict:
    return {
        "first_alert_observed_at": row.get("first_alert_observed_at"),
        "first_alert_reference_price": row.get("first_alert_reference_price"),
        "first_alert_score": row.get("first_alert_score"),
        "first_alert_coherent_confirmations": row.get("first_alert_coherent_confirmations"),
        "first_alert_reference_exchange": row.get("first_alert_reference_exchange"),
    }


def _valid_milestone(m: dict) -> bool:
    try:
        return bool(_dt(m.get("first_alert_observed_at")) and float(m.get("first_alert_reference_price") or 0) > 0 and float(m.get("first_alert_score") or 0) > 0)
    except Exception:
        return False


def _merge_earliest(existing: dict, incoming: dict) -> dict:
    if not _valid_milestone(incoming):
        return existing
    if not _valid_milestone(existing):
        return dict(incoming)
    old_dt = _dt(existing.get("first_alert_observed_at"))
    new_dt = _dt(incoming.get("first_alert_observed_at"))
    if old_dt is None or (new_dt is not None and new_dt < old_dt):
        return dict(incoming)
    return existing


def update_ledger(previous: dict, pending: dict, spot: dict, observed_at: str) -> dict:
    symbols = previous.get("symbols") if isinstance(previous.get("symbols"), dict) else {}
    symbols = {str(k): dict(v) for k, v in symbols.items() if isinstance(v, dict)}

    for row in pending.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        symbol = _base_symbol(row.get("symbol") or row.get("base_symbol"))
        if not symbol:
            continue
        merged = _merge_earliest(symbols.get(symbol, {}), _milestone_from_pending(row))
        if merged:
            merged["symbol"] = symbol
            merged.setdefault("first_preserved_at", observed_at)
            merged["last_confirmed_at"] = observed_at
            merged["source"] = "IMMUTABLE_EARLY_SIGNAL_LEDGER"
            symbols[symbol] = merged

    spot_rows = []
    for name in ("watchlist", "alerts"):
        spot_rows.extend([x for x in spot.get(name) or [] if isinstance(x, dict)])
    for row in spot_rows:
        symbol = _base_symbol(row.get("symbol"))
        if not symbol:
            continue
        merged = _merge_earliest(symbols.get(symbol, {}), _milestone_from_spot(row))
        if merged:
            merged["symbol"] = symbol
            merged.setdefault("first_preserved_at", observed_at)
            merged["last_confirmed_at"] = observed_at
            merged["source"] = "IMMUTABLE_EARLY_SIGNAL_LEDGER"
            symbols[symbol] = merged

    return {
        "version": 1,
        "mode": "IMMUTABLE_FORWARD_ONLY_EARLY_SIGNAL_LEDGER_V1",
        "updated_at": observed_at,
        "truth_contract": {
            "no_hindsight": True,
            "earliest_first_alert_never_overwritten_by_later_signal": True,
            "symbol_entry_is_evidence_only_not_actionable": True,
            "exact_identity_pair_still_required_for_precision_pre_wave": True,
            "real_alert_gate_unchanged": True,
        },
        "symbol_count": len(symbols),
        "symbols": symbols,
    }


def _enriched_pending(pending: dict, ledger: dict) -> dict:
    current: dict[str, dict] = {}
    for row in pending.get("candidates") or []:
        if isinstance(row, dict):
            symbol = _base_symbol(row.get("symbol") or row.get("base_symbol"))
            if symbol:
                current[symbol] = dict(row)
    for symbol, evidence in (ledger.get("symbols") or {}).items():
        if not isinstance(evidence, dict):
            continue
        row = current.setdefault(symbol, {"symbol": f"{symbol}USDT", "base_symbol": symbol})
        for field in (
            "first_alert_observed_at",
            "first_alert_reference_price",
            "first_alert_score",
            "first_alert_coherent_confirmations",
            "first_alert_reference_exchange",
        ):
            if evidence.get(field) is not None:
                row[field] = evidence.get(field)
    return {"candidates": list(current.values())}


def run(data_dir: str | Path = DATA, observed_at: str | None = None) -> dict:
    data = Path(data_dir)
    now = observed_at or datetime.now(timezone.utc).isoformat()
    pending = _load(data / "cex-early-revival-pending.json", {})
    spot = _load(data / "cex-spot-revival-radar.json", {})
    ledger = update_ledger(_load(data / LEDGER.name, {}), pending, spot, now)
    _write(data / LEDGER.name, ledger)

    payload = build_v1(
        _load(data / "near-alert-observatory.json", {}),
        _enriched_pending(pending, ledger),
        _load(data / "cex-spot-identity-radar.json", {}),
        _load(data / "real-alerts.json", {}),
        observed_at=now,
    )
    payload["version"] = 2
    payload["mode"] = MODE
    payload["early_signal_ledger"] = {
        "mode": ledger.get("mode"),
        "symbol_count": ledger.get("symbol_count"),
        "forward_only": True,
        "immutable_earliest_first_alert": True,
    }
    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth["persistent_early_signal_ledger_required"] = True
    truth["no_hindsight"] = True
    truth["early_signal_survives_watchlist_exit"] = True
    payload["truth_contract"] = truth
    _write(data / OUT.name, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
