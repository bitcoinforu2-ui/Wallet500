from __future__ import annotations

import json
import os
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SYMBOL = "LSK"
ENTRY_PRICE_USD = 0.47
WARN_DOWN_PCT = -5.0
CRITICAL_DOWN_PCT = -8.0
WARN_UP_PCT = 8.0
EXTREME_DISLOCATION_PCT = 15.0
MIN_HEALTHY_VENUES = 3
TIMEOUT_SECONDS = 8
STATE_PATH = Path("data/lsk-cross-exchange-watch-state.json")
REPORT_PATH = Path("data/lsk-cross-exchange-watch.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
        return json.loads(r.read().decode("utf-8"))


def _f(value):
    try:
        x = float(value)
        return x if x > 0 else None
    except Exception:
        return None


def fetch_prices() -> tuple[dict, dict]:
    prices: dict[str, float] = {}
    errors: dict[str, str] = {}
    sources = {
        "OKX": lambda: _f(_get_json("https://www.okx.com/api/v5/market/ticker?instId=LSK-USDT")["data"][0]["last"]),
        "KUCOIN": lambda: _f(_get_json("https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=LSK-USDT")["data"]["price"]),
        "MEXC": lambda: _f(_get_json("https://api.mexc.com/api/v3/ticker/bookTicker?symbol=LSKUSDT")["bidPrice"]),
        "GATE": lambda: _f(_get_json("https://api.gateio.ws/api/v4/spot/tickers?currency_pair=LSK_USDT")[0]["last"]),
    }
    for name, fn in sources.items():
        try:
            p = fn()
            if p is None:
                raise ValueError("missing_or_zero_price")
            prices[name] = p
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}:{exc}"[:220]
    return prices, errors


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _send_telegram(text: str) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"sent": False, "reason": "TELEGRAM_SECRETS_MISSING"}
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
            payload = json.loads(r.read().decode("utf-8"))
        return {"sent": bool(payload.get("ok")), "reason": "OK" if payload.get("ok") else "TELEGRAM_API_REJECTED"}
    except Exception as exc:
        return {"sent": False, "reason": f"TELEGRAM_ERROR:{type(exc).__name__}"}


def run() -> dict:
    observed_at = _now()
    prices, errors = fetch_prices()
    healthy = len(prices)
    median_price = statistics.median(prices.values()) if healthy else None
    rows = []
    if median_price:
        for venue, price in sorted(prices.items()):
            gap = (price / median_price - 1.0) * 100.0
            rows.append({"venue": venue, "price_usd": round(price, 12), "gap_vs_median_pct": round(gap, 4)})

    downside = [r for r in rows if r["gap_vs_median_pct"] <= WARN_DOWN_PCT]
    upside = [r for r in rows if r["gap_vs_median_pct"] >= WARN_UP_PCT]
    strongest_down = min(downside, key=lambda r: r["gap_vs_median_pct"], default=None)
    strongest_up = max(upside, key=lambda r: r["gap_vs_median_pct"], default=None)

    if healthy < MIN_HEALTHY_VENUES:
        status = "INSUFFICIENT_CROSS_EXCHANGE_COVERAGE"
    elif strongest_down and strongest_down["gap_vs_median_pct"] <= CRITICAL_DOWN_PCT:
        status = "CRITICAL_DOWNSIDE_LEAD"
    elif strongest_down:
        status = "EARLY_DOWNSIDE_LEAD"
    elif strongest_up:
        status = "UPSIDE_LEAD"
    else:
        status = "NO_MATERIAL_DISLOCATION"

    max_abs_gap = max((abs(r["gap_vs_median_pct"]) for r in rows), default=0.0)
    glitch_risk = max_abs_gap >= 50.0
    alert = status in {"CRITICAL_DOWNSIDE_LEAD", "EARLY_DOWNSIDE_LEAD", "UPSIDE_LEAD"}
    signature = json.dumps({
        "status": status,
        "down": strongest_down["venue"] if strongest_down else None,
        "up": strongest_up["venue"] if strongest_up else None,
        "bucket": int(max_abs_gap // 5),
        "glitch_risk": glitch_risk,
    }, sort_keys=True)

    previous = _load_state()
    previous_signature = previous.get("active_signature")
    should_notify = alert and signature != previous_signature

    telegram = {"sent": False, "reason": "NO_NEW_ALERT"}
    if should_notify:
        lines = [
            "🚨 Wallet500 LSK Cross-Exchange",
            f"Status: {status}",
            f"Median: ${median_price:.6f}" if median_price else "Median: n/a",
            f"Your entry: ${ENTRY_PRICE_USD:.4f}",
        ]
        if strongest_down:
            lines.append(f"⚠️ Lead down: {strongest_down['venue']} ${strongest_down['price_usd']:.6f} ({strongest_down['gap_vs_median_pct']:+.2f}% vs median)")
        if strongest_up:
            lines.append(f"🚀 Lead up: {strongest_up['venue']} ${strongest_up['price_usd']:.6f} ({strongest_up['gap_vs_median_pct']:+.2f}% vs median)")
        lines.append("Venues: " + " | ".join(f"{r['venue']} ${r['price_usd']:.6f} ({r['gap_vs_median_pct']:+.1f}%)" for r in rows))
        if glitch_risk:
            lines.append("⚠️ UNVERIFIED_GLITCH_RISK: extreme single-venue gap; do not assume executable arbitrage without order-book/network verification.")
        elif status in {"CRITICAL_DOWNSIDE_LEAD", "EARLY_DOWNSIDE_LEAD"}:
            lines.append("Risk note: another venue is leading lower. Check your exchange immediately; this is an early-warning signal, not an automatic sell.")
        else:
            lines.append("Opportunity note: another venue is leading higher. Check whether the move propagates; not an automatic buy/sell.")
        lines.append(f"Observed: {observed_at}")
        telegram = _send_telegram("\n".join(lines))

    new_signature = signature if alert else None
    state = {
        "version": 1,
        "updated_at": observed_at,
        "symbol": SYMBOL,
        "active_signature": new_signature,
        "last_status": status,
        "last_alert_at": observed_at if should_notify and telegram.get("sent") else previous.get("last_alert_at"),
        "last_alert_signature": signature if should_notify and telegram.get("sent") else previous.get("last_alert_signature"),
    }
    if previous.get("active_signature") != state["active_signature"] or (should_notify and telegram.get("sent")):
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    report = {
        "version": 1,
        "generated_at": observed_at,
        "mode": "LIVE_LSK_CROSS_EXCHANGE_EARLY_WARNING_V1",
        "symbol": SYMBOL,
        "entry_price_usd": ENTRY_PRICE_USD,
        "status": status,
        "healthy_venues": healthy,
        "minimum_healthy_venues": MIN_HEALTHY_VENUES,
        "median_price_usd": round(median_price, 12) if median_price else None,
        "venues": rows,
        "source_errors": errors,
        "downside_leader": strongest_down,
        "upside_leader": strongest_up,
        "glitch_risk": glitch_risk,
        "alert_condition": alert,
        "new_alert": should_notify,
        "telegram": telegram,
        "automatic_sell": False,
        "automatic_buy": False,
        "automatic_transfer": False,
        "truth_contract": {
            "cross_exchange_median_requires_multiple_live_sources": True,
            "single_venue_extreme_move_is_not_proof_of_executable_price": True,
            "no_automatic_trading": True,
        },
        "thresholds": {
            "early_downside_gap_pct": WARN_DOWN_PCT,
            "critical_downside_gap_pct": CRITICAL_DOWN_PCT,
            "upside_gap_pct": WARN_UP_PCT,
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
