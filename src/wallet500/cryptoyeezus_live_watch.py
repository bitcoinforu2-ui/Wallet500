from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .social_direct_providers import scan_x
from .telegram_alerts import _fmt_israel_time, _fmt_money, _send
from .waking_fallbacks import _get_json, _get_text, parse_telegram_messages

X_HANDLE = "CryptoYeezussss"
TG_HANDLE = "cryptoyeezuscalls"
X_URL = f"https://x.com/{X_HANDLE}"
TG_URL = f"https://t.me/{TG_HANDLE}"

DATA_DIR = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
STATE_PATH = Path(os.getenv("YEEZUS_STATE_PATH", str(DATA_DIR / "cryptoyeezus-live-state.json")))
CALLS_PATH = Path(os.getenv("YEEZUS_CALLS_PATH", str(DATA_DIR / "cryptoyeezus-calls.json")))
LATEST_PATH = Path(os.getenv("YEEZUS_LATEST_PATH", str(DATA_DIR / "cryptoyeezus-live-latest.json")))

TICKER_RE = re.compile(r"(?<![\w$])\$([A-Za-z][A-Za-z0-9_]{1,14})\b")
EVM_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
SOL_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")
URL_RE = re.compile(r"https?://\S+", re.I)
DEX_RE = re.compile(r"https?://(?:www\.)?dexscreener\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9]+)[^\s<>\"]*", re.I)
PRIMARY_TICKER_RE = re.compile(
    r"(?:bag(?:ging)?(?:\s+(?:a|the))?|gambl\w*|ape\w*|punt\w*|buy(?:ing)?|bought|loading|load|adding|added|entry|position)"
    r"[^$\n]{0,55}\$([A-Za-z][A-Za-z0-9_]{1,14})\b",
    re.I,
)

CALL_WORDS = (
    "bag", "gambl", "ape", "aped", "punt", "buy", "bought", "loading",
    "load ", "adding", "added", "entry", "position", "call", "send it",
    "sending", "tekk", "conviction", "runner", "moon", "play", "cook",
)
REPEAT_MATERIAL_WORDS = (
    "new ath", "ath", "added", "adding", "bought more", "size", "conviction",
    "breakout", "send it", "sending", "entry", "re-entry", "reentry",
)


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


def _post_key(row: dict) -> str:
    return f"{str(row.get('source') or '').lower()}:{row.get('id') or row.get('url') or row.get('published_at') or ''}"


def extract_refs(text: str) -> dict:
    """Extract only explicit identifiers from post body; URLs are not contracts."""
    text = str(text or "")

    tickers: list[str] = []
    seen_tickers: set[str] = set()
    for raw in TICKER_RE.findall(text):
        sym = _norm_symbol(raw)
        if sym and sym not in seen_tickers:
            seen_tickers.add(sym)
            tickers.append(sym)

    dex_links = []
    for m in DEX_RE.finditer(text):
        dex_links.append({
            "url": m.group(0).rstrip(".,);]"),
            "chain_hint": m.group(1).lower(),
            "pair_address": m.group(2),
        })

    # A DexScreener pair path is pair evidence, not an explicit token CA. Strip
    # all URLs first, then strip EVM addresses before the base58 scan so a
    # substring such as `x111...` can never be misclassified as Solana.
    body = URL_RE.sub(" ", text)
    evm = []
    seen_contracts: set[str] = set()
    for raw in EVM_RE.findall(body):
        low = raw.lower()
        if low not in seen_contracts:
            seen_contracts.add(low)
            evm.append(raw)
    base58_body = EVM_RE.sub(" ", body)
    sol = []
    for raw in SOL_RE.findall(base58_body):
        if not any(c.isdigit() for c in raw):
            continue
        low = raw.lower()
        if low not in seen_contracts:
            seen_contracts.add(low)
            sol.append(raw)

    return {"tickers": tickers, "contracts": [*evm, *sol], "dex_links": dex_links}


def looks_like_call(text: str, refs: dict | None = None) -> bool:
    refs = refs or extract_refs(text)
    if not (refs["tickers"] or refs["contracts"] or refs["dex_links"]):
        return False
    low = str(text or "").lower()
    return bool(refs["dex_links"]) or any(word in low for word in CALL_WORDS)


