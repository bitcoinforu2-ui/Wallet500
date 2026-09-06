from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

SYMBOL = "AOBS"
TOKEN_CA = "0x47366e0f257ac009e82bd46fb74e2fb50826ce98"
NETWORK = "robinhood"
POOL = "0x66afd314846523485d2e9505e46871fa49b8dfe4090d0f48d2580e89412097a9"
UPPER = Decimal("0.00071")
LOWER = Decimal("0.00053")
STATE_PATH = Path(os.environ.get("AOBS_STATE_PATH", "data/aobs-price-watch.json"))
IL_TZ = ZoneInfo("Asia/Jerusalem")
GECKO_URL = f"https://api.geckoterminal.com/api/v2/networks/{NETWORK}/pools/{POOL}"
POOL_URL = f"https://www.geckoterminal.com/{NETWORK}/pools/{POOL}"


def _decimal(value: object) -> Decimal | None:
    try:
        if value is None or value == "":
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _num(value: object) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (ValueError, TypeError):
        return None


def _money(value: object) -> str:
    n = _num(value)
    if n is None:
        return "—"
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n / 1_000:.1f}K"
    if abs(n) >= 1:
        return f"${n:.4f}"
    return f"${n:.10f}".rstrip("0").rstrip(".")


def _pct(value: object) -> str:
    n = _num(value)
    return "—" if n is None else f"{n:+.1f}%"


def _price(value: Decimal) -> str:
    return f"${value:.10f}".rstrip("0").rstrip(".")


def _zone(price: Decimal) -> str:
    if price > UPPER:
        return "ABOVE_UPPER"
    if price < LOWER:
        return "BELOW_LOWER"
    return "MID_RANGE"


def _should_alert(previous_zone: str | None, current_zone: str) -> bool:
    return current_zone in {"ABOVE_UPPER", "BELOW_LOWER"} and previous_zone != current_zone


