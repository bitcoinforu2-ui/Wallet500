"""Selective Catalyst alerts.

Raw listing discoveries stay silent. New listing candidates are watched silently and
are promoted to Telegram only when the exchange + exact market setup crosses a
high-interest threshold. Promoted candidates are monitored until listing and only
material changes are sent. Scores are rankings, not probabilities of future return.
"""
from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .market_data import snapshot as market_snapshot

DATA = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
WIRE = DATA / "catalyst-wire-live.json"
LEDGER = DATA / "catalyst-wire-ledger.json"
STATE = DATA / "catalyst-focus-state.json"
OUT = DATA / "catalyst-focus-live.json"

MIN_LIQ = 50_000.0
FOCUS_SCORE = 76.0
DROP_SCORE = 64.0
PENDING_RECHECK_MIN = 15
FOCUS_COOLDOWN_MIN = 30
UNKNOWN_MAX_H = 72
MAX_PENDING = 120

# Bootstrap priors only. They are intentionally labelled as uncalibrated until the
# exchange-specific historical listing DNA study replaces them with empirical data.
PRIORS = {
    "binance": (100, 96, "S"),
    "coinbase": (96, 94, "S"),
    "okx": (91, 84, "A"),
    "bybit": (87, 78, "A"),
    "kraken": (83, 84, "A"),
    "upbit": (82, 88, "A"),
    "bithumb": (72, 82, "A"),
    "bitget": (78, 66, "B"),
    "gate": (74, 58, "B"),
    "kucoin": (72, 62, "B"),
    "crypto.com": (70, 72, "B"),
    "mexc": (64, 30, "C"),
    "htx": (60, 48, "C"),
    "coinex": (48, 45, "C"),
    "lbank": (44, 35, "C"),
    "bingx": (46, 38, "C"),
    "bitmart": (42, 34, "C"),
    "weex": (34, 28, "D"),
}