def repeat_is_material(text: str, refs: dict | None = None) -> bool:
    refs = refs or extract_refs(text)
    low = str(text or "").lower()
    return bool(refs["contracts"] or refs["dex_links"]) or any(word in low for word in REPEAT_MATERIAL_WORDS)


def _primary_symbol(text: str, refs: dict, market: dict | None) -> str | None:
    if market and market.get("symbol"):
        return _norm_symbol(market["symbol"])
    match = PRIMARY_TICKER_RE.search(str(text or ""))
    if match:
        return _norm_symbol(match.group(1))
    tickers = refs.get("tickers") or []
    return _norm_symbol(tickers[0]) if len(tickers) == 1 else None


def _safe_pair_snapshot(pair: dict, expected_symbols: list[str] | None = None) -> tuple[dict | None, list[str]]:
    if not isinstance(pair, dict):
        return None, ["PAIR_PAYLOAD_INVALID"]
    base = pair.get("baseToken") or {}
    symbol = _norm_symbol(base.get("symbol"))
    expected = {_norm_symbol(x) for x in (expected_symbols or []) if _norm_symbol(x)}
    flags: list[str] = []
    if expected and symbol and symbol not in expected:
        return None, ["SYMBOL_MISMATCH"]
    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}
    return {
        "chain": pair.get("chainId"),
        "dex": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"),
        "token_address": base.get("address"),
        "symbol": symbol or None,
        "price_usd": pair.get("priceUsd"),
        "market_cap_usd": pair.get("marketCap"),
        "fdv_usd": pair.get("fdv"),
        "liquidity_usd": (pair.get("liquidity") or {}).get("usd"),
        "volume_h1_usd": volume.get("h1"),
        "volume_h24_usd": volume.get("h24"),
        "price_change_h1_pct": price_change.get("h1"),
        "price_change_h6_pct": price_change.get("h6"),
        "price_change_h24_pct": price_change.get("h24"),
        "pair_created_at": pair.get("pairCreatedAt"),
        "dex_url": pair.get("url"),
    }, flags


def resolve_market_identity(refs: dict) -> tuple[dict | None, list[str]]:
    flags: list[str] = []
    expected = refs.get("tickers") or []

    for link in refs.get("dex_links") or []:
        chain = str(link.get("chain_hint") or "").strip()
        pair_address = str(link.get("pair_address") or "").strip()
        if not chain or not pair_address:
            continue
        try:
            payload = _get_json(f"https://api.dexscreener.com/latest/dex/pairs/{quote(chain)}/{quote(pair_address)}")
            pairs = payload.get("pairs") or []
            if pairs:
                snap, pair_flags = _safe_pair_snapshot(pairs[0], expected)
                flags.extend(pair_flags)
                if snap:
                    snap["identity_evidence"] = "EXACT_DEXSCREENER_PAIR_LINK"
                    snap["pair_identity_locked"] = True
                    return snap, sorted(set(flags))
        except Exception as exc:
            flags.append(f"DEX_PAIR_LOOKUP_FAILED:{type(exc).__name__}")

    for contract in refs.get("contracts") or []:
        try:
            payload = _get_json("https://api.dexscreener.com/latest/dex/tokens/" + quote(contract))
            candidates = []
            for pair in payload.get("pairs") or []:
                base = pair.get("baseToken") or {}
                if str(base.get("address") or "").lower() != str(contract).lower():
                    continue
                try:
                    liq = float((pair.get("liquidity") or {}).get("usd") or 0)
                except (TypeError, ValueError):
                    liq = 0.0
                candidates.append((liq, pair))
            candidates.sort(key=lambda item: item[0], reverse=True)
            for _, pair in candidates[:5]:
                snap, pair_flags = _safe_pair_snapshot(pair, expected)
                flags.extend(pair_flags)
                if snap:
                    snap["identity_evidence"] = "EXACT_CONTRACT_DEXSCREENER_DEEPEST_POOL"
                    snap["pair_identity_locked"] = True
                    return snap, sorted(set(flags))
        except Exception as exc:
            flags.append(f"DEX_TOKEN_LOOKUP_FAILED:{type(exc).__name__}")

    if expected:
        flags.append("TICKER_ONLY_IDENTITY_UNRESOLVED")
    return None, sorted(set(flags))


