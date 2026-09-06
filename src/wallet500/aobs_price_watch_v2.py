from __future__ import annotations

import argparse
from decimal import Decimal

import aobs_price_watch as base

EXTREME_ZONES = {"ABOVE_UPPER", "BELOW_LOWER"}


def _should_alert(previous_zone: str | None, current_zone: str) -> bool:
    """Alert on threshold entry and on a meaningful return to the mid-range."""
    if current_zone in EXTREME_ZONES:
        return previous_zone != current_zone
    return current_zone == "MID_RANGE" and previous_zone in EXTREME_ZONES


def _signal_state(previous_zone: str | None, current_zone: str) -> tuple[str, str, str, str]:
    if current_zone == "ABOVE_UPPER":
        return (
            "🟢 BUY SETUP",
            f"פריצה מעל {base._price(base.UPPER)}",
            "מועמד לכניסה רק אחרי אישור שהמחיר מחזיק מעל הרמה; לא לרדוף אחרי wick בודד.",
            "אישור רצוי: החזקה מעל הסף + נפח/קניות שלא נחלשים. חזרה מהירה מתחת לסף = WAIT / פריצה כושלת.",
        )
    if current_zone == "BELOW_LOWER":
        return (
            "🔴 DANGER",
            f"שבירה מתחת {base._price(base.LOWER)}",
            "לא סטאפ קנייה כרגע. לא לתפוס סכין נופלת; המבנה הקצר נחלש.",
            "הסטאפ יכול להשתפר רק אם המחיר חוזר מעל הסף ומחזיק אותו מחדש (reclaim).",
        )
    if previous_zone == "BELOW_LOWER":
        return (
            "🟡 WAIT · REVERSAL WATCH",
            f"Reclaim מעל {base._price(base.LOWER)}",
            "יש התאוששות ראשונית, אבל עדיין לא BUY SETUP. מחכים לאישור שהחזרה לטווח מחזיקה.",
            f"אם ההחזקה מתבססת, היעד הבא למעקב הוא אזור הפריצה {base._price(base.UPPER)}.",
        )
    return (
        "🟡 WAIT · FAILED BREAKOUT WATCH",
        f"חזרה מתחת {base._price(base.UPPER)}",
        "הפריצה לא החזיקה. לא לרדוף אחרי המחיר; מחכים למבנה חדש או לפריצה חוזרת מאושרת.",
        "פריצה חוזרת מעל הסף עם החזקה ונפח תחזיר את המצב ל-BUY SETUP.",
    )


def _message(market: dict, zone: str, observed_at) -> str:
    previous = base._load_state()
    previous_zone = str(previous.get("zone") or "").strip() or None
    state, headline, action, explanation = _signal_state(previous_zone, zone)
    price: Decimal = market["price"]

    if zone == "ABOVE_UPPER":
        distance = (price / base.UPPER - Decimal("1")) * Decimal("100")
        distance_text = f"{float(distance):+.2f}% מעל 0.00071"
    elif zone == "BELOW_LOWER":
        distance = (price / base.LOWER - Decimal("1")) * Decimal("100")
        distance_text = f"{float(distance):+.2f}% ביחס ל-0.00053"
    else:
        distance_text = "חזרה לטווח 0.00053–0.00071"

    il_time = observed_at.astimezone(base.IL_TZ).strftime("%d/%m/%Y %H:%M:%S IL")
    buys = market.get("buys_h1")
    sells = market.get("sells_h1")
    flow = "—" if buys is None and sells is None else f"{buys if buys is not None else '—'} / {sells if sells is not None else '—'}"

    return "\n".join(
        [
            "🚨 AOBS · LIVE TRADING SETUP ALERT",
            f"{state}",
            f"📍 {headline}",
            f"💰 מחיר חי: {base._price(price)} | {distance_text}",
            f"🎯 פעולה: {action}",
            f"🧠 למה: {explanation}",
            f"⏱ שינוי: 5m {base._pct(market.get('price_change_m5'))} | 1H {base._pct(market.get('price_change_h1'))} | 24H {base._pct(market.get('price_change_h24'))}",
            f"💧 נזילות exact pool: {base._money(market.get('liquidity_usd'))}",
            f"📊 Volume: 1H {base._money(market.get('volume_h1_usd'))} | 24H {base._money(market.get('volume_h24_usd'))}",
            f"🟢/🔴 עסקאות 1H — buys / sells: {flow}",
            f"🔒 Identity locked: {base.TOKEN_CA}",
            f"🕒 {il_time}",
            "⚠️ BUY SETUP הוא סטאפ למעקב ולא הוראת קנייה; יש לאמת מחיר/נזילות בזמן הביצוע.",
            f"🔗 {market['pool_url']}",
        ]
    )[:3900]


def self_test() -> None:
    assert _should_alert(None, "MID_RANGE") is False
    assert _should_alert("MID_RANGE", "ABOVE_UPPER") is True
    assert _should_alert("ABOVE_UPPER", "ABOVE_UPPER") is False
    assert _should_alert("ABOVE_UPPER", "MID_RANGE") is True
    assert _should_alert("MID_RANGE", "BELOW_LOWER") is True
    assert _should_alert("BELOW_LOWER", "BELOW_LOWER") is False
    assert _should_alert("BELOW_LOWER", "MID_RANGE") is True
    assert _signal_state("MID_RANGE", "ABOVE_UPPER")[0] == "🟢 BUY SETUP"
    assert _signal_state("MID_RANGE", "BELOW_LOWER")[0] == "🔴 DANGER"
    assert _signal_state("BELOW_LOWER", "MID_RANGE")[0].startswith("🟡 WAIT")
    assert _signal_state("ABOVE_UPPER", "MID_RANGE")[0].startswith("🟡 WAIT")
    print("AOBS signal-watch v2 self-test: OK")


def run() -> dict:
    base._should_alert = _should_alert
    base._message = _message
    return base.run()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        base.self_test()
        self_test()
    else:
        run()


if __name__ == "__main__":
    main()
