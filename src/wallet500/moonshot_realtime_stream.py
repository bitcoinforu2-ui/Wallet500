"""Seconds-level Moonshot official announcement -> Telegram service.

Keeps a persistent X Filtered Stream connection for @moonshot and sends an
intelligence-only Telegram alert as soon as an official post contains an exact
Solana contract and either future-listing or verification language.

No trading logic lives here. This service never signs or broadcasts transactions
and never changes Wallet500 production gates.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import moonshot_future_listing_watch as fw
from . import moonshot_verification_watch as mv

MODE = "MOONSHOT_REALTIME_X_STREAM_V1"
STREAM_URL = "https://api.x.com/2/tweets/search/stream?tweet.fields=created_at,author_id"
RULES_URL = "https://api.x.com/2/tweets/search/stream/rules"
RULE_VALUE = "from:moonshot -is:retweet"
RULE_TAG = "wallet500-moonshot-official"
STATE_DIR = Path(os.getenv("WALLET500_STATE_DIR", "/tmp/wallet500"))
STATE_PATH = STATE_DIR / "moonshot-realtime-stream-state.json"
STATUS: dict[str, Any] = {
    "mode": MODE,
    "started_at": None,
    "stream_connected": False,
    "last_stream_line_at": None,
    "last_event_at": None,
    "last_error": None,
    "telegram_delivered": 0,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _headers() -> dict[str, str]:
    token = str(os.getenv("X_BEARER_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("X_BEARER_TOKEN_MISSING")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Wallet500-MoonshotRealtime/1.0",
    }


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"sent_event_keys": []}
    except Exception:
        return {"sent_event_keys": []}


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    sent = list(dict.fromkeys(str(x) for x in (state.get("sent_event_keys") or []) if x))[-5000:]
    STATE_PATH.write_text(
        json.dumps({"updated_at": _iso_now(), "sent_event_keys": sent}, indent=2) + "\n",
        encoding="utf-8",
    )


def _classification(text: str) -> str | None:
    if fw.is_future_listing_text(text):
        return "FUTURE_LISTING"
    if mv.VERIFY_RE.search(text) or re.search(r"verification\s+is\s+neither\s+an\s+endorsement", text, re.I):
        return "VERIFIED"
    return None


def parse_stream_payload(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return []
    data = payload["data"]
    text = str(data.get("text") or "")
    kind = _classification(text)
    if not kind:
        return []
    post_id = str(data.get("id") or "").strip()
    addresses = mv.extract_solana_addresses(text)
    if not post_id or not addresses:
        return []
    symbol_match = mv.SYMBOL_RE.search(text)
    symbol = symbol_match.group(1).upper() if symbol_match else None
    source_url = f"https://x.com/moonshot/status/{post_id}"
    return [{
        "post_id": post_id,
        "event_type": f"MOONSHOT_{kind}",
        "token": token,
        "symbol": symbol,
        "chain": "solana",
        "source_owner": "moonshot",
        "source_url": source_url,
        "published_at": data.get("created_at"),
        "text": text,
    } for token in addresses]


def _message(event: dict[str, Any]) -> str:
    kind = "FUTURE LISTING" if event.get("event_type") == "MOONSHOT_FUTURE_LISTING" else "VERIFIED"
    return "\n".join([
        f"🚨🔥 MOONSHOT {kind} — LIVE",
        f"{event.get('symbol') or '?'} | SOLANA",
        "📋 CONTRACT / CA:",
        str(event.get("token") or ""),
        "⚡ Official Moonshot event received from realtime stream",
        "⚠️ EARLY INTELLIGENCE — NOT A BUY SIGNAL",
        f"🔗 Source: {event.get('source_url')}",
        f"🕒 Published: {event.get('published_at') or 'unknown'}",
    ])


def _event_key(event: dict[str, Any]) -> str:
    return f"{event.get('post_id') or ''}:{event.get('token') or ''}"


def _send_event(event: dict[str, Any], state: dict[str, Any]) -> bool:
    key = _event_key(event)
    sent = set(str(x) for x in (state.get("sent_event_keys") or []))
    if key == ":" or key in sent:
        return False
    ok, status = fw._telegram_send(_message(event))
    if not ok:
        raise RuntimeError(f"TELEGRAM_{status}")
    state.setdefault("sent_event_keys", []).append(key)
    _save_state(state)
    STATUS["last_event_at"] = _iso_now()
    STATUS["telegram_delivered"] = int(STATUS.get("telegram_delivered") or 0) + 1
    return True


def _request_json(url: str, method: str = "GET", body: object | None = None) -> dict[str, Any]:
    raw_body = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=raw_body, method=method, headers=_headers())
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else {}


def ensure_rule() -> None:
    current = _request_json(RULES_URL)
    rows = current.get("data") if isinstance(current.get("data"), list) else []
    for row in rows:
        if str(row.get("tag") or "") == RULE_TAG and str(row.get("value") or "") == RULE_VALUE:
            return
    _request_json(RULES_URL, "POST", {"add": [{"value": RULE_VALUE, "tag": RULE_TAG}]})


def stream_once() -> None:
    ensure_rule()
    req = urllib.request.Request(STREAM_URL, headers=_headers())
    state = _load_state()
    with urllib.request.urlopen(req, timeout=90) as response:
        STATUS["stream_connected"] = True
        STATUS["last_error"] = None
        for raw in response:
            STATUS["last_stream_line_at"] = _iso_now()
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            for event in parse_stream_payload(payload):
                _send_event(event, state)
    STATUS["stream_connected"] = False


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/health", "/healthz"}:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(STATUS, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _health_server() -> None:
    port = int(os.getenv("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), _Health).serve_forever()


def run_forever() -> None:
    STATUS["started_at"] = _iso_now()
    threading.Thread(target=_health_server, daemon=True).start()
    backoff = 2
    while True:
        try:
            stream_once()
            backoff = 2
        except urllib.error.HTTPError as exc:
            STATUS["stream_connected"] = False
            STATUS["last_error"] = f"X_HTTP_{exc.code}"
        except Exception as exc:
            STATUS["stream_connected"] = False
            STATUS["last_error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
        time.sleep(backoff)
        backoff = min(60, backoff * 2)


if __name__ == "__main__":
    run_forever()