def _fetch_telegram() -> tuple[list[dict], dict]:
    try:
        page = _get_text(f"https://t.me/s/{TG_HANDLE}")
        rows = parse_telegram_messages(page, TG_HANDLE)
        return rows, {"provider": "telegram_public", "status": "OK", "count": len(rows)}
    except Exception as exc:
        return [], {"provider": "telegram_public", "status": f"{type(exc).__name__}:{str(exc)[:120]}"}


def _fetch_x() -> tuple[list[dict], dict]:
    rows, status = scan_x({"official_x": X_URL})
    rows = [r for r in rows if str(r.get("author") or "").lower().lstrip("@") == X_HANDLE.lower()]
    status = dict(status or {})
    status["count_after_author_lock"] = len(rows)
    return rows, status


def fetch_sources(state: dict) -> tuple[list[dict], dict]:
    tg_rows, tg_status = _fetch_telegram()
    run_count = int(state.get("run_count") or 0)
    every = max(1, int(os.getenv("YEEZUS_X_POLL_EVERY_CYCLES", "6")))
    should_poll_x = run_count <= 1 or run_count % every == 0
    if should_poll_x:
        x_rows, x_status = _fetch_x()
    else:
        x_rows, x_status = [], {"provider": "x", "status": "SKIPPED_BUDGET_GUARD"}

    rows = []
    for row in [*tg_rows, *x_rows]:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").lower()
        author = str(row.get("author") or "").lower().lstrip("@")
        if source == "telegram" and author != TG_HANDLE.lower():
            continue
        if source == "x" and author != X_HANDLE.lower():
            continue
        rows.append(row)
    rows.sort(key=lambda r: str(r.get("published_at") or ""))
    return rows, {"telegram": tg_status, "x": x_status}


def _token_record_key(refs: dict, market: dict | None, symbol: str | None = None) -> str | None:
    if market and market.get("token_address"):
        return "ca:" + str(market["token_address"]).lower()
    if refs.get("contracts"):
        return "ca:" + str(refs["contracts"][0]).lower()
    if symbol:
        return "symbol:" + _norm_symbol(symbol)
    return None


def _find_existing_token_key(tokens: dict, refs: dict, market: dict | None, symbol: str | None) -> str | None:
    direct = _token_record_key(refs, market, symbol)
    if direct and direct in tokens:
        return direct
    symbols = {_norm_symbol(symbol)} if symbol else set()
    if market and market.get("symbol"):
        symbols.add(_norm_symbol(market["symbol"]))
    addresses = {str(x).lower() for x in refs.get("contracts") or []}
    if market and market.get("token_address"):
        addresses.add(str(market["token_address"]).lower())
    for key, row in tokens.items():
        if not isinstance(row, dict):
            continue
        if _norm_symbol(row.get("symbol")) in symbols and _norm_symbol(row.get("symbol")):
            return key
        address = str(row.get("token_address") or "").lower()
        if address and address in addresses:
            return key
    return None


def _dt(value: object) -> datetime | None:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _same_token(a: dict, b: dict) -> bool:
    am = a.get("market_snapshot") or {}
    bm = b.get("market_snapshot") or {}
    aa = str(am.get("token_address") or a.get("explicit_contract") or "").lower()
    ba = str(bm.get("token_address") or b.get("explicit_contract") or "").lower()
    if aa and ba:
        return aa == ba
    sa = _norm_symbol(a.get("symbol") or am.get("symbol"))
    sb = _norm_symbol(b.get("symbol") or bm.get("symbol"))
    return bool(sa and sb and sa == sb)