def nowdt():
    return datetime.now(timezone.utc)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def num(value, default=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def clamp(value):
    return max(0.0, min(100.0, value))


def pct(new, old):
    return None if not old else (new / old - 1.0) * 100.0


def parseiso(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc) if value else None
    except Exception:
        return None


def prior(owner):
    reach, scarcity, tier = PRIORS.get(str(owner or "").lower(), (45, 40, "C"))
    return {"reach": reach, "scarcity": scarcity, "tier": tier}


def liqscore(value):
    if value < MIN_LIQ:
        return 0
    if value < 100_000:
        return 45 + 25 * (value - 50_000) / 50_000
    if value < 250_000:
        return 70 + 15 * (value - 100_000) / 150_000
    if value < 1_000_000:
        return 85 + 15 * (value - 250_000) / 750_000
    return 100


def flowscore(buys, sells):
    ratio = (buys + 1) / (sells + 1)
    score = (
        10 if ratio < 0.6
        else 35 if ratio < 0.85
        else 55 if ratio < 1.05
        else 70 if ratio < 1.3
        else 86 if ratio < 1.75
        else 96 if ratio < 2.5
        else 90
    )
    return score, ratio


def turnoverscore(volume_h1, liquidity):
    ratio = volume_h1 / liquidity if liquidity else 0
    score = (
        20 if ratio < 0.05
        else 45 if ratio < 0.2
        else 65 if ratio < 0.5
        else 85 if ratio < 1.5
        else 100 if ratio < 4
        else 78 if ratio < 8
        else 58
    )
    return score, ratio


def headroom(h1, h24):
    if h1 >= 80 or h24 >= 220:
        return 15
    if h1 >= 50 or h24 >= 140:
        return 35
    if h1 >= 25 or h24 >= 80:
        return 55
    if h1 >= 12 or h24 >= 45:
        return 72
    if max(h1, h24) >= 0:
        return 90
    if max(h1, h24) >= -15:
        return 78
    return 58


def grade(score):
    return (
        "A+" if score >= 88
        else "A" if score >= 82
        else "B+" if score >= 76
        else "B" if score >= 68
        else "C" if score >= 58
        else "D"
    )


def risk(market):
    score = 0
    reasons = []
    liquidity = num(market.get("liquidity_usd"))
    cap = num(market.get("market_cap")) or num(market.get("fdv"))
    buys, sells = int(market.get("buys_h1") or 0), int(market.get("sells_h1") or 0)
    h1, h24 = num(market.get("price_change_h1")), num(market.get("price_change_h24"))

    if liquidity < MIN_LIQ:
        score += 60
        reasons.append("LIQUIDITY_BELOW_50K")
    if cap > 0:
        depth = liquidity / cap
        if depth < 0.01:
            score += 25
            reasons.append("LIQUIDITY_LT_1PCT_MCAP")
        elif depth < 0.03:
            score += 15
            reasons.append("LIQUIDITY_LT_3PCT_MCAP")
        elif depth < 0.05:
            score += 7
            reasons.append("LIQUIDITY_LT_5PCT_MCAP")
    if sells > max(10, buys * 1.45):
        score += 18
        reasons.append("SELL_PRESSURE")
    if h1 >= 80 or h24 >= 220:
        score += 22
        reasons.append("ALREADY_OVEREXTENDED")
    if market.get("token_identity_verified") is not True:
        score += 50
        reasons.append("TOKEN_IDENTITY_UNVERIFIED")
    if not market.get("pair_address"):
        score += 50
        reasons.append("PAIR_UNRESOLVED")
    return clamp(score), reasons


def listing_start(event):
    value = (event.get("machine_state") or {}).get("start") or event.get("listing_start")
    if value in (None, "", 0, "0"):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            x = float(value)
            x = x / 1000 if x > 10_000_000_000 else x
            return datetime.fromtimestamp(x, tz=timezone.utc).isoformat()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def score_event(event):
    out = dict(event)
    chain = str(event.get("chain") or "").lower()
    token = str(event.get("contract") or "").strip()
    market = None
    if chain and token:
        try:
            market = market_snapshot(chain, token)
        except Exception as exc:
            out["market_error"] = f"{type(exc).__name__}: {exc}"[:160]

    if not market:
        out.update(
            decision_score=0.0,
            grade="D",
            focus_eligible=False,
            decision="WATCH_SILENT_NO_EXACT_MARKET",
            market=None,
            blockers=["EXACT_MARKET_UNAVAILABLE"],
        )
        return out

    ep = prior(event.get("source_owner"))
    exchange_score = 0.64 * ep["reach"] + 0.36 * ep["scarcity"]
    liquidity = num(market.get("liquidity_usd"))
    liquidity_score = liqscore(liquidity)
    flow_score, flow_ratio = flowscore(int(market.get("buys_h1") or 0), int(market.get("sells_h1") or 0))
    turnover_score, turnover_ratio = turnoverscore(num(market.get("volume_h1")), liquidity)
    room = headroom(num(market.get("price_change_h1")), num(market.get("price_change_h24")))
    readiness = 0.45 * liquidity_score + 0.30 * flow_score + 0.25 * turnover_score
    risk_score, risk_reasons = risk(market)

    raw = (
        0.24 * clamp(num(event.get("impact_score")))
        + 0.27 * exchange_score
        + 0.27 * readiness
        + 0.22 * room
    )
    score = clamp(raw - 0.35 * risk_score)

    blockers = []
    if event.get("preliminary_filter_pass") is not True:
        blockers.append("PRELIMINARY_FILTER_FAIL")
    if not event.get("source_url"):
        blockers.append("OFFICIAL_SOURCE_MISSING")
    if liquidity < MIN_LIQ:
        blockers.append("LIQUIDITY_BELOW_50K")
    if market.get("token_identity_verified") is not True or not market.get("pair_address"):
        blockers.append("EXACT_PAIR_NOT_VERIFIED")
    if risk_score >= 55:
        blockers.append("RISK_TOO_HIGH")
    if exchange_score < 50:
        blockers.append("EXCHANGE_IMPACT_TOO_LOW")

    start = listing_start(event)
    start_dt = parseiso(start)
    if start_dt and start_dt <= nowdt():
        blockers.append("LISTING_ALREADY_STARTED")

    eligible = bool(score >= FOCUS_SCORE and not blockers)
    out.update(
        market=market,
        dex_url=market.get("url") or event.get("dex_url"),
        listing_start=start,
        exchange_prior=ep,
        exchange_score=round(exchange_score, 2),
        market_readiness_score=round(readiness, 2),
        headroom_score=round(room, 2),
        risk_score=round(risk_score, 2),
        decision_score=round(score, 2),
        grade=grade(score),
        focus_eligible=eligible,
        decision="FOCUS_UNTIL_LISTING" if eligible else "WATCH_SILENT",
        blockers=blockers,
        decision_reasons=[
            f"EXCHANGE_{str(event.get('source_owner') or 'unknown').upper()}_{ep['tier']}",
            f"FLOW_RATIO_{flow_ratio:.2f}",
            f"TURNOVER_H1_{turnover_ratio:.2f}",
            *risk_reasons,
        ],
    )
    return out


def focus_key(event):
    return f"{event.get('chain')}:{str(event.get('contract') or '').lower()}:{str(event.get('source_owner') or '').lower()}"


def _current_forward(wire):
    out = {}
    for event in wire.get("events") or []:
        if not isinstance(event, dict) or not event.get("forward_new"):
            continue
        event_id = str(event.get("event_id") or "")
        if event_id:
            out[event_id] = event
    return out


def discover_unseen(wire, ledger, state, seen):
    """Use the immutable ledger so a 5-minute timing race cannot lose an event.

    On the first Focus run we baseline historical ledger entries, while preserving
    any event currently marked forward_new by Catalyst Wire.
    """
    records = ledger.get("events") if isinstance(ledger.get("events"), dict) else {}
    forward = _current_forward(wire)
    baseline_done = bool(state.get("ledger_baseline_complete"))

    if not baseline_done:
        for event_id, rec in records.items():
            if event_id not in forward:
                seen[event_id] = (rec or {}).get("first_seen_at") or nowdt().isoformat()
        state["ledger_baseline_complete"] = True
        state["ledger_baseline_at"] = nowdt().isoformat()

    candidates = {}
    for event_id, rec in records.items():
        if event_id in seen or not isinstance(rec, dict):
            continue
        event = rec.get("event")
        if isinstance(event, dict):
            candidates[event_id] = event

    # Safety fallback if an event is fresh in the current feed but the ledger commit
    # has not yet landed in the checkout used by this workflow.
    for event_id, event in forward.items():
        if event_id not in seen:
            candidates[event_id] = event

    return candidates


def send(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "TELEGRAM_SECRETS_MISSING"
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("ok")), "OK" if payload.get("ok") else "API_OK_FALSE"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:180]


