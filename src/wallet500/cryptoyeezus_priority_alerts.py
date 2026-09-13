from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .cryptoyeezus_live_watch import repeat_is_material
from .telegram_alerts import _fmt_israel_time, _fmt_money, _send
from .waking_fallbacks import _get_json

DATA_DIR = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
STATE_PATH = Path(os.getenv("YEEZUS_STATE_PATH", str(DATA_DIR / "cryptoyeezus-live-state.json")))
CALLS_PATH = Path(os.getenv("YEEZUS_CALLS_PATH", str(DATA_DIR / "cryptoyeezus-calls.json")))
LATEST_PATH = Path(os.getenv("YEEZUS_LATEST_PATH", str(DATA_DIR / "cryptoyeezus-live-latest.json")))
PRIORITY_STATE_PATH = Path(os.getenv("YEEZUS_PRIORITY_STATE_PATH", str(DATA_DIR / "cryptoyeezus-priority-state.json")))

PERSISTENCE_ALERT_MINUTES = max(30, int(os.getenv("YEEZUS_PERSISTENCE_ALERT_MINUTES", "120")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_symbol(value: object) -> str:
    return str(value or "").strip().upper().lstrip("$")


def _dt(value: object) -> datetime | None:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _token_record(event: dict, live_state: dict) -> tuple[str | None, dict | None]:
    tokens = live_state.get("tokens") or {}
    market = event.get("market_snapshot") or {}
    addresses = {
        str(x).lower()
        for x in (market.get("token_address"), event.get("explicit_contract"))
        if x
    }
    for address in addresses:
        key = "ca:" + address
        row = tokens.get(key)
        if isinstance(row, dict):
            return key, row

    symbol = _norm_symbol(event.get("symbol") or market.get("symbol"))
    if not symbol:
        return None, None
    matches = [
        (key, row)
        for key, row in tokens.items()
        if isinstance(row, dict) and _norm_symbol(row.get("symbol")) == symbol
    ]
    if len(matches) == 1:
        return matches[0]
    return None, None


def _identity_from_record(record: dict | None) -> dict | None:
    if not isinstance(record, dict):
        return None
    prior = record.get("first_market_snapshot") or {}
    token = str(record.get("token_address") or prior.get("token_address") or "").strip()
    pair = str(prior.get("pair_address") or "").strip()
    chain = str(prior.get("chain") or "").strip()
    symbol = _norm_symbol(record.get("symbol") or prior.get("symbol"))
    if not token or not pair or not chain or prior.get("pair_identity_locked") is not True:
        return None
    return {
        "token_address": token,
        "pair_address": pair,
        "chain": chain,
        "symbol": symbol or None,
        "dex_url": prior.get("dex_url"),
    }


def _fresh_exact_pair(identity: dict | None) -> dict | None:
    if not identity:
        return None
    chain = str(identity.get("chain") or "").strip()
    pair = str(identity.get("pair_address") or "").strip()
    token = str(identity.get("token_address") or "").strip()
    if not chain or not pair or not token:
        return None
    try:
        payload = _get_json(
            f"https://api.dexscreener.com/latest/dex/pairs/{quote(chain)}/{quote(pair)}"
        )
        rows = payload.get("pairs") or []
        for row in rows:
            base = row.get("baseToken") or {}
            if str(base.get("address") or "").lower() != token.lower():
                continue
            if str(row.get("pairAddress") or "").lower() != pair.lower():
                continue
            volume = row.get("volume") or {}
            price_change = row.get("priceChange") or {}
            return {
                "chain": row.get("chainId") or chain,
                "dex": row.get("dexId"),
                "pair_address": row.get("pairAddress") or pair,
                "token_address": base.get("address") or token,
                "symbol": _norm_symbol(base.get("symbol") or identity.get("symbol")) or None,
                "price_usd": row.get("priceUsd"),
                "market_cap_usd": row.get("marketCap"),
                "fdv_usd": row.get("fdv"),
                "liquidity_usd": (row.get("liquidity") or {}).get("usd"),
                "volume_h1_usd": volume.get("h1"),
                "volume_h24_usd": volume.get("h24"),
                "price_change_h1_pct": price_change.get("h1"),
                "price_change_h24_pct": price_change.get("h24"),
                "pair_created_at": row.get("pairCreatedAt"),
                "dex_url": row.get("url") or identity.get("dex_url"),
                "identity_evidence": "PRIOR_EXACT_CALL_PLUS_FRESH_EXACT_PAIR",
                "pair_identity_locked": True,
            }
    except Exception:
        return None
    return None


def _identity_only_snapshot(identity: dict | None) -> dict | None:
    if not identity:
        return None
    return {
        "chain": identity.get("chain"),
        "pair_address": identity.get("pair_address"),
        "token_address": identity.get("token_address"),
        "symbol": identity.get("symbol"),
        "dex_url": identity.get("dex_url"),
        "identity_evidence": "PRIOR_EXACT_CALL_IDENTITY_ONLY",
        "pair_identity_locked": True,
        "fresh_market_data": False,
    }


def _token_key(event: dict, live_state: dict) -> tuple[str, dict | None, dict | None]:
    record_key, record = _token_record(event, live_state)
    market = event.get("market_snapshot") or {}
    if market.get("token_address"):
        key = "ca:" + str(market["token_address"]).lower()
    elif event.get("explicit_contract"):
        key = "ca:" + str(event["explicit_contract"]).lower()
    elif record_key:
        key = record_key
    else:
        key = "symbol:" + _norm_symbol(event.get("symbol") or "UNKNOWN")
    identity = _identity_from_record(record)
    return key, record, identity


def _elapsed_minutes(earlier: object, later: object) -> float | None:
    a = _dt(earlier)
    b = _dt(later)
    if not a or not b:
        return None
    return (b - a).total_seconds() / 60.0


def _decision(event: dict, priority_state: dict, token_key: str, exact_identity: bool) -> tuple[bool, str]:
    if event.get("baseline_only"):
        return False, "BASELINE_NO_HINDSIGHT"
    if event.get("event_type") == "CROSS_POST_DUPLICATE":
        return False, "CROSS_SOURCE_DEDUPLICATED"
    event_id = str(event.get("event_id") or "")
    if event_id and event_id in set(priority_state.get("sent_event_ids") or []):
        return False, "PRIORITY_EVENT_ALREADY_SENT"
    if event.get("event_type") == "FIRST_MENTION":
        return True, "FIRST_MENTION_PRIORITY"
    if repeat_is_material(str(event.get("text") or "")):
        return True, "MATERIAL_REPEAT_PRIORITY"

    token_alerts = priority_state.get("token_alerts") or {}
    last = (token_alerts.get(token_key) or {}).get("last_sent_at")
    elapsed = _elapsed_minutes(last, event.get("published_at") or event.get("observed_at"))
    if exact_identity and elapsed is not None and elapsed >= PERSISTENCE_ALERT_MINUTES:
        return True, "PERSISTENT_REPEAT_PRIORITY"
    return False, "NON_MATERIAL_REPEAT_COOLDOWN"


def _alert_text(event: dict, reason: str) -> str:
    market = event.get("market_snapshot") or {}
    symbol = event.get("symbol") or market.get("symbol") or "UNKNOWN"
    label = "NEW CALL" if event.get("event_type") == "FIRST_MENTION" else "REPEAT / PERSISTENCE"
    lines = [
        "🔥🔥🔥 Wallet500 • CRYPTOYEEZUS PRIORITY",
        f"{label} • {reason}",
        f"Token: ${symbol}" if symbol != "UNKNOWN" else "Token: UNKNOWN",
        f"Source: {str(event.get('source') or '').upper()} • {_fmt_israel_time(event.get('published_at'))}",
        f"CA: {market.get('token_address') or event.get('explicit_contract') or 'UNVERIFIED'}",
        f"Chain: {market.get('chain') or 'UNVERIFIED'}",
        f"Exact pair: {market.get('pair_address') or 'UNVERIFIED'}",
    ]
    if market.get("price_usd") is not None:
        lines.append(f"Price: ${market.get('price_usd')}")
    lines.extend([
        f"MC: {_fmt_money(market.get('market_cap_usd') or market.get('fdv_usd'))}",
        f"Liquidity: {_fmt_money(market.get('liquidity_usd'))}",
        f"Vol 1h / 24h: {_fmt_money(market.get('volume_h1_usd'))} / {_fmt_money(market.get('volume_h24_usd'))}",
    ])
    if market.get("price_change_h1_pct") is not None:
        lines.append(f"Move 1h: {market.get('price_change_h1_pct')}%")
    if event.get("url"):
        lines.append(f"Post: {event['url']}")
    if market.get("dex_url"):
        lines.append(f"Dex: {market['dex_url']}")
    if market.get("fresh_market_data") is False:
        lines.append("Market metrics unavailable now • identity retained from prior exact call")
    lines.append("Manual review only • no automatic buy")
    return "\n".join(lines)


def _send_priority(event: dict, reason: str) -> dict:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return {"attempted": False, "sent": False, "reason": "TELEGRAM_SECRETS_MISSING"}
    try:
        message_id, attempts = _send(token, chat_id, _alert_text(event, reason))
        return {
            "attempted": True,
            "sent": True,
            "message_id": message_id,
            "attempts": attempts,
            "delivery_policy": "CRYPTOYEEZUS_PRIORITY_V2",
            "priority_reason": reason,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "sent": False,
            "reason": f"{type(exc).__name__}:{str(exc)[:160]}",
            "delivery_policy": "CRYPTOYEEZUS_PRIORITY_V2",
            "priority_reason": reason,
        }


def run() -> dict:
    live_state = _load(STATE_PATH, {})
    calls_doc = _load(CALLS_PATH, {"events": []})
    latest = _load(LATEST_PATH, {"latest_events": []})
    priority_state = _load(PRIORITY_STATE_PATH, {
        "version": 2,
        "mode": "FORWARD_ONLY_CRYPTOYEEZUS_PRIORITY_ALERTS",
        "sent_event_ids": [],
        "token_alerts": {},
    })

    sent_ids = list(priority_state.get("sent_event_ids") or [])
    token_alerts = priority_state.setdefault("token_alerts", {})
    events_by_id = {
        str(row.get("event_id") or ""): row
        for row in calls_doc.get("events") or []
        if isinstance(row, dict) and row.get("event_id")
    }

    sent_count = 0
    skipped_count = 0
    for event in latest.get("latest_events") or []:
        if not isinstance(event, dict):
            continue
        token_key, _record, identity = _token_key(event, live_state)
        market = event.get("market_snapshot") or {}
        exact_now = bool(market.get("pair_identity_locked") is True and market.get("token_address") and market.get("pair_address"))

        if not exact_now and identity:
            refreshed = _fresh_exact_pair(identity)
            event["market_snapshot"] = refreshed or _identity_only_snapshot(identity)
            event["pair_identity_locked"] = True
            flags = [x for x in (event.get("risk_flags") or []) if x != "TICKER_ONLY_IDENTITY_UNRESOLVED"]
            event["risk_flags"] = flags
            exact_now = True

        should_send, reason = _decision(event, priority_state, token_key, exact_now)
        if should_send:
            outcome = _send_priority(event, reason)
        else:
            outcome = {
                "attempted": False,
                "sent": False,
                "reason": reason,
                "delivery_policy": "CRYPTOYEEZUS_PRIORITY_V2",
            }

        event["alert"] = outcome
        event["priority_alert"] = True
        event_id = str(event.get("event_id") or "")
        canonical = events_by_id.get(event_id)
        if canonical is not None:
            canonical.update(event)

        if outcome.get("sent") is True:
            sent_count += 1
            if event_id:
                sent_ids.append(event_id)
            when = event.get("published_at") or event.get("observed_at") or _now_iso()
            row = token_alerts.setdefault(token_key, {})
            row["last_sent_at"] = when
            row["last_event_id"] = event_id
            row["sent_count"] = int(row.get("sent_count") or 0) + 1
            row["last_reason"] = reason
        else:
            skipped_count += 1

    priority_state["sent_event_ids"] = sent_ids[-2000:]
    priority_state["last_run_at"] = _now_iso()
    priority_state["last_sent_count"] = sent_count
    priority_state["last_skipped_count"] = skipped_count
    priority_state["truth_contract"] = {
        "forward_only": True,
        "no_hindsight": True,
        "first_mention_alerts_once": True,
        "ticker_only_repeat_may_inherit_only_prior_exact_identity": True,
        "inherited_identity_requires_prior_exact_pair_lock": True,
        "fresh_market_metrics_require_same_exact_pair_and_token": True,
        "repeat_entry_time_never_resets": True,
        "cross_source_duplicates_never_alert_twice": True,
        "persistent_repeat_requires_cooldown_minutes": PERSISTENCE_ALERT_MINUTES,
        "automatic_buy": False,
    }

    latest["priority_delivery"] = {
        "policy": "CRYPTOYEEZUS_PRIORITY_V2",
        "sent": sent_count,
        "skipped": skipped_count,
        "persistence_alert_minutes": PERSISTENCE_ALERT_MINUTES,
    }
    calls_doc["priority_delivery_policy"] = "CRYPTOYEEZUS_PRIORITY_V2"

    _write(PRIORITY_STATE_PATH, priority_state)
    _write(CALLS_PATH, calls_doc)
    _write(LATEST_PATH, latest)
    return latest["priority_delivery"]


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