def _find_cross_post(event: dict, prior_events: list[dict], window_minutes: int = 90) -> dict | None:
    when = _dt(event.get("published_at") or event.get("observed_at"))
    if when is None:
        return None
    for prior in reversed(prior_events[-100:]):
        if str(prior.get("source") or "") == str(event.get("source") or ""):
            continue
        if not _same_token(event, prior):
            continue
        pwhen = _dt(prior.get("published_at") or prior.get("observed_at"))
        if pwhen and abs((when - pwhen).total_seconds()) <= window_minutes * 60:
            return prior
    return None


def _alert_text(event: dict) -> str:
    market = event.get("market_snapshot") or {}
    symbol = event.get("symbol") or market.get("symbol") or "UNKNOWN"
    lines = [
        "🚨 Wallet500 • CryptoYeezus Social Call",
        f"Type: {event.get('event_type')}",
        f"Source: {str(event.get('source') or '').upper()}",
        f"Time (Israel): {_fmt_israel_time(event.get('published_at'))}",
        f"Token: ${symbol}" if symbol != "UNKNOWN" else "Token: UNKNOWN",
        f"CA: {market.get('token_address') or event.get('explicit_contract') or 'UNVERIFIED'}",
        f"Chain: {market.get('chain') or 'UNVERIFIED'}",
        f"Exact pair: {market.get('pair_address') or 'UNVERIFIED'}",
        f"MC: {_fmt_money(market.get('market_cap_usd') or market.get('fdv_usd'))}",
        f"Liquidity: {_fmt_money(market.get('liquidity_usd'))}",
        f"Vol 1h / 24h: {_fmt_money(market.get('volume_h1_usd'))} / {_fmt_money(market.get('volume_h24_usd'))}",
    ]
    if event.get("url"):
        lines.append(f"Post: {event['url']}")
    if market.get("dex_url"):
        lines.append(f"Dex: {market['dex_url']}")
    if event.get("risk_flags"):
        lines.append("Flags: " + ", ".join(event["risk_flags"][:5]))
    lines.append("Research alert only • no automatic buy")
    return "\n".join(lines)


def _send_alert(event: dict) -> dict:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return {"attempted": False, "sent": False, "reason": "TELEGRAM_SECRETS_MISSING"}
    try:
        message_id, attempts = _send(token, chat_id, _alert_text(event))
        return {"attempted": True, "sent": True, "message_id": message_id, "attempts": attempts}
    except Exception as exc:
        return {"attempted": True, "sent": False, "reason": f"{type(exc).__name__}:{str(exc)[:160]}"}


def _event_from_row(row: dict, state: dict, observed_at: str, resolve_market: bool = True) -> dict | None:
    text = str(row.get("text") or "")
    refs = extract_refs(text)
    if not looks_like_call(text, refs):
        return None
    market, flags = resolve_market_identity(refs) if resolve_market else (None, [])
    symbol = _primary_symbol(text, refs, market)
    if not symbol and not refs.get("contracts") and not market:
        return None

    tokens = state.setdefault("tokens", {})
    existing_key = _find_existing_token_key(tokens, refs, market, symbol)
    key = existing_key or _token_record_key(refs, market, symbol)
    if not key:
        return None

    event = {
        "event_id": _post_key(row) + ":" + key,
        "event_type": "REPEAT_PROMOTION" if existing_key else "FIRST_MENTION",
        "caller": "CryptoYeezus",
        "source": str(row.get("source") or "").lower(),
        "source_post_id": row.get("id"),
        "published_at": row.get("published_at"),
        "observed_at": observed_at,
        "url": row.get("url"),
        "symbol": symbol,
        "explicit_contract": (refs.get("contracts") or [None])[0],
        "tickers": refs.get("tickers") or [],
        "dex_links": refs.get("dex_links") or [],
        "text": text[:1500],
        "market_snapshot": market,
        "risk_flags": flags,
        "pair_identity_locked": bool(market and market.get("pair_identity_locked") is True),
        "automatic_buy": False,
        "research_only": True,
    }

    if not existing_key:
        tokens[key] = {
            "symbol": symbol,
            "token_address": (market or {}).get("token_address") or event.get("explicit_contract"),
            "first_seen_at": row.get("published_at") or observed_at,
            "first_observed_at": observed_at,
            "first_source": event["source"],
            "first_post_id": row.get("id"),
            "first_post_url": row.get("url"),
            "first_market_snapshot": market,
        }
    else:
        record = tokens[existing_key]
        if market and market.get("token_address") and not record.get("token_address"):
            record["token_address"] = market["token_address"]
        if symbol and not record.get("symbol"):
            record["symbol"] = symbol
        record["last_promotion_at"] = row.get("published_at") or observed_at
        record["last_promotion_source"] = event["source"]
    return event