def money(value):
    x = num(value)
    if x >= 1e6:
        return f"${x/1e6:.2f}M"
    if x >= 1e3:
        return f"${x/1e3:.1f}K"
    return f"${x:.2f}" if x > 0 else "—"


def price(value):
    x = num(value)
    return f"${x:.8g}" if x > 0 else "—"


def startmsg(event):
    market = event.get("market") or {}
    lines = [
        "🚨 WALLET500 · FOCUS LISTING ALERT",
        f"{event.get('symbol')} · {str(event.get('source_owner') or '').upper()} · {event.get('event_type')}",
        f"Decision {event.get('decision_score')}/100 · Grade {event.get('grade')} (ranking, not probability)",
        f"Exchange {event.get('exchange_score')}/100 · Readiness {event.get('market_readiness_score')}/100 · Risk {event.get('risk_score')}/100",
        f"Price {price(market.get('price_usd'))} · Liq {money(market.get('liquidity_usd'))} · MCap {money(market.get('market_cap') or market.get('fdv'))}",
        f"1h {num(market.get('price_change_h1')):+.1f}% · Vol {money(market.get('volume_h1'))} · Buys/Sells {market.get('buys_h1',0)}/{market.get('sells_h1',0)}",
        "🎯 FOCUS UNTIL LISTING — only material changes will be sent",
    ]
    if event.get("listing_start"):
        lines.append("Listing UTC: " + event["listing_start"])
    if event.get("dex_url"):
        lines.append("📈 DEX: " + event["dex_url"])
    if event.get("source_url"):
        lines.append("🔗 Official: " + event["source_url"])
    return "\n".join(lines)


