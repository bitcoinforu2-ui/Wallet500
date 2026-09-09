from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .cryptoyeezus_live_watch import extract_refs, resolve_market_identity
from .social_direct_providers import scan_x
from .telegram_alerts import _fmt_israel_time, _send

X_HANDLE = "AgentOBSRH"
X_URL = f"https://x.com/{X_HANDLE}"
DATA_DIR = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
STATE_PATH = Path(os.getenv("AGENTOBS_STATE_PATH", str(DATA_DIR / "agentobs-intel-state.json")))
EVENTS_PATH = Path(os.getenv("AGENTOBS_EVENTS_PATH", str(DATA_DIR / "agentobs-intel-events.json")))
LATEST_PATH = Path(os.getenv("AGENTOBS_LATEST_PATH", str(DATA_DIR / "agentobs-intel-latest.json")))

TRADE_WORDS = (
    "buy", "bought", "sell", "sold", "entry", "exit", "position", "trade",
    "long", "short", "pnl", "profit", "loss", "filled", "swap", "ape", "added",
)
REASON_WORDS = (
    "because", "reason", "reasoning", "thesis", "setup", "conviction", "risk",
    "target", "stop", "liquidity", "volume", "momentum", "wallet", "flow",
)
NEWS_WORDS = (
    "obscura", "fomo", "launch", "listing", "listed", "integration", "integrated",
    "partnership", "deploy", "upgrade", "release", "agent", "robinhood",
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


def _post_key(row: dict) -> str:
    return f"x:{row.get('id') or row.get('url') or row.get('published_at') or ''}"


def classify_post(text: str, refs: dict | None = None) -> dict:
    refs = refs or extract_refs(text)
    low = str(text or "").lower()
    categories = []
    if any(word in low for word in TRADE_WORDS):
        categories.append("TRADE")
    if any(word in low for word in REASON_WORDS):
        categories.append("REASONING")
    if any(word in low for word in NEWS_WORDS):
        categories.append("NEWS")
    if refs.get("contracts") or refs.get("dex_links"):
        categories.append("ONCHAIN_IDENTITY")
    if refs.get("tickers"):
        categories.append("TOKEN_MENTION")

    score = 0
    score += 45 if "TRADE" in categories else 0
    score += 20 if "REASONING" in categories else 0
    score += 25 if "NEWS" in categories else 0
    score += 25 if "ONCHAIN_IDENTITY" in categories else 0
    score += 10 if "TOKEN_MENTION" in categories else 0
    score = min(score, 100)
    material = score >= 45 or ("NEWS" in categories and "REASONING" in categories)
    return {"categories": categories, "intelligence_score": score, "material": material}


def fetch_x() -> tuple[list[dict], dict]:
    rows, status = scan_x({"official_x": X_URL})
    locked = [
        row for row in rows
        if str(row.get("author") or "").lower().lstrip("@") == X_HANDLE.lower()
    ]
    status = dict(status or {})
    status["count_after_author_lock"] = len(locked)
    return locked, status


def _alert_text(event: dict) -> str:
    market = event.get("market_snapshot") or {}
    refs = event.get("refs") or {}
    cats = ", ".join(event.get("categories") or []) or "UNCLASSIFIED"
    lines = [
        "🧠 Wallet500 • Agent OBS Intelligence",
        f"Source: @{X_HANDLE}",
        f"Published (Israel): {_fmt_israel_time(event.get('published_at'))}",
        f"Categories: {cats}",
        f"Intel score: {event.get('intelligence_score', 0)}/100",
    ]
    symbol = market.get("symbol") or ((refs.get("tickers") or [None])[0])
    if symbol:
        lines.append(f"Token: {symbol}")
    if market.get("token_address"):
        lines.append(f"Contract: {market['token_address']}")
    elif refs.get("contracts"):
        lines.append(f"Explicit contract: {refs['contracts'][0]}")
    if market.get("pair_address"):
        lines.append(f"Pair: {market['pair_address']}")
    if market:
        lines.append(f"Identity: {market.get('identity_evidence') or 'resolved'}")
    text = str(event.get("text") or "").strip().replace("\n", " ")
    if text:
        lines.append(f"Post: {text[:700]}")
    if event.get("url"):
        lines.append(f"X: {event['url']}")
    lines.append("Research intelligence only — not an automatic trade signal.")
    return "\n".join(lines)


def run() -> dict:
    now = _now_iso()
    state = _load(STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    seen = set(state.get("seen_post_keys") or [])
    first_run = not bool(state.get("initialized"))

    rows, provider = fetch_x()
    rows.sort(key=lambda r: str(r.get("published_at") or ""))
    events_payload = _load(EVENTS_PATH, {"version": 1, "events": []})
    events = list(events_payload.get("events") or []) if isinstance(events_payload, dict) else []

    new_events = []
    alert_events = []
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    for row in rows:
        key = _post_key(row)
        if not key or key in seen:
            continue
        refs = extract_refs(row.get("text") or "")
        classification = classify_post(row.get("text") or "", refs)
        market = None
        identity_flags = []
        if refs.get("contracts") or refs.get("dex_links"):
            market, identity_flags = resolve_market_identity(refs)
        event = {
            "source": "x",
            "source_account": X_HANDLE,
            "post_id": row.get("id"),
            "published_at": row.get("published_at"),
            "observed_at": now,
            "url": row.get("url"),
            "text": row.get("text"),
            "engagement": row.get("engagement"),
            "refs": refs,
            "market_snapshot": market,
            "identity_flags": identity_flags,
            **classification,
            "production_trade_impact": "NONE",
            "research_only": True,
        }
        events.append(event)
        new_events.append(event)
        seen.add(key)

        # First run establishes a forward-only baseline and never floods old posts.
        if first_run or not event.get("material"):
            continue
        if bot_token and chat_id:
            try:
                message_id, attempts = _send(bot_token, chat_id, _alert_text(event))
                event["telegram"] = {"status": "SENT", "message_id": message_id, "attempts": attempts}
                alert_events.append(event)
            except Exception as exc:
                event["telegram"] = {"status": f"ERROR:{type(exc).__name__}", "detail": str(exc)[:160]}
        else:
            event["telegram"] = {"status": "SKIPPED_UNCONFIGURED"}

    # Keep bounded history while preserving forward-only dedupe truth.
    events = events[-1000:]
    seen_list = list(seen)[-5000:]
    state_out = {
        "version": 1,
        "mode": "AGENTOBS_X_INTELLIGENCE_WATCH_V1",
        "initialized": True,
        "updated_at": now,
        "seen_post_keys": seen_list,
        "source_account": X_HANDLE,
    }
    latest = {
        "version": 1,
        "mode": "AGENTOBS_X_INTELLIGENCE_WATCH_V1",
        "observed_at": now,
        "status": "OK" if str(provider.get("status") or "").startswith("OK") else "DEGRADED",
        "provider": provider,
        "first_run_baseline": first_run,
        "new_posts": len(new_events),
        "material_posts": sum(1 for e in new_events if e.get("material")),
        "telegram_alerts": len(alert_events),
        "latest_events": new_events[-20:],
        "production_trade_impact": "NONE",
    }
    _write(STATE_PATH, state_out)
    _write(EVENTS_PATH, {"version": 1, "events": events})
    _write(LATEST_PATH, latest)
    print(json.dumps(latest, ensure_ascii=False, indent=2))
    return latest


if __name__ == "__main__":
    run()
