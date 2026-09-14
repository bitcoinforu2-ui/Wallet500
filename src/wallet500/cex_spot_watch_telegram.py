from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import cex_identity_preflight as age_preflight

DATA = Path("data")
MIN_MARKET_AGE_DAYS = 90
MIN_FIRST_ALERT_SCORE = 35
MAX_FIRST_ALERT_MOVE_PCT = 30.0
FIRST_RUN_FRESH_HOURS = 2.0
MAX_DELIVERY_LAG_HOURS = 24.0
MAX_SENDS_PER_RUN = 8
MODE = "EARLY_CEX_WATCH_MANUAL_REVIEW_V4"
LEVERAGED_SUFFIXES = (
    "2L", "2S", "3L", "3S", "4L", "4S", "5L", "5S",
    "BULL", "BEAR", "UP", "DOWN",
)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _f(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _i(value) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _parse_dt(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _base_symbol(value) -> str:
    text = str(value or "").split(":", 1)[0].upper().strip()
    text = text.replace("-", "").replace("_", "").replace("/", "")
    if text.endswith("USDTM"):
        return text[:-5]
    if text.endswith("USDT"):
        return text[:-4]
    return text


def _canonical_symbol(value) -> str:
    base = _base_symbol(value)
    return f"{base}USDT" if base else ""


def _is_leveraged(value) -> bool:
    base = _base_symbol(value)
    return any(base.endswith(suffix) and len(base) > len(suffix) for suffix in LEVERAGED_SUFFIXES)


def _first_alert(row: dict) -> dict:
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    first = milestones.get("first_alert") if isinstance(milestones.get("first_alert"), dict) else {}
    if first:
        return first
    ts = row.get("first_alert_observed_at")
    price = row.get("first_alert_reference_price")
    if not ts or _f(price) <= 0:
        return {}
    return {
        "kind": "FIRST_ALERT",
        "observed_at": ts,
        "reference_price": price,
        "reference_exchange": row.get("first_alert_reference_exchange"),
        "reference_change_24h_pct": row.get("first_alert_reference_change_24h_pct"),
        "score": row.get("first_alert_score"),
        "coherent_confirmations": row.get("first_alert_coherent_confirmations"),
    }


def _preeligible(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("research_only") is not True or row.get("actionable") is not False:
        return False
    if row.get("automatic_buy") is True or _is_leveraged(row.get("symbol")):
        return False
    first = _first_alert(row)
    if not first:
        return False
    if _i(first.get("score")) < MIN_FIRST_ALERT_SCORE:
        return False
    if _f(first.get("reference_price")) <= 0 or _parse_dt(first.get("observed_at")) is None:
        return False
    if abs(_f(first.get("reference_change_24h_pct"))) > MAX_FIRST_ALERT_MOVE_PCT:
        return False
    return True


def _event_key(row: dict) -> str:
    first = _first_alert(row)
    return f"{_canonical_symbol(row.get('symbol'))}|{first.get('observed_at')}"


def _current_market(row: dict) -> dict:
    markets = [x for x in (row.get("markets") or []) if isinstance(x, dict)]
    usd_like = [x for x in markets if x.get("volume_comparable_usd_like", True)]
    pool = usd_like or markets
    return max(pool, key=lambda x: (_f(x.get("volume_24h")), _f(x.get("price"))), default={})


def _identity_index(payload: dict) -> dict[str, dict]:
    out = {}
    for row in payload.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        base = _base_symbol(row.get("symbol"))
        if not base:
            continue
        prev = out.get(base)
        if prev is None or (
            row.get("identity_status") == "DEX_VERIFIED"
            and prev.get("identity_status") != "DEX_VERIFIED"
        ):
            out[base] = row
    return out


def _age_from_identity(row: dict | None) -> dict | None:
    if not isinstance(row, dict) or row.get("market_age_verified") is not True:
        return None
    days = _i(row.get("market_age_min_days"))
    if days < MIN_MARKET_AGE_DAYS:
        return None
    return {
        "market_age_verified": True,
        "market_age_min_days": days,
        "market_age_evidence_at": row.get("market_age_evidence_at"),
        "market_age_evidence_source": row.get("market_age_evidence_source"),
        "coingecko_id": row.get("coingecko_id"),
    }


def _verify_ages(rows: list[dict], identities: dict[str, dict]) -> tuple[dict[str, dict], list[dict], str | None]:
    verified: dict[str, dict] = {}
    unresolved: list[dict] = []
    for row in rows:
        base = _base_symbol(row.get("symbol"))
        meta = _age_from_identity(identities.get(base))
        if meta:
            verified[base] = meta
        else:
            unresolved.append(row)

    if not unresolved:
        return verified, [], None

    try:
        matches_by_symbol = age_preflight._fetch_by_symbols(
            [_base_symbol(row.get("symbol")) for row in unresolved]
        )
    except Exception as exc:
        return verified, unresolved, f"{type(exc).__name__}: {exc}"[:300]

    still_unresolved = []
    for row in unresolved:
        base = _base_symbol(row.get("symbol"))
        matches = matches_by_symbol.get(base) or []
        chosen = None
        if len(matches) == 1:
            chosen = matches[0]
        elif len(matches) > 1:
            chosen, _evidence = age_preflight._resolve_ambiguous(row, base, matches)
        meta = age_preflight._age_meta(
            chosen, "COINGECKO_ATH_OR_ATL_EARLY_CEX_TELEGRAM_PREFLIGHT"
        ) if chosen else None
        if meta and _i(meta.get("market_age_min_days")) >= MIN_MARKET_AGE_DAYS:
            verified[base] = meta
        else:
            still_unresolved.append(row)
    return verified, still_unresolved, None


def _send(bot_token: str, chat_id: str, text: str, max_attempts: int = 3) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("ok") is not True:
                raise RuntimeError(f"Telegram API rejected message: {payload}")
            return
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt + 1 < max_attempts:
                retry_after = 2
                try:
                    payload = json.loads(exc.read().decode("utf-8"))
                    retry_after = max(1, min(30, int((payload.get("parameters") or {}).get("retry_after") or 2)))
                except Exception:
                    pass
                time.sleep(retry_after)
                continue
            if 500 <= exc.code < 600 and attempt + 1 < max_attempts:
                time.sleep(1 + attempt)
                continue
            raise
        except Exception:
            if attempt + 1 >= max_attempts:
                raise
            time.sleep(1 + attempt)


def _format_price(value: float) -> str:
    if value <= 0:
        return "n/a"
    if value >= 1:
        return f"${value:,.6f}".rstrip("0").rstrip(".")
    return f"${value:.10f}".rstrip("0").rstrip(".")


def _format_message(row: dict, identity: dict | None, age: dict) -> str:
    first = _first_alert(row)
    market = _current_market(row)
    detect_price = _f(first.get("reference_price"))
    current_price = _f(market.get("price"))
    gain = ((current_price / detect_price) - 1.0) * 100.0 if detect_price > 0 and current_price > 0 else None
    symbol = _canonical_symbol(row.get("symbol"))
    exact = (
        isinstance(identity, dict)
        and identity.get("identity_status") == "DEX_VERIFIED"
        and identity.get("identity_verified") is True
    )
    lines = [
        f"🔥 EARLY CEX WATCH — {symbol}",
        f"Discovery price: {_format_price(detect_price)}",
        f"Current CEX price: {_format_price(current_price)}",
        f"Since discovery: {gain:+.2f}%" if gain is not None else "Since discovery: n/a",
        f"First alert: {first.get('observed_at')} | score {_i(first.get('score'))} | 24h {_f(first.get('reference_change_24h_pct')):+.2f}%",
        f"Current score: {_i(row.get('spot_revival_score') or row.get('current_score'))} | coherent venues: {_i(row.get('coherent_confirmations') or row.get('current_coherent_confirmations'))}",
        f"Veteran age verified: {age.get('market_age_min_days')}d | CoinGecko: {age.get('coingecko_id') or 'verified'}",
    ]
    if exact:
        lines.extend([
            f"Exact on-chain identity: VERIFIED ({identity.get('chain')})",
            f"Contract: {identity.get('token_address') or identity.get('token')}",
            f"Pair: {identity.get('pair_address')}",
        ])
        if identity.get("dex_url"):
            lines.append(f"DEX: {identity.get('dex_url')}")
    else:
        lines.append("Exact on-chain identity: PENDING — CEX evidence only")
    lines.extend([
        "",
        "⚠️ MANUAL REVIEW ONLY — NOT A BUY ORDER — NO AUTOMATIC TRADE",
        "Production REAL_ALERT, liquidity and survival gates remain unchanged.",
    ])
    return "\n".join(lines)


def _candidate_rows(radar: dict) -> list[dict]:
    merged: dict[str, dict] = {}
    for lane in ("watchlist", "alerts"):
        for row in radar.get(lane) or []:
            if not _preeligible(row):
                continue
            key = _event_key(row)
            if key:
                merged[key] = dict(row)
    return list(merged.values())


def run(data_dir: Path = DATA, now: datetime | None = None) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    radar = _load(data_dir / "cex-spot-revival-radar.json", {})
    identity_payload = _load(data_dir / "cex-spot-identity-radar.json", {})
    state_path = data_dir / "cex-spot-telegram-state.json"
    report_path = data_dir / "cex-spot-telegram-report.json"
    had_state = state_path.exists()
    state = _load(state_path, {"version": 1, "sent": {}, "baselined": {}, "pending": {}})
    for name in ("sent", "baselined", "pending"):
        if not isinstance(state.get(name), dict):
            state[name] = {}

    now_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_s = now_dt.isoformat()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(bot_token and chat_id)

    current_rows = _candidate_rows(radar if isinstance(radar, dict) else {})
    events: dict[str, dict] = {_event_key(row): row for row in current_rows}
    for key, pending in state["pending"].items():
        row = pending.get("row") if isinstance(pending, dict) else None
        if isinstance(row, dict) and key not in events and _preeligible(row):
            events[key] = row

    suppressed = []
    delivered = []
    failures = []
    identities = _identity_index(identity_payload if isinstance(identity_payload, dict) else {})

    if not configured:
        report = {
            "version": 4,
            "mode": MODE,
            "generated_at": now_s,
            "status": "SKIPPED_UNCONFIGURED_NO_STATE_WRITE",
            "research_only": True,
            "automatic_buy": False,
            "telegram_delivery_enabled": False,
            "eligible_event_count": len(events),
            "delivered_count": 0,
            "pending_count": len(state["pending"]),
            "baselined_count": 0,
            "suppressed": [],
            "truth_contract": {
                "manual_review_only": True,
                "never_real_alert": True,
                "automatic_buy_never_enabled": True,
                "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
                "immutable_first_alert_required": True,
                "maximum_first_alert_move_pct": MAX_FIRST_ALERT_MOVE_PCT,
                "production_gates_unchanged": True,
            },
        }
        _write(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    active_rows = []
    active_keys = []
    for key, row in events.items():
        if key in state["sent"] or key in state["baselined"]:
            continue
        first_dt = _parse_dt(_first_alert(row).get("observed_at"))
        if first_dt is None:
            continue
        age_hours = max(0.0, (now_dt - first_dt).total_seconds() / 3600.0)
        if not had_state and age_hours > FIRST_RUN_FRESH_HOURS:
            state["baselined"][key] = {"at": now_s, "reason": "FIRST_RUN_STALE_BASELINE"}
            suppressed.append({"key": key, "reason": "FIRST_RUN_STALE_BASELINE"})
            state["pending"].pop(key, None)
            continue
        if had_state and age_hours > MAX_DELIVERY_LAG_HOURS:
            state["baselined"][key] = {"at": now_s, "reason": "STALE_UNDELIVERED_OVER_24H"}
            suppressed.append({"key": key, "reason": "STALE_UNDELIVERED_OVER_24H"})
            state["pending"].pop(key, None)
            continue
        active_rows.append(row)
        active_keys.append(key)
        state["pending"][key] = {"first_observed_at": now_s, "row": row}

    verified, unresolved, age_error = _verify_ages(active_rows, identities)
    unresolved_keys = {_event_key(row) for row in unresolved}
    for key in unresolved_keys:
        suppressed.append({"key": key, "reason": "AGE_IDENTITY_PENDING_RETRY"})

    send_budget = MAX_SENDS_PER_RUN
    for key, row in zip(active_keys, active_rows):
        if key in unresolved_keys:
            continue
        base = _base_symbol(row.get("symbol"))
        age = verified.get(base)
        if not age:
            suppressed.append({"key": key, "reason": "AGE_IDENTITY_UNVERIFIED"})
            continue
        if send_budget <= 0:
            suppressed.append({"key": key, "reason": "PER_RUN_SEND_BUDGET_RETRY_NEXT_CYCLE"})
            continue
        identity = identities.get(base)
        text = _format_message(row, identity, age)
        try:
            _send(bot_token, chat_id, text)
        except Exception as exc:
            failures.append({"key": key, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        state["sent"][key] = {
            "sent_at": now_s,
            "symbol": _canonical_symbol(row.get("symbol")),
            "first_alert_observed_at": _first_alert(row).get("observed_at"),
            "first_alert_reference_price": _first_alert(row).get("reference_price"),
        }
        state["pending"].pop(key, None)
        delivered.append({"key": key, "symbol": _canonical_symbol(row.get("symbol"))})
        send_budget -= 1

    state["version"] = 1
    state["updated_at"] = now_s
    if len(state["pending"]) > 100:
        state["pending"] = dict(list(state["pending"].items())[-100:])
    if len(state["baselined"]) > 2000:
        state["baselined"] = dict(list(state["baselined"].items())[-2000:])
    if len(state["sent"]) > 5000:
        state["sent"] = dict(list(state["sent"].items())[-5000:])
    _write(state_path, state)

    status = "OK"
    if failures:
        status = "PARTIAL_SEND_FAILURE_RETRY_PENDING"
    elif age_error:
        status = "DEGRADED_AGE_PREFLIGHT_RETRY_PENDING"
    report = {
        "version": 4,
        "mode": MODE,
        "generated_at": now_s,
        "status": status,
        "research_only": True,
        "automatic_buy": False,
        "telegram_delivery_enabled": True,
        "source_generated_at": radar.get("generated_at") if isinstance(radar, dict) else None,
        "eligible_event_count": len(events),
        "delivered_count": len(delivered),
        "delivered": delivered,
        "pending_count": len(state["pending"]),
        "baselined_count": len(suppressed),
        "suppressed": suppressed,
        "failures": failures,
        "age_preflight_error": age_error,
        "policy": (
            "Only immutable veteran FIRST_ALERT CEX events are user-facing in this narrow manual-review lane. "
            "Generic research candidates remain silent and CEX evidence never becomes a REAL_ALERT or an automatic trade."
        ),
        "truth_contract": {
            "manual_review_only": True,
            "never_real_alert": True,
            "automatic_buy_never_enabled": True,
            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "immutable_first_alert_required": True,
            "minimum_first_alert_score": MIN_FIRST_ALERT_SCORE,
            "maximum_first_alert_move_pct": MAX_FIRST_ALERT_MOVE_PCT,
            "exact_onchain_identity_may_be_pending": True,
            "production_gates_unchanged": True,
        },
    }
    _write(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
