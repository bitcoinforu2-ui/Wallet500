from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import aobs_price_watch as base

EXTREME_ZONES = {"ABOVE_UPPER", "BELOW_LOWER"}
BLOCKSCOUT_ROOT = "https://robinhoodchain.blockscout.com"
HOLDER_COUNTERS_URL = f"{BLOCKSCOUT_ROOT}/api/v2/tokens/{base.TOKEN_CA}/counters"
HOLDER_INFO_URL = f"{BLOCKSCOUT_ROOT}/api/v2/tokens/{base.TOKEN_CA}"
HOLDER_HISTORY_HOURS = 8

_ORIGINAL_FETCH_EXACT_POOL = base._fetch_exact_pool
_ORIGINAL_SAVE_STATE = base._save_state


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


def _parse_ts(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _holder_count(value: object) -> int | None:
    try:
        count = int(str(value).replace(",", ""))
        return count if count >= 0 else None
    except (TypeError, ValueError):
        return None


def _fetch_verified_holder_count(max_attempts: int = 3) -> tuple[int | None, str | None, str | None]:
    """Fetch exact-contract holder count. Failure never blocks the price alert path."""
    errors: list[str] = []
    endpoints = (
        (HOLDER_COUNTERS_URL, "token_holders_count", False),
        (HOLDER_INFO_URL, "holders_count", True),
    )
    for url, field, verify_identity in endpoints:
        for attempt in range(1, max_attempts + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "accept": "application/json",
                        "user-agent": "Wallet500-AOBS-Holder-Velocity/1.0",
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise RuntimeError("Blockscout payload is not an object")
                if verify_identity:
                    address = str(payload.get("address_hash") or "").lower()
                    if address and address != base.TOKEN_CA.lower():
                        raise RuntimeError(f"Blockscout exact CA mismatch: {address}")
                count = _holder_count(payload.get(field))
                if count is None:
                    raise RuntimeError(f"Blockscout missing valid {field}")
                return count, url, None
            except Exception as exc:
                errors.append(f"{field}:{str(exc)[:120]}")
                if attempt < max_attempts:
                    time.sleep(attempt)
    return None, None, " | ".join(errors[-4:])[:500]


def _clean_holder_history(raw: object, now: datetime | None = None) -> list[dict]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(hours=HOLDER_HISTORY_HOURS)
    cleaned: list[tuple[datetime, int]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            ts = _parse_ts(item.get("observed_at"))
            count = _holder_count(item.get("holders"))
            if ts is None or count is None or ts < cutoff or ts > now + timedelta(minutes=2):
                continue
            cleaned.append((ts, count))
    cleaned.sort(key=lambda x: x[0])
    return [{"observed_at": ts.isoformat(), "holders": count} for ts, count in cleaned]


def _nearest_reference(
    history: list[dict],
    now: datetime,
    target_minutes: int,
    tolerance_minutes: int,
) -> tuple[int | None, float | None]:
    target = now - timedelta(minutes=target_minutes)
    candidates: list[tuple[float, datetime, int]] = []
    for item in history:
        ts = _parse_ts(item.get("observed_at"))
        count = _holder_count(item.get("holders"))
        if ts is None or count is None or ts >= now:
            continue
        distance = abs((ts - target).total_seconds())
        if distance <= tolerance_minutes * 60:
            candidates.append((distance, ts, count))
    if not candidates:
        return None, None
    _, ts, count = min(candidates, key=lambda x: x[0])
    age_minutes = (now - ts).total_seconds() / 60
    return count, age_minutes


def _holder_deltas(history: list[dict], current: int | None, now: datetime) -> dict:
    result: dict[str, object] = {}
    specs = {
        "5m": (5, 4),
        "1h": (60, 15),
        "6h": (360, 35),
    }
    for label, (minutes, tolerance) in specs.items():
        reference, actual_age = _nearest_reference(history, now, minutes, tolerance)
        delta = None if current is None or reference is None else current - reference
        pct = None
        if delta is not None and reference and reference > 0:
            pct = round(delta * 100.0 / reference, 3)
        result[label] = {
            "delta": delta,
            "pct": pct,
            "reference_holders": reference,
            "reference_age_minutes": None if actual_age is None else round(actual_age, 1),
        }
    return result


def _velocity_status(current: int | None, deltas: dict) -> str:
    if current is None:
        return "NO_VERIFIED_HOLDER_DATA"
    available = [v.get("delta") for v in deltas.values() if isinstance(v, dict) and v.get("delta") is not None]
    if not available:
        return "BASELINE_BUILDING"
    if any(value > 0 for value in available):
        return "GROWING"
    if any(value < 0 for value in available):
        return "SHRINKING"
    return "FLAT"


def _delta_text(value: object) -> str:
    if not isinstance(value, dict) or value.get("delta") is None:
        return "—"
    delta = int(value["delta"])
    pct = value.get("pct")
    sign = "+" if delta > 0 else ""
    pct_text = "" if pct is None else f" ({float(pct):+.2f}%)"
    return f"{sign}{delta}{pct_text}"


def _fetch_exact_pool_with_holders(max_attempts: int = 3) -> dict:
    market = _ORIGINAL_FETCH_EXACT_POOL(max_attempts=max_attempts)
    now = datetime.now(timezone.utc)
    previous = base._load_state()
    history = _clean_holder_history(previous.get("holder_history"), now)
    holders, source_url, holder_error = _fetch_verified_holder_count()
    deltas = _holder_deltas(history, holders, now)
    market.update(
        {
            "holders_verified": holders,
            "holder_source": "BLOCKSCOUT_EXACT_CONTRACT" if holders is not None else None,
            "holder_source_url": source_url,
            "holder_error": holder_error,
            "holder_velocity": deltas,
            "holder_velocity_status": _velocity_status(holders, deltas),
        }
    )
    return market


def _holders_line(market: dict) -> str:
    holders = market.get("holders_verified")
    if holders is None:
        return "👥 Holders: NO VERIFIED HOLDER DATA"
    velocity = market.get("holder_velocity") if isinstance(market.get("holder_velocity"), dict) else {}
    return (
        f"👥 Holders verified: {int(holders):,} | "
        f"Δ5m {_delta_text(velocity.get('5m'))} | "
        f"Δ1H {_delta_text(velocity.get('1h'))} | "
        f"Δ6H {_delta_text(velocity.get('6h'))}"
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
            _holders_line(market),
            f"💧 נזילות exact pool: {base._money(market.get('liquidity_usd'))}",
            f"📊 Volume: 1H {base._money(market.get('volume_h1_usd'))} | 24H {base._money(market.get('volume_h24_usd'))}",
            f"🟢/🔴 עסקאות 1H — buys / sells: {flow}",
            f"🔒 Identity locked: {base.TOKEN_CA}",
            f"🕒 {il_time}",
            "⚠️ BUY SETUP הוא סטאפ למעקב ולא הוראת קנייה; יש לאמת מחיר/נזילות בזמן הביצוע.",
            f"🔗 {market['pool_url']}",
        ]
    )[:3900]


def _save_state_with_holders(previous: dict, market: dict, zone: str, observed_at, alert_sent: bool) -> dict:
    state = _ORIGINAL_SAVE_STATE(previous, market, zone, observed_at, alert_sent)
    history = _clean_holder_history(previous.get("holder_history"), observed_at)
    holders = _holder_count(market.get("holders_verified"))
    if holders is not None:
        if history and history[-1].get("observed_at") == observed_at.isoformat():
            history[-1]["holders"] = holders
        else:
            history.append({"observed_at": observed_at.isoformat(), "holders": holders})
    history = _clean_holder_history(history, observed_at)

    state["holders_verified"] = holders
    state["holder_source"] = market.get("holder_source")
    state["holder_source_url"] = market.get("holder_source_url")
    state["holder_velocity_status"] = market.get("holder_velocity_status")
    state["holder_velocity"] = market.get("holder_velocity") or {}
    state["holder_history"] = history
    if market.get("holder_error"):
        state["holder_error"] = str(market.get("holder_error"))[:500]
    else:
        state.pop("holder_error", None)
    base.STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


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

    now = datetime(2026, 9, 6, 17, 30, tzinfo=timezone.utc)
    history = [
        {"observed_at": (now - timedelta(minutes=5)).isoformat(), "holders": 1680},
        {"observed_at": (now - timedelta(minutes=60)).isoformat(), "holders": 1600},
        {"observed_at": (now - timedelta(minutes=360)).isoformat(), "holders": 1200},
    ]
    deltas = _holder_deltas(history, 1700, now)
    assert deltas["5m"]["delta"] == 20
    assert deltas["1h"]["delta"] == 100
    assert deltas["6h"]["delta"] == 500
    assert _velocity_status(1700, deltas) == "GROWING"
    assert _holder_deltas([], 1700, now)["5m"]["delta"] is None
    assert _velocity_status(1700, _holder_deltas([], 1700, now)) == "BASELINE_BUILDING"
    assert _holders_line({"holders_verified": 1700, "holder_velocity": deltas}).startswith("👥 Holders verified: 1,700")
    print("AOBS signal-watch v2 + holder-velocity self-test: OK")


def run() -> dict:
    base._should_alert = _should_alert
    base._fetch_exact_pool = _fetch_exact_pool_with_holders
    base._message = _message
    base._save_state = _save_state_with_holders
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
