from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
POSITION_SIZE_USD = 10.0
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


def _num(row: dict[str, Any], *names: str) -> float:
    for name in names:
        try:
            v = float(row.get(name))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return 0.0


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
        if not isinstance(row, dict):
            continue
        if _norm(chain, row.get("pairAddress")) == want:
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
        if key.count(":") >= 2:
            out[key] = row
    return out


def initial_ledger(now: str | None = None) -> dict[str, Any]:
    ts = now or _now()
    return {
        "version": 1,
        "mode": "PAPER_ONLY_NO_REAL_MONEY",
        "rule": "ONLY_NEW_TELEGRAM_DELIVERED_REAL_ALERTS_FROM_ACTIVATION_FORWARD",
        "created_at": ts,
        "updated_at": ts,
        "position_size_usd": POSITION_SIZE_USD,
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

    # Entry truth is the Telegram delivery event itself. This intentionally
    # prevents backfilling historical REAL ALERT cards into the $10 cohort.
    for delivered in list((telegram_report or {}).get("delivered") or []):
        if not isinstance(delivered, dict):
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

        quote = quote_fn(chain, pair)
        live_price, live_liq = _quote_price_liquidity(quote)
        fallback_price = _num(real, "price_usd", "current_price_usd")
        fallback_liq = _num(real, "execution_pool_liquidity_usd", "liquidity_usd")
        entry_price = live_price or fallback_price
        if entry_price <= 0:
            events.append({"at": ts, "type": "ENTRY_SKIPPED", "key": key, "reason": "NO_EXACT_PAIR_PRICE"})
            continue

        sent_at = str(delivered.get("sent_at") or ts)
        quantity = POSITION_SIZE_USD / entry_price
        pos = {
            "key": key,
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
            "entry_time": ts,
            "cost_usd": POSITION_SIZE_USD,
            "entry_price_usd": entry_price,
            "entry_price_source": "DEXSCREENER_EXACT_PAIR_AT_TRACK_START" if live_price > 0 else "REAL_ALERT_EXACT_PAIR_FALLBACK",
            "entry_liquidity_usd": live_liq or fallback_liq,
            "quantity": quantity,
            "current_price_usd": entry_price,
            "current_value_usd": POSITION_SIZE_USD,
            "current_return_pct": 0.0,
            "peak_price_usd": entry_price,
            "peak_return_pct": 0.0,
            "trough_price_usd": entry_price,
            "trough_return_pct": 0.0,
            "last_mark_at": ts,
            "last_liquidity_usd": live_liq or fallback_liq,
            "tracking_rule": "NO_AUTOMATIC_EXIT_TRACK_UNTIL_POLICY_DEFINED",
        }
        positions.append(pos)
        existing[key] = pos
        events.append({"at": ts, "type": "PAPER_BUY_10_USD", "key": key, "entry_price_usd": entry_price, "telegram_sent_at": sent_at})

    # Mark every tracked position on the immutable exact pair only.
    for pos in positions:
        if not isinstance(pos, dict) or pos.get("status") != "ACTIVE_TRACKING":
            continue
        chain = str(pos.get("chain") or "").lower()
        pair = str(pos.get("pair_address") or "")
        quote = quote_fn(chain, pair)
        price, liquidity = _quote_price_liquidity(quote)
        if price <= 0:
            continue
        entry = float(pos.get("entry_price_usd") or 0)
        qty = float(pos.get("quantity") or 0)
        if entry <= 0 or qty <= 0:
            continue
        ret = ((price / entry) - 1.0) * 100.0
        peak_price = max(float(pos.get("peak_price_usd") or entry), price)
        trough_price = min(float(pos.get("trough_price_usd") or entry), price)
        pos.update({
            "current_price_usd": price,
            "current_value_usd": qty * price,
            "current_return_pct": round(ret, 6),
            "peak_price_usd": peak_price,
            "peak_return_pct": round(((peak_price / entry) - 1.0) * 100.0, 6),
            "trough_price_usd": trough_price,
            "trough_return_pct": round(((trough_price / entry) - 1.0) * 100.0, 6),
            "last_mark_at": ts,
            "last_liquidity_usd": liquidity,
        })

    total_cost = sum(float(p.get("cost_usd") or 0) for p in positions if isinstance(p, dict))
    current_value = sum(float(p.get("current_value_usd") or 0) for p in positions if isinstance(p, dict))
    pnl = current_value - total_cost
    roi = (pnl / total_cost * 100.0) if total_cost > 0 else 0.0
    winners = sum(1 for p in positions if float(p.get("current_return_pct") or 0) > 0)
    losers = sum(1 for p in positions if float(p.get("current_return_pct") or 0) < 0)

    ledger.update({"updated_at": ts, "positions": positions, "events": events[-5000:]})
    summary = {
        "version": 1,
        "updated_at": ts,
        "mode": "PAPER_ONLY_NO_REAL_MONEY",
        "position_size_usd": POSITION_SIZE_USD,
        "new_entry_trigger": "SUCCESSFULLY_DELIVERED_NEW_TELEGRAM_REAL_ALERT_ONLY",
        "positions_total": len(positions),
        "paper_cost_usd": round(total_cost, 8),
        "current_value_usd": round(current_value, 8),
        "pnl_usd": round(pnl, 8),
        "roi_pct": round(roi, 6),
        "winners_now": winners,
        "losers_now": losers,
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
        "positions_total": summary["positions_total"],
        "paper_cost_usd": summary["paper_cost_usd"],
        "current_value_usd": summary["current_value_usd"],
        "roi_pct": summary["roi_pct"],
    }, indent=2))


if __name__ == "__main__":
    main()