def updatemsg(event, reason, previous):
    market = event.get("market") or {}
    old_market = previous.get("market") or {}
    price_delta = pct(num(market.get("price_usd")), num(old_market.get("price_usd")))
    liquidity_delta = pct(num(market.get("liquidity_usd")), num(old_market.get("liquidity_usd")))
    return "\n".join(
        [
            "⚡ WALLET500 · FOCUS UPDATE",
            f"{event.get('symbol')} · {str(event.get('source_owner') or '').upper()} · {reason}",
            f"Score {event.get('decision_score')}/100 · Grade {event.get('grade')} · Risk {event.get('risk_score')}/100",
            f"Price {price(market.get('price_usd'))}" + (f" ({price_delta:+.1f}%)" if price_delta is not None else ""),
            f"Liquidity {money(market.get('liquidity_usd'))}" + (f" ({liquidity_delta:+.1f}%)" if liquidity_delta is not None else ""),
            f"1h {num(market.get('price_change_h1')):+.1f}% · Buys/Sells {market.get('buys_h1',0)}/{market.get('sells_h1',0)}",
            f"📈 DEX: {event.get('dex_url') or 'unresolved'}",
        ]
    )


def finalmsg(event, reason):
    market = event.get("market") or {}
    return "\n".join(
        [
            "🏁 WALLET500 · FOCUS CLOSED",
            f"{event.get('symbol')} · {str(event.get('source_owner') or '').upper()} · {reason}",
            f"Final score {event.get('decision_score')}/100 · Risk {event.get('risk_score')}/100",
            f"Price {price(market.get('price_usd'))} · Liq {money(market.get('liquidity_usd'))}",
            f"📈 DEX: {event.get('dex_url') or 'unresolved'}",
        ]
    )


def material_change(current, previous):
    current_market = current.get("market") or {}
    old_market = previous.get("market") or {}
    if num(current_market.get("liquidity_usd")) < MIN_LIQ:
        return "LIQUIDITY_BROKE_50K", True
    if num(current.get("decision_score")) < DROP_SCORE:
        return "SCORE_COLLAPSED", True

    score_delta = num(current.get("decision_score")) - num(previous.get("decision_score"))
    if abs(score_delta) >= 8:
        return f"SCORE_CHANGE_{score_delta:+.0f}", False

    price_delta = pct(num(current_market.get("price_usd")), num(old_market.get("price_usd")))
    if price_delta is not None and abs(price_delta) >= 10:
        return f"PRICE_MOVE_{price_delta:+.1f}PCT", False

    liquidity_delta = pct(
        num(current_market.get("liquidity_usd")), num(old_market.get("liquidity_usd"))
    )
    if liquidity_delta is not None and abs(liquidity_delta) >= 20:
        return f"LIQUIDITY_MOVE_{liquidity_delta:+.1f}PCT", False

    _, current_ratio = flowscore(
        int(current_market.get("buys_h1") or 0), int(current_market.get("sells_h1") or 0)
    )
    _, previous_ratio = flowscore(
        int(old_market.get("buys_h1") or 0), int(old_market.get("sells_h1") or 0)
    )
    if current_ratio >= 1.6 and previous_ratio < 1.6:
        return "BUY_PRESSURE_SURGE", False
    if current_ratio <= 0.7 and previous_ratio > 0.7:
        return "SELL_PRESSURE_SURGE", True
    return None, False


def _listing_close_reason(event, first_seen, now):
    listing = parseiso(event.get("listing_start"))
    if listing and now >= listing:
        return "LISTING_TIME_REACHED"
    if not listing and now - first_seen >= timedelta(hours=UNKNOWN_MAX_H):
        return "72H_NO_LISTING_TIME"
    return None


def _due(last_check, minutes, now):
    last = parseiso(last_check)
    return last is None or now - last >= timedelta(minutes=minutes)


def _send_record(text, delivered, errors, payload):
    ok, detail = send(text)
    if ok:
        delivered.append(payload)
    elif detail != "TELEGRAM_SECRETS_MISSING":
        errors.append({"key": payload.get("key"), "error": detail})
    return ok