def _fetch_exact_pool(max_attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(
                GECKO_URL,
                headers={
                    "accept": "application/json",
                    "user-agent": "Wallet500-AOBS-Price-Watch/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.load(response)

            data = payload.get("data") or {}
            attrs = data.get("attributes") or {}
            rel = data.get("relationships") or {}
            base_id = str((((rel.get("base_token") or {}).get("data") or {}).get("id") or "")).lower()
            quote_id = str((((rel.get("quote_token") or {}).get("data") or {}).get("id") or "")).lower()
            ca = TOKEN_CA.lower()

            base_match = base_id == ca or base_id.endswith("_" + ca)
            quote_match = quote_id == ca or quote_id.endswith("_" + ca)
            if not (base_match or quote_match):
                raise RuntimeError(f"AOBS exact CA not present in exact pool relationships: {base_id} / {quote_id}")

            raw_price = attrs.get("base_token_price_usd") if base_match else attrs.get("quote_token_price_usd")
            price = _decimal(raw_price)
            if price is None or price <= 0:
                raise RuntimeError("Exact pool returned no valid AOBS USD price")

            tx = attrs.get("transactions") or {}
            pc = attrs.get("price_change_percentage") or {}
            vol = attrs.get("volume_usd") or {}
            h1_tx = tx.get("h1") or {}
            return {
                "price": price,
                "liquidity_usd": attrs.get("reserve_in_usd"),
                "volume_h1_usd": vol.get("h1"),
                "volume_h24_usd": vol.get("h24"),
                "price_change_m5": pc.get("m5"),
                "price_change_h1": pc.get("h1"),
                "price_change_h6": pc.get("h6"),
                "price_change_h24": pc.get("h24"),
                "buys_h1": h1_tx.get("buys"),
                "sells_h1": h1_tx.get("sells"),
                "source": "GECKOTERMINAL_EXACT_POOL",
                "source_url": GECKO_URL,
                "pool_url": POOL_URL,
            }
        except Exception as exc:  # network errors are retried, truth errors still fail closed after retries
            last_error = exc
            if attempt < max_attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"AOBS exact-pair market fetch failed: {last_error}")


def _load_state() -> dict:
    try:
        if STATE_PATH.exists() and STATE_PATH.stat().st_size:
            value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets are not configured")
    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Wallet500-AOBS/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rejected AOBS alert: {str(payload)[:300]}")


def _message(market: dict, zone: str, observed_at: datetime) -> str:
    price: Decimal = market["price"]
    if zone == "ABOVE_UPPER":
        icon = "📈"
        headline = f"פריצה מעל {_price(UPPER)}"
        distance = (price / UPPER - Decimal("1")) * Decimal("100")
        meaning = (
            "המחיר עבר את רמת האישור לסטאפ הקצר. זה מחזק מומנטום, אבל חשוב לראות החזקה מעל הרמה ולא רק wick; "
            "חזרה מהירה מתחתיה נחשבת פריצה כושלת."
        )
        distance_text = f"{float(distance):+.2f}% מעל הסף"
    else:
        icon = "📉"
        headline = f"שבירה מתחת {_price(LOWER)}"
        distance = (price / LOWER - Decimal("1")) * Decimal("100")
        meaning = (
            "המחיר איבד את רמת ההגנה של הסטאפ הקצר. זה מחליש משמעותית את מבנה הסקאלפ ומעלה סיכון להמשך ירידה; "
            "חזרה מהירה מעל הרמה תיחשב reclaim שדורש אימות נוסף."
        )
        distance_text = f"{float(distance):+.2f}% ביחס לסף"

    il_time = observed_at.astimezone(IL_TZ).strftime("%d/%m/%Y %H:%M:%S IL")
    buys = market.get("buys_h1")
    sells = market.get("sells_h1")
    flow = "—" if buys is None and sells is None else f"{buys if buys is not None else '—'} / {sells if sells is not None else '—'}"
    return "\n".join(
        [
            f"🚨 AOBS · LIVE PRICE ALERT",
            f"{icon} {headline}",
            f"💰 מחיר חי: {_price(price)} | {distance_text}",
            f"⏱ שינוי: 5m {_pct(market.get('price_change_m5'))} | 1H {_pct(market.get('price_change_h1'))} | 24H {_pct(market.get('price_change_h24'))}",
            f"💧 נזילות exact pool: {_money(market.get('liquidity_usd'))}",
            f"📊 Volume: 1H {_money(market.get('volume_h1_usd'))} | 24H {_money(market.get('volume_h24_usd'))}",
            f"🟢/🔴 עסקאות 1H — buys / sells: {flow}",
            f"🧠 פירוש: {meaning}",
            f"🔒 Identity locked: {TOKEN_CA}",
            f"🕒 {il_time}",
            "⚠️ התראת מעקב בלבד — לא הוראת קנייה/מכירה.",
            f"🔗 {market['pool_url']}",
        ]
    )[:3900]


def _save_state(previous: dict, market: dict, zone: str, observed_at: datetime, alert_sent: bool) -> dict:
    state = {
        "version": 1,
        "symbol": SYMBOL,
        "network": NETWORK,
        "token_address": TOKEN_CA,
        "pool_address": POOL,
        "upper_threshold": str(UPPER),
        "lower_threshold": str(LOWER),
        "zone": zone,
        "price_usd": str(market["price"]),
        "observed_at": observed_at.isoformat(),
        "source": market.get("source"),
        "source_url": market.get("source_url"),
        "pool_url": market.get("pool_url"),
        "last_alert_zone": previous.get("last_alert_zone"),
        "last_alert_at": previous.get("last_alert_at"),
    }
    if alert_sent:
        state["last_alert_zone"] = zone
        state["last_alert_at"] = observed_at.isoformat()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def run() -> dict:
    previous = _load_state()
    previous_zone = str(previous.get("zone") or "").strip() or None
    market = _fetch_exact_pool()
    price: Decimal = market["price"]
    current_zone = _zone(price)
    observed_at = datetime.now(timezone.utc)
    alert = _should_alert(previous_zone, current_zone)

    if alert:
        _send_telegram(_message(market, current_zone, observed_at))

    state = _save_state(previous, market, current_zone, observed_at, alert)
    result = {
        "price_usd": str(price),
        "previous_zone": previous_zone,
        "current_zone": current_zone,
        "alert_sent": alert,
        "observed_at": observed_at.isoformat(),
        "state": state,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def self_test() -> None:
    assert _zone(Decimal("0.000711")) == "ABOVE_UPPER"
    assert _zone(Decimal("0.000710")) == "MID_RANGE"
    assert _zone(Decimal("0.000600")) == "MID_RANGE"
    assert _zone(Decimal("0.000530")) == "MID_RANGE"
    assert _zone(Decimal("0.000529")) == "BELOW_LOWER"
    assert _should_alert(None, "ABOVE_UPPER") is True
    assert _should_alert(None, "MID_RANGE") is False
    assert _should_alert("MID_RANGE", "ABOVE_UPPER") is True
    assert _should_alert("ABOVE_UPPER", "ABOVE_UPPER") is False
    assert _should_alert("ABOVE_UPPER", "MID_RANGE") is False
    assert _should_alert("MID_RANGE", "BELOW_LOWER") is True
    assert _should_alert("BELOW_LOWER", "BELOW_LOWER") is False
    print("AOBS price-watch self-test: OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        run()


if __name__ == "__main__":
    main()
