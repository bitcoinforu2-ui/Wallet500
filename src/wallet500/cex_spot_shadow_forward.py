from __future__ import annotations

import gzip
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

DATA = Path("data")
RADAR = DATA / "cex-spot-revival-radar.json"
STATE = DATA / "cex-spot-state.json"
LEDGER = DATA / "cex-spot-shadow-forward-ledger.json"
REPORT = DATA / "cex-spot-shadow-forward-report.json"

MODE = "FORWARD_ONLY_CEX_SPOT_SHADOW_V1"
USD_LIKE_QUOTES = {"USD", "USDT", "USDC"}
HORIZONS = ((6, "6h"), (24, "24h"), (72, "72h"))
MAX_CHECKPOINT_DELAY_MINUTES = 45.0
MIN_LABELED_24H = 30
MIN_POSITIVE_24H = 10
MIN_NEGATIVE_24H = 10
MEANINGFUL_WAVE_PEAK_PCT = 20.0


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _load_state(path: Path) -> dict[str, Any]:
    gz = Path(str(path) + ".gz")
    try:
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8") as handle:
                value = json.load(handle)
                return value if isinstance(value, dict) else {}
        value = _load_json(path, {})
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def _dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _latest_usd_like_prices(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    markets = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for key, history in markets.items():
        if not isinstance(key, str) or not isinstance(history, list) or not history:
            continue
        parts = key.split(":", 3)
        if len(parts) < 4 or parts[0] != "spot":
            continue
        exchange, symbol = parts[1], parts[2]
        last = history[-1] if isinstance(history[-1], dict) else {}
        quote = str(last.get("quote_symbol") or "").upper()
        price = _num(last.get("price"))
        observed_at = _dt(last.get("observed_at"))
        if quote not in USD_LIKE_QUOTES or price is None or price <= 0 or observed_at is None:
            continue
        grouped.setdefault(symbol, []).append(
            {
                "exchange": exchange,
                "price": price,
                "observed_at": observed_at,
                "quote_symbol": quote,
            }
        )

    out: dict[str, dict[str, Any]] = {}
    for symbol, rows in grouped.items():
        prices = [float(row["price"]) for row in rows]
        latest = max(row["observed_at"] for row in rows)
        out[symbol] = {
            "symbol": symbol,
            "price_usd_like": float(median(prices)),
            "observed_at": _iso(latest),
            "exchange_count": len(rows),
            "exchanges": sorted({str(row["exchange"]) for row in rows}),
            "aggregation": "MEDIAN_USD_LIKE_SPOT_VENUES",
        }
    return out


def _candidate_event(row: dict[str, Any]) -> tuple[datetime | None, float | None, dict[str, Any]]:
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    first = milestones.get("first_shadow_watch") if isinstance(milestones.get("first_shadow_watch"), dict) else {}
    observed_at = _dt(first.get("observed_at"))
    price = _num(first.get("reference_price"))
    quote = str(first.get("reference_quote_symbol") or "USDT").upper()
    if quote not in USD_LIKE_QUOTES:
        price = None
    return observed_at, price, first


def _entry_key(symbol: str, event_at: datetime) -> str:
    return f"{symbol}|{_iso(event_at)}"


def _entry_record(row: dict[str, Any], event_at: datetime, entry_price: float, enrolled_at: datetime) -> dict[str, Any]:
    slow = row.get("slow_ignition") if isinstance(row.get("slow_ignition"), dict) else {}
    regional = row.get("regional_spot_lead") if isinstance(row.get("regional_spot_lead"), dict) else {}
    coverage = row.get("source_coverage") if isinstance(row.get("source_coverage"), dict) else {}
    return {
        "mode": MODE,
        "lane": "CEX_SPOT_SHADOW_FORWARD",
        "symbol": str(row.get("symbol") or ""),
        "event_at": _iso(event_at),
        "enrolled_at": _iso(enrolled_at),
        "entry_price_usd_like": entry_price,
        "entry_price_source": "IMMUTABLE_FIRST_SHADOW_WATCH_MILESTONE",
        "entry_immutable": True,
        "research_only": True,
        "actionable": False,
        "automatic_buy": False,
        "production_portfolio_impact": "NONE",
        "shadow_features": list(row.get("shadow_features") or []),
        "shadow_reasons": list(row.get("shadow_reasons") or []),
        "slow_ignition_at_entry": {
            "status": slow.get("status"),
            "confirmations": slow.get("confirmations"),
            "exchanges": list(slow.get("exchanges") or []),
            "multi_horizon_confirmations": slow.get("multi_horizon_confirmations"),
            "multi_horizon_exchanges": list(slow.get("multi_horizon_exchanges") or []),
        },
        "regional_spot_lead_at_entry": regional,
        "source_coverage_at_entry": coverage,
        "spot_revival_score_at_entry": row.get("spot_revival_score"),
        "coherent_confirmations_at_entry": row.get("coherent_confirmations"),
        "confirmations_at_entry": row.get("confirmations"),
        "observations": 0,
        "samples": [],
        "checkpoints": {},
        "peak_sampled_return_pct": None,
        "trough_sampled_return_pct": None,
        "latest_return_pct": None,
        "completed": False,
    }


def _observe(entry: dict[str, Any], market: dict[str, Any]) -> bool:
    if entry.get("completed") is True:
        return False
    event_at = _dt(entry.get("event_at"))
    observed_at = _dt(market.get("observed_at"))
    entry_price = _num(entry.get("entry_price_usd_like"))
    current_price = _num(market.get("price_usd_like"))
    last_observed = _dt(entry.get("latest_observed_at"))
    if event_at is None or observed_at is None or entry_price is None or entry_price <= 0 or current_price is None or current_price <= 0:
        return False
    if observed_at < event_at or (last_observed is not None and observed_at <= last_observed):
        return False

    ret = (current_price / entry_price - 1.0) * 100.0
    age_minutes = (observed_at - event_at).total_seconds() / 60.0
    peak = _num(entry.get("peak_sampled_return_pct"))
    trough = _num(entry.get("trough_sampled_return_pct"))
    peak = ret if peak is None else max(peak, ret)
    trough = ret if trough is None else min(trough, ret)

    entry["observations"] = int(entry.get("observations") or 0) + 1
    entry["latest_observed_at"] = _iso(observed_at)
    entry["latest_price_usd_like"] = current_price
    entry["latest_return_pct"] = round(ret, 6)
    entry["peak_sampled_return_pct"] = round(peak, 6)
    entry["trough_sampled_return_pct"] = round(trough, 6)
    entry["latest_exchange_count"] = int(market.get("exchange_count") or 0)
    entry["latest_exchanges"] = list(market.get("exchanges") or [])
    samples = entry.setdefault("samples", [])
    samples.append(
        {
            "observed_at": _iso(observed_at),
            "price_usd_like": current_price,
            "return_pct": round(ret, 6),
            "exchange_count": int(market.get("exchange_count") or 0),
        }
    )
    entry["samples"] = samples[-320:]

    checkpoints = entry.setdefault("checkpoints", {})
    for hours, label in HORIZONS:
        horizon_minutes = hours * 60.0
        if age_minutes < horizon_minutes or label in checkpoints:
            continue
        delay = age_minutes - horizon_minutes
        checkpoint = {
            "captured_at": _iso(observed_at),
            "captured_age_minutes": round(age_minutes, 3),
            "capture_delay_minutes": round(delay, 3),
            "timely": delay <= MAX_CHECKPOINT_DELAY_MINUTES,
            "price_usd_like": current_price,
            "gross_return_pct": round(ret, 6),
            "peak_return_pct_to_checkpoint": round(peak, 6),
            "trough_return_pct_to_checkpoint": round(trough, 6),
            "exchange_count": int(market.get("exchange_count") or 0),
        }
        checkpoints[label] = checkpoint
        if label == "24h":
            if checkpoint["timely"]:
                checkpoint["directional_label"] = "POSITIVE" if ret > 0 else "NEGATIVE"
                checkpoint["meaningful_wave_20pct"] = peak >= MEANINGFUL_WAVE_PEAK_PCT
                checkpoint["label_eligible"] = True
            else:
                checkpoint["directional_label"] = "LATE_CHECKPOINT_EXCLUDED"
                checkpoint["meaningful_wave_20pct"] = None
                checkpoint["label_eligible"] = False
        if label == "72h":
            entry["completed"] = True
            entry["completed_at"] = _iso(observed_at)
    return True


def _sample_maturity(entries: dict[str, Any]) -> dict[str, Any]:
    labeled = 0
    positive = 0
    negative = 0
    meaningful = 0
    late_excluded = 0
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        cp = (entry.get("checkpoints") or {}).get("24h")
        if not isinstance(cp, dict):
            continue
        if cp.get("label_eligible") is not True:
            late_excluded += 1
            continue
        label = cp.get("directional_label")
        if label not in {"POSITIVE", "NEGATIVE"}:
            continue
        labeled += 1
        if label == "POSITIVE":
            positive += 1
        else:
            negative += 1
        if cp.get("meaningful_wave_20pct") is True:
            meaningful += 1

    gate_met = labeled >= MIN_LABELED_24H and positive >= MIN_POSITIVE_24H and negative >= MIN_NEGATIVE_24H
    return {
        "status": "SAMPLE_MATURE_FOR_MATCHED_REPLAY" if gate_met else "INSUFFICIENT_SAMPLE_FOR_STATISTICAL_CLAIM",
        "descriptive_evaluation_allowed": gate_met,
        "statistical_claim_allowed": False,
        "production_promotion_allowed": False,
        "reason": (
            "Forward sample gate met; next step is matched-cohort replay before any scoring change."
            if gate_met
            else "Forward-only sample must mature naturally before evaluation; thresholds are never loosened to accelerate proof."
        ),
        "labeled_24h": labeled,
        "positive_24h": positive,
        "negative_24h": negative,
        "meaningful_wave_20pct_count": meaningful,
        "late_checkpoint_excluded": late_excluded,
        "gate": {
            "minimum_labeled_24h": MIN_LABELED_24H,
            "minimum_positive_24h": MIN_POSITIVE_24H,
            "minimum_negative_24h": MIN_NEGATIVE_24H,
            "max_checkpoint_delay_minutes": MAX_CHECKPOINT_DELAY_MINUTES,
        },
        "remaining": {
            "labeled_24h": max(0, MIN_LABELED_24H - labeled),
            "positive_24h": max(0, MIN_POSITIVE_24H - positive),
            "negative_24h": max(0, MIN_NEGATIVE_24H - negative),
        },
    }


def run(data_dir: str | Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    radar = _load_json(data_dir / RADAR.name, {})
    state = _load_state(data_dir / STATE.name)
    if not isinstance(radar, dict) or not str(radar.get("mode") or "").startswith("RESEARCH_ONLY_CEX_SPOT_REVIVAL"):
        raise SystemExit("CEX_SPOT_RADAR_MISSING_OR_INVALID")
    if not isinstance(state, dict) or not isinstance(state.get("markets"), dict):
        raise SystemExit("CEX_SPOT_STATE_MISSING_OR_INVALID")

    ledger_path = data_dir / LEDGER.name
    ledger = _load_json(ledger_path, {})
    if not isinstance(ledger, dict) or ledger.get("mode") != MODE:
        ledger = {
            "version": 1,
            "mode": MODE,
            "activation_at": _iso(reference),
            "updated_at": _iso(reference),
            "research_only": True,
            "production_portfolio_impact": "NONE",
            "automatic_buy": False,
            "no_hindsight": True,
            "entries": {},
        }
    activation = _dt(ledger.get("activation_at")) or reference
    entries = ledger.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        ledger["entries"] = entries

    enrolled = 0
    pre_activation_skipped = 0
    invalid_entry_skipped = 0
    shadow_rows = radar.get("shadow_watchlist") if isinstance(radar.get("shadow_watchlist"), list) else []
    for row in shadow_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "")
        event_at, entry_price, _first = _candidate_event(row)
        if not symbol or event_at is None or entry_price is None or entry_price <= 0:
            invalid_entry_skipped += 1
            continue
        if event_at < activation:
            pre_activation_skipped += 1
            continue
        key = _entry_key(symbol, event_at)
        if key not in entries:
            entries[key] = _entry_record(row, event_at, entry_price, reference)
            enrolled += 1

    latest = _latest_usd_like_prices(state)
    observed = 0
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        market = latest.get(str(entry.get("symbol") or ""))
        if market and _observe(entry, market):
            observed += 1

    ledger["updated_at"] = _iso(reference)
    ledger["truth_contract"] = {
        "forward_only_after_activation": True,
        "pre_activation_shadow_candidates_not_backfilled": True,
        "entry_uses_immutable_first_shadow_watch_milestone": True,
        "usd_like_reference_only": True,
        "regional_native_quote_not_coerced_to_usd": True,
        "future_outcomes_never_change_entry": True,
        "late_24h_checkpoints_excluded_from_sample_gate": True,
        "shadow_lane_never_actionable": True,
        "production_scoring_unchanged": True,
    }
    _write(ledger_path, ledger)

    maturity = _sample_maturity(entries)
    report = {
        "version": 1,
        "mode": MODE,
        "generated_at": _iso(reference),
        "activation_at": ledger.get("activation_at"),
        "research_only": True,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "no_hindsight": True,
        "entry_count": len(entries),
        "completed_72h_count": sum(1 for value in entries.values() if isinstance(value, dict) and value.get("completed") is True),
        "enrolled_this_run": enrolled,
        "observed_this_run": observed,
        "pre_activation_shadow_rows_skipped_this_run": pre_activation_skipped,
        "invalid_entry_rows_skipped_this_run": invalid_entry_skipped,
        "sample_maturity": maturity,
        "next_step_when_mature": "RUN_MATCHED_COHORT_DECISION_REPLAY_BEFORE_ANY_SCORE_OR_ALERT_CHANGE",
        "truth_contract": ledger.get("truth_contract"),
    }
    _write(data_dir / REPORT.name, report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