def run():
    wire = load(WIRE, {})
    ledger = load(LEDGER, {"events": {}})
    state = load(
        STATE,
        {
            "version": 2,
            "focus": {},
            "pending": {},
            "seen_event_ids": {},
            "ledger_baseline_complete": False,
        },
    )
    if not isinstance(state, dict):
        state = {}

    focus = state.get("focus") if isinstance(state.get("focus"), dict) else {}
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
    seen = state.get("seen_event_ids") if isinstance(state.get("seen_event_ids"), dict) else {}
    now = nowdt()
    delivered, errors, evaluated = [], [], []

    # 1) Ingest every genuinely new raw event into a silent watch queue. Nothing is
    # sent to Telegram merely because a listing event exists.
    new_events = discover_unseen(wire, ledger, state, seen)
    for event_id, event in new_events.items():
        seen[event_id] = now.isoformat()
        if event_id not in pending:
            pending[event_id] = {
                "status": "WATCHING_SILENT",
                "first_seen_at": now.isoformat(),
                "event": event,
                "last_check_at": None,
            }

    # 2) Re-score silent candidates. They may become interesting later, so an early
    # low score or temporarily unresolved DEX does not permanently discard them.
    for event_id, rec in list(pending.items()):
        if rec.get("status") != "WATCHING_SILENT":
            continue
        if not _due(rec.get("last_check_at"), PENDING_RECHECK_MIN, now):
            continue

        first_seen = parseiso(rec.get("first_seen_at")) or now
        scored = score_event(dict(rec.get("event") or {}))
        rec["last_check_at"] = now.isoformat()
        rec["last_snapshot"] = scored
        evaluated.append(scored)

        close_reason = _listing_close_reason(scored, first_seen, now)
        if close_reason:
            rec.update(status="CLOSED_SILENT", closed_at=now.isoformat(), close_reason=close_reason)
            continue

        if not scored.get("focus_eligible"):
            continue

        key = focus_key(scored)
        if key in focus and focus[key].get("status") == "TRACKING":
            rec.update(status="MERGED_INTO_FOCUS", promoted_at=now.isoformat(), focus_key=key)
            continue

        focus[key] = {
            "status": "TRACKING",
            "selected_at": now.isoformat(),
            "event": scored,
            "last_alert_at": None,
            "last_alert_snapshot": scored,
            "last_snapshot": scored,
            "start_alert_delivered": False,
            "updates_sent": 0,
            "countdown_60_sent": False,
            "countdown_15_sent": False,
        }
        rec.update(status="PROMOTED", promoted_at=now.isoformat(), focus_key=key)

    # 3) Monitor only promoted Focus candidates every run until listing.
    for key, rec in list(focus.items()):
        if rec.get("status") != "TRACKING":
            continue

        current = score_event(dict(rec.get("event") or {}))
        rec["last_check_at"] = now.isoformat()
        if not current.get("market"):
            rec["last_check_error"] = current.get("market_error") or "EXACT_MARKET_UNAVAILABLE"
            continue

        selected = parseiso(rec.get("selected_at")) or now
        close_reason = _listing_close_reason(current, selected, now)
        if close_reason:
            if rec.get("start_alert_delivered"):
                _send_record(
                    finalmsg(current, close_reason),
                    delivered,
                    errors,
                    {"key": key, "type": "FOCUS_CLOSED", "symbol": current.get("symbol"), "reason": close_reason},
                )
            rec.update(
                status="LISTING_REACHED" if close_reason == "LISTING_TIME_REACHED" else "TIMEOUT",
                closed_at=now.isoformat(),
                last_snapshot=current,
            )
            continue

        # Retry the initial Focus alert if Telegram had a transient failure.
        if not rec.get("start_alert_delivered"):
            ok = _send_record(
                startmsg(current),
                delivered,
                errors,
                {"key": key, "type": "FOCUS_START", "symbol": current.get("symbol")},
            )
            if ok:
                rec.update(
                    start_alert_delivered=True,
                    last_alert_at=now.isoformat(),
                    last_alert_snapshot=current,
                )
            rec["last_snapshot"] = current
            continue

        # Two useful countdown alerts max, only when an exact listing time is known.
        listing = parseiso(current.get("listing_start"))
        if listing:
            remaining = (listing - now).total_seconds() / 60.0
            countdown_reason = None
            if 0 < remaining <= 15 and not rec.get("countdown_15_sent"):
                countdown_reason = f"LISTING_IN_{max(1, int(round(remaining)))}_MIN"
                rec["countdown_15_sent"] = True
                rec["countdown_60_sent"] = True
            elif 15 < remaining <= 60 and not rec.get("countdown_60_sent"):
                countdown_reason = f"LISTING_IN_{int(round(remaining))}_MIN"
                rec["countdown_60_sent"] = True
            if countdown_reason:
                if _send_record(
                    updatemsg(current, countdown_reason, rec.get("last_alert_snapshot") or current),
                    delivered,
                    errors,
                    {"key": key, "type": "FOCUS_COUNTDOWN", "symbol": current.get("symbol"), "reason": countdown_reason},
                ):
                    rec.update(last_alert_at=now.isoformat(), last_alert_snapshot=current)
                rec["last_snapshot"] = current
                continue

        previous = rec.get("last_alert_snapshot") or rec.get("event") or {}
        reason, critical = material_change(current, previous)
        cooldown_ok = critical or _due(rec.get("last_alert_at"), FOCUS_COOLDOWN_MIN, now)
        if reason and cooldown_ok:
            text = finalmsg(current, reason) if critical else updatemsg(current, reason, previous)
            if _send_record(
                text,
                delivered,
                errors,
                {
                    "key": key,
                    "type": "FOCUS_CRITICAL" if critical else "FOCUS_UPDATE",
                    "symbol": current.get("symbol"),
                    "reason": reason,
                },
            ):
                rec.update(
                    last_alert_at=now.isoformat(),
                    last_alert_snapshot=current,
                    updates_sent=int(rec.get("updates_sent") or 0) + 1,
                )
                if critical:
                    rec.update(status="DROPPED", closed_at=now.isoformat())
        rec["last_snapshot"] = current

    # Keep state bounded without throwing away active silent research candidates.
    active_pending = [
        (event_id, rec)
        for event_id, rec in pending.items()
        if rec.get("status") == "WATCHING_SILENT"
    ]
    active_pending.sort(key=lambda item: item[1].get("first_seen_at") or "", reverse=True)
    if len(active_pending) > MAX_PENDING:
        for event_id, rec in active_pending[MAX_PENDING:]:
            rec.update(status="EVICTED_SILENT_CAP", closed_at=now.isoformat())

    if len(seen) > 20_000:
        seen = dict(list(seen.items())[-20_000:])

    active_focus = [
        dict(rec, key=key)
        for key, rec in focus.items()
        if rec.get("status") == "TRACKING"
    ]
    active_focus.sort(
        key=lambda item: num((item.get("last_snapshot") or {}).get("decision_score")),
        reverse=True,
    )

    out = {
        "version": 2,
        "updated_at": now.isoformat(),
        "mode": "SELECTIVE_LISTING_FOCUS_ONLY",
        "policy": {
            "raw_listing_telegram": False,
            "silent_watch_before_promotion": True,
            "focus_threshold": FOCUS_SCORE,
            "hard_liquidity_floor_usd": MIN_LIQ,
            "focus_score_is_probability": False,
            "selected_candidates_monitored_until_listing": True,
            "pending_recheck_minutes": PENDING_RECHECK_MIN,
            "focus_check_every_run": True,
            "unknown_listing_time_fallback_hours": UNKNOWN_MAX_H,
            "followup_only_on_material_change_or_countdown": True,
            "automatic_trade": False,
            "exchange_priors_status": "BOOTSTRAP_PRIORS_PENDING_EMPIRICAL_EXCHANGE_LISTING_DNA_CALIBRATION",
        },
        "counts": {
            "raw_events": len(wire.get("events") or []),
            "new_raw_ingested": len(new_events),
            "silent_pending": sum(1 for rec in pending.values() if rec.get("status") == "WATCHING_SILENT"),
            "evaluated_this_run": len(evaluated),
            "promoted_total": sum(1 for rec in pending.values() if rec.get("status") == "PROMOTED"),
            "active_focus": len(active_focus),
            "telegram_delivered_this_run": len(delivered),
        },
        "active_focus": active_focus[:50],
        "new_evaluations": evaluated[:100],
        "telegram": {"delivered": delivered, "errors": errors},
    }

    write(OUT, out)
    state.update(
        version=2,
        updated_at=now.isoformat(),
        focus=focus,
        pending=pending,
        seen_event_ids=seen,
    )
    write(STATE, state)
    print("CATALYST_FOCUS", json.dumps(out["counts"], separators=(",", ":")))
    return out


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
