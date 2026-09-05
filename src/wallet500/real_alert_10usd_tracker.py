from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
POSITION_SIZE_USD = 10.0
ACTIVATION_AT = "2026-09-05T14:47:25+00:00"
CHECKPOINTS = (
    (15, "15m"),
    (60, "1h"),
    (240, "4h"),
    (1440, "24h"),
    (4320, "72h"),
    (10080, "7d"),
)
LEDGER_PATH = DATA / "real-alert-10usd-ledger.json"
SUMMARY_PATH = DATA / "real-alert-10usd-summary.json"
TELEGRAM_REPORT_PATH = DATA / "telegram-alert-report.json"
REAL_ALERTS_PATH = DATA / "real-alerts.json"
UA = {"User-Agent": "Wallet500/2.0", "Accept": "application/json"}
EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _norm(chain: str, value: object) -> str:
    s = str(value or "").strip()
    return s.lower() if chain.lower() in EVM else s


def _key(chain: object, token: object, pair: object) -> str:
    c = str(chain or "").strip().lower()
    return f"{c}:{_norm(c, token)}:{_norm(c, pair)}"


def _event_id(key: str, sent_at: str) -> str:
    return hashlib.sha256(f"{key}|{sent_at}".encode("utf-8")).hexdigest()[:16]


def _num(row: dict[str, Any], *names: str) -> float:
    for name in names:
        try:
            v = float(row.get(name))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return 0.0