def run() -> dict:
    observed_at = _now_iso()
    state = _load(STATE_PATH, {
        "version": 1,
        "bootstrapped": False,
        "run_count": 0,
        "seen_posts": [],
        "tokens": {},
    })
    state["run_count"] = int(state.get("run_count") or 0) + 1
    rows, provider_status = fetch_sources(state)
    seen = {str(x) for x in state.get("seen_posts") or []}
    new_rows = [r for r in rows if _post_key(r) not in seen]

    calls_doc = _load(CALLS_PATH, {
        "version": 1,
        "mode": "FORWARD_ONLY_CRYPTOYEEZUS_SOCIAL_CALL_RESEARCH_V1",
        "caller": "CryptoYeezus",
        "canonical_sources": {"x": X_URL, "telegram": TG_URL},
        "automatic_buy": False,
        "events": [],
    })
    events = calls_doc.setdefault("events", [])
    new_events = []

    if not state.get("bootstrapped"):
        for row in rows:
            seen.add(_post_key(row))
            event = _event_from_row(row, state, observed_at, resolve_market=False)
            if event:
                event["baseline_only"] = True
                event["alert"] = {"attempted": False, "sent": False, "reason": "INITIAL_BASELINE_NO_HINDSIGHT"}
                events.append(event)
        state["bootstrapped"] = True
        status = "BASELINE_BOOTSTRAPPED"
    else:
        status = "OK"
        for row in new_rows:
            seen.add(_post_key(row))
            event = _event_from_row(row, state, observed_at, resolve_market=True)
            if not event:
                continue
            cross_post = _find_cross_post(event, events)
            if cross_post:
                event["event_type"] = "CROSS_POST_DUPLICATE"
                event["canonical_event_id"] = cross_post.get("event_id")
                event["alert"] = {"attempted": False, "sent": False, "reason": "CROSS_SOURCE_DEDUPLICATED"}
                cross_post.setdefault("cross_posts", []).append({
                    "source": event.get("source"),
                    "published_at": event.get("published_at"),
                    "url": event.get("url"),
                    "source_post_id": event.get("source_post_id"),
                })
            else:
                should_alert = event["event_type"] == "FIRST_MENTION" or repeat_is_material(event["text"], extract_refs(event["text"]))
                event["alert"] = _send_alert(event) if should_alert else {
                    "attempted": False,
                    "sent": False,
                    "reason": "NON_MATERIAL_REPEAT_PROMOTION",
                }
            events.append(event)
            new_events.append(event)

    state["seen_posts"] = list(seen)[-1500:]
    state["last_run_at"] = observed_at
    state["provider_status"] = provider_status

    calls_doc["events"] = events[-2000:]
    calls_doc["updated_at"] = observed_at
    calls_doc["event_count"] = len(calls_doc["events"])
    calls_doc["truth_contract"] = {
        "forward_only": True,
        "no_hindsight": True,
        "ticker_only_never_becomes_exact_contract_without_evidence": True,
        "pair_identity_requires_provider_or_post_evidence": True,
        "repeat_promotion_never_resets_entry_time": True,
        "cross_source_duplicates_do_not_create_second_alert": True,
        "misses_and_failures_retained": True,
        "automatic_buy": False,
    }

    latest = {
        "version": 1,
        "mode": "CRYPTOYEEZUS_LIVE_SOURCE_WATCH_V1",
        "observed_at": observed_at,
        "status": status,
        "providers": provider_status,
        "new_posts": len(new_rows),
        "new_call_events": len(new_events),
        "latest_events": new_events[-20:],
        "automatic_buy": False,
    }
    _write(STATE_PATH, state)
    _write(CALLS_PATH, calls_doc)
    _write(LATEST_PATH, latest)
    return latest


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