def _parse_ts(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def _after_activation(value: object) -> bool:
    sent = _parse_ts(value)
    cutoff = _parse_ts(ACTIVATION_AT)
    return bool(sent and cutoff and sent >= cutoff)


def _elapsed_minutes(start: object, end: object) -> float | None:
    a = _parse_ts(start)
    b = _parse_ts(end)
    if not a or not b or b < a:
        return None
    return (b - a).total_seconds() / 60.0


def _http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _dex_chain(chain: str) -> str:
    c = chain.lower()
    return {"bnb": "bsc", "eth": "ethereum"}.get(c, c)


def _pair_quote(chain: str, pair: str) -> dict[str, Any] | None:
    if not chain or not pair:
        return None
    try:
        payload = _http_json(f"https://api.dexscreener.com/latest/dex/pairs/{_dex_chain(chain)}/{pair}")
    except Exception:
        return None
    rows = payload.get("pairs") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    want = _norm(chain, pair)
    for row in rows:
        if isinstance(row, dict) and _norm(chain, row.get("pairAddress")) == want:
            return row
    return None


def _quote_price_liquidity(row: dict[str, Any] | None) -> tuple[float, float]:
    if not isinstance(row, dict):
        return 0.0, 0.0
    try:
        price = float(row.get("priceUsd") or 0)
    except (TypeError, ValueError):
        price = 0.0
    liq = row.get("liquidity") if isinstance(row.get("liquidity"), dict) else {}
    try:
        liquidity = float(liq.get("usd") or 0)
    except (TypeError, ValueError):
        liquidity = 0.0
    return price if price > 0 else 0.0, liquidity if liquidity >= 0 else 0.0


def _real_index(payload: Any) -> dict[str, dict[str, Any]]:
    rows = payload.get("alerts") if isinstance(payload, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = _key(row.get("chain"), row.get("token_address") or row.get("token"), row.get("pair_address"))
        out[key] = row
    return out


def _capture_checkpoints(pos: dict[str, Any], ts: str, price: float, liquidity: float) -> None:
    elapsed = _elapsed_minutes(pos.get("telegram_sent_at"), ts)
    entry = float(pos.get("entry_price_usd") or 0)
    qty = float(pos.get("quantity") or 0)
    if elapsed is None or entry <= 0 or qty <= 0 or price <= 0:
        return
    checkpoints = dict(pos.get("checkpoints") or {})
    ret = ((price / entry) - 1.0) * 100.0
    for target_minutes, label in CHECKPOINTS:
        if elapsed < target_minutes or label in checkpoints:
            continue
        checkpoints[label] = {
            "target_minutes": target_minutes,
            "captured_at": ts,
            "captured_elapsed_minutes": round(elapsed, 3),
            "price_usd": price,
            "value_usd": round(qty * price, 8),
            "return_pct": round(ret, 6),
            "liquidity_usd": liquidity,
            "capture_rule": "FIRST_OBSERVED_EXACT_PAIR_MARK_AT_OR_AFTER_HORIZON",
        }
    pos["checkpoints"] = checkpoints


def initial_ledger(now: str | None = None) -> dict[str, Any]:
    ts = now or _now()
    return {
        "version": 3,
        "mode": "PAPER_ONLY_NO_REAL_MONEY",
        "activation_at": ACTIVATION_AT,
        "rule": "ONLY_NEW_TELEGRAM_DELIVERED_REAL_ALERTS_FROM_ACTIVATION_FORWARD",
        "created_at": ts,
        "updated_at": ts,
        "position_size_usd": POSITION_SIZE_USD,
        "checkpoint_horizons": [label for _, label in CHECKPOINTS],
        "positions": [],
        "events": [],
    }


def reconcile(
    ledger: dict[str, Any],
    telegram_report: dict[str, Any],
    real_payload: dict[str, Any],
    now: str | None = None,
    quote_fn=_pair_quote,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = now or _now()
    ledger = dict(ledger or initial_ledger(ts))
    positions = list(ledger.get("positions") or [])
    events = list(ledger.get("events") or [])
    existing = {str(p.get("key")): p for p in positions if isinstance(p, dict) and p.get("key")}
    real_index = _real_index(real_payload)

    # Entry truth is a Telegram delivery after the explicit activation cutoff.
    # Historical REAL ALERT cards are never backfilled into this cohort.
    for delivered in list((telegram_report or {}).get("delivered") or []):
        if not isinstance(delivered, dict):
            continue
        sent_at = str(delivered.get("sent_at") or "")
        if not _after_activation(sent_at):
            continue
        key = str(delivered.get("key") or "")
        if not key or key in existing:
            continue
        real = real_index.get(key)
        if not isinstance(real, dict) or real.get("status") != "REAL_ALERT":
            continue
        chain = str(real.get("chain") or "").lower()
        token = str(real.get("token_address") or real.get("token") or "")
        pair = str(real.get("pair_address") or "")
        if not chain or not token or not pair:
            continue

        # The REAL ALERT price belongs to the same verified snapshot that emitted
        # Telegram, so it is the canonical paper-entry price. Live DEX is fallback.
        alert_price = _num(real, "price_usd", "current_price_usd")
        alert_liq = _num(real, "execution_pool_liquidity_usd", "liquidity_usd")
        quote = quote_fn(chain, pair)
        live_price, live_liq = _quote_price_liquidity(quote)
        entry_price = alert_price or live_price
        if entry_price <= 0:
            events.append({"at": ts, "type": "ENTRY_SKIPPED", "key": key, "reason": "NO_EXACT_PAIR_PRICE"})
            continue

        quantity = POSITION_SIZE_USD / entry_price
        current_price = live_price or entry_price
        current_ret = ((current_price / entry_price) - 1.0) * 100.0
        event_id = _event_id(key, sent_at)
        pos = {
            "key": key,
            "alert_event_id": event_id,
            "symbol": delivered.get("symbol") or real.get("symbol"),
            "chain": chain,
            "token_address": token,
            "pair_address": pair,
            "dex": real.get("dex"),
            "dex_url": delivered.get("dex_url") or real.get("dex_url"),
            "status": "ACTIVE_TRACKING",
            "paper_only": True,
            "telegram_sent_at": sent_at,
            "telegram_sent_at_israel": delivered.get("sent_at_israel"),
            "original_signal_t0": real.get("first_alert_at"),
            "entry_time": sent_at,
            "tracker_started_at": ts,
            "cost_usd": POSITION_SIZE_USD,
            "entry_price_usd": entry_price,
            "entry_price_source": "REAL_ALERT_PRICE_AT_TELEGRAM_SCAN" if alert_price > 0 else "DEXSCREENER_EXACT_PAIR_FALLBACK",
            "entry_liquidity_usd": alert_liq or live_liq,
            "entry_score": real.get("score"),
            "entry_market_age_days": real.get("market_age_days"),
            "entry_source_lanes": list(real.get("source_lanes") or []),
            "entry_evidence_status": real.get("evidence_envelope_status"),
            "entry_positive_evidence": list(real.get("evidence_positive_lanes") or []),
            "entry_verified_evidence": list(real.get("evidence_verified_lanes") or []),
            "quantity": quantity,
            "current_price_usd": current_price,
            "current_value_usd": quantity * current_price,
            "current_return_pct": round(current_ret, 6),
            "current_multiple": round(current_price / entry_price, 8),
            "peak_price_usd": max(entry_price, current_price),
            "peak_return_pct": round(((max(entry_price, current_price) / entry_price) - 1.0) * 100.0, 6),
            "trough_price_usd": min(entry_price, current_price),
            "trough_return_pct": round(((min(entry_price, current_price) / entry_price) - 1.0) * 100.0, 6),
            "drawdown_from_peak_pct": round(((current_price / max(entry_price, current_price)) - 1.0) * 100.0, 6),
            "last_mark_at": ts,
            "last_mark_attempt_at": ts,
            "missed_mark_count": 0,
            "last_liquidity_usd": live_liq or alert_liq,
            "checkpoints": {},
            "tracking_rule": "NO_AUTOMATIC_EXIT_TRACK_UNTIL_POLICY_DEFINED",
        }
        _capture_checkpoints(pos, ts, current_price, live_liq or alert_liq)
        positions.append(pos)
        existing[key] = pos
        events.append({
            "at": ts,
            "type": "PAPER_BUY_10_USD",
            "key": key,
            "alert_event_id": event_id,
            "entry_price_usd": entry_price,
            "telegram_sent_at": sent_at,
        })

    # Mark every tracked position on the immutable exact pair only.
    for pos in positions:
        if not isinstance(pos, dict) or pos.get("status") != "ACTIVE_TRACKING":
            continue
        pos["last_mark_attempt_at"] = ts
        chain = str(pos.get("chain") or "").lower()
        pair = str(pos.get("pair_address") or "")
        quote = quote_fn(chain, pair)
        price, liquidity = _quote_price_liquidity(quote)
        if price <= 0:
            pos["missed_mark_count"] = int(pos.get("missed_mark_count") or 0) + 1
            continue
        entry = float(pos.get("entry_price_usd") or 0)
        qty = float(pos.get("quantity") or 0)
        if entry <= 0 or qty <= 0:
            continue
        ret = ((price / entry) - 1.0) * 100.0
        peak_price = max(float(pos.get("peak_price_usd") or entry), price)
        trough_price = min(float(pos.get("trough_price_usd") or entry), price)
        drawdown = ((price / peak_price) - 1.0) * 100.0 if peak_price > 0 else 0.0
        pos.update({
            "current_price_usd": price,
            "current_value_usd": qty * price,
            "current_return_pct": round(ret, 6),
            "current_multiple": round(price / entry, 8),
            "peak_price_usd": peak_price,
            "peak_return_pct": round(((peak_price / entry) - 1.0) * 100.0, 6),
            "trough_price_usd": trough_price,
            "trough_return_pct": round(((trough_price / entry) - 1.0) * 100.0, 6),
            "drawdown_from_peak_pct": round(drawdown, 6),
            "last_mark_at": ts,
            "last_liquidity_usd": liquidity,
        })
        _capture_checkpoints(pos, ts, price, liquidity)

    total_cost = sum(float(p.get("cost_usd") or 0) for p in positions if isinstance(p, dict))
    current_value = sum(float(p.get("current_value_usd") or 0) for p in positions if isinstance(p, dict))
    pnl = current_value - total_cost
    roi = (pnl / total_cost * 100.0) if total_cost > 0 else 0.0
    current_returns = [float(p.get("current_return_pct") or 0) for p in positions if isinstance(p, dict)]
    peak_returns = [float(p.get("peak_return_pct") or 0) for p in positions if isinstance(p, dict)]
    winners = sum(1 for r in current_returns if r > 0)
    losers = sum(1 for r in current_returns if r < 0)
    doubled = sum(1 for r in peak_returns if r >= 100.0)
    up_50 = sum(1 for r in peak_returns if r >= 50.0)

    ledger.update({
        "version": 3,
        "activation_at": ACTIVATION_AT,
        "updated_at": ts,
        "checkpoint_horizons": [label for _, label in CHECKPOINTS],
        "positions": positions,
        "events": events[-5000:],
    })
    summary = {
        "version": 3,
        "updated_at": ts,
        "mode": "PAPER_ONLY_NO_REAL_MONEY",
        "activation_at": ACTIVATION_AT,
        "position_size_usd": POSITION_SIZE_USD,
        "new_entry_trigger": "SUCCESSFULLY_DELIVERED_NEW_TELEGRAM_REAL_ALERT_AFTER_ACTIVATION_ONLY",
        "positions_total": len(positions),
        "paper_cost_usd": round(total_cost, 8),
        "current_value_usd": round(current_value, 8),
        "pnl_usd": round(pnl, 8),
        "roi_pct": round(roi, 6),
        "winners_now": winners,
        "losers_now": losers,
        "best_current_return_pct": round(max(current_returns), 6) if current_returns else 0.0,
        "worst_current_return_pct": round(min(current_returns), 6) if current_returns else 0.0,
        "best_peak_return_pct": round(max(peak_returns), 6) if peak_returns else 0.0,
        "positions_peak_ge_50pct": up_50,
        "positions_peak_ge_100pct": doubled,
        "checkpoint_horizons": [label for _, label in CHECKPOINTS],
        "tracking_policy": "track exact pair continuously; no automatic sell is defined",
        "positions": positions,
    }
    return ledger, summary


def main() -> None:
    ledger = _read(LEDGER_PATH, initial_ledger())
    telegram_report = _read(TELEGRAM_REPORT_PATH, {})
    real_payload = _read(REAL_ALERTS_PATH, {})
    ledger, summary = reconcile(ledger, telegram_report, real_payload)
    _write(LEDGER_PATH, ledger)
    _write(SUMMARY_PATH, summary)
    print(json.dumps({
        "mode": summary["mode"],
        "activation_at": summary["activation_at"],
        "positions_total": summary["positions_total"],
        "paper_cost_usd": summary["paper_cost_usd"],
        "current_value_usd": summary["current_value_usd"],
        "roi_pct": summary["roi_pct"],
        "positions_peak_ge_100pct": summary["positions_peak_ge_100pct"],
    }, indent=2))


if __name__ == "__main__":
    main()
