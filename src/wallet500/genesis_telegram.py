from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .genesis_radar import PAPER_ENTRY_USD


def _data_dir() -> Path:
    return Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _send(token: str, chat_id: str, text: str) -> None:
    body = urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError("TELEGRAM_SEND_FAILED")


def _fmt_money(value) -> str:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.4f}" if v < 1 else f"${v:.2f}"


def _message(entry: dict, candidate: dict | None) -> str:
    candidate = candidate or {}
    created = str(entry.get("created_at") or "")
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        stamp = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        stamp = created or "unknown"
    signals = ", ".join(entry.get("entry_acceleration_signals") or []) or "—"
    symbol = entry.get("symbol") or candidate.get("symbol") or "NEW TOKEN"
    mode = entry.get("paper_mode") or "PAPER"
    warning = "VERIFIED safety gates" if mode == "VERIFIED_PAPER" else "SHADOW research — LP/critical evidence not fully verified"
    return (
        f"🧪 GENESIS PAPER ${PAPER_ENTRY_USD:.0f} • NEW\n"
        f"🕒 {stamp}\n"
        f"🪙 {symbol} | {str(entry.get('chain') or '').upper()}\n"
        f"Mode: {mode}\n"
        f"Genesis: {entry.get('entry_genesis_score')} | Shadow: {entry.get('entry_shadow_score')}\n"
        f"Age: {entry.get('entry_age_minutes')}m\n"
        f"Entry: {_fmt_money(entry.get('entry_price_usd'))}\n"
        f"Liquidity: {_fmt_money(entry.get('entry_liquidity_usd'))}\n"
        f"Holders: {entry.get('entry_holders') if entry.get('entry_holders') is not None else '—'}\n"
        f"Top10: {entry.get('entry_top10_pct') if entry.get('entry_top10_pct') is not None else '—'}%\n"
        f"Signals: {signals}\n"
        f"⚠️ PAPER ONLY — no real-money buy. {warning}\n"
        f"DEX: {entry.get('dex_url') or candidate.get('url') or '—'}"
    )


def run(data_dir: Path | None = None, now: datetime | None = None) -> dict:
    data_dir = data_dir or _data_dir()
    now = now or datetime.now(timezone.utc)
    radar = _load(data_dir / "genesis-radar.json", {})
    state_path = data_dir / "genesis-alert-state.json"
    state = _load(state_path, {"version": 1, "sent": {}})
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}

    token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    configured = bool(token and chat_id)
    candidates = {x.get("candidate_key"): x for x in (radar.get("candidates") or []) if isinstance(x, dict)}

    attempted = 0
    delivered = 0
    failures = []
    for entry in radar.get("new_paper_entries") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "")
        if not entry_id or entry_id in sent:
            continue
        try:
            created = datetime.fromisoformat(str(entry.get("created_at") or "").replace("Z", "+00:00"))
            age_seconds = (now - created.astimezone(timezone.utc)).total_seconds()
            if age_seconds > 90 * 60:
                continue
        except Exception:
            continue
        attempted += 1
        if not configured:
            failures.append({"entry_id": entry_id, "reason": "TELEGRAM_SECRETS_MISSING"})
            continue
        try:
            _send(token, chat_id, _message(entry, candidates.get(entry.get("candidate_key"))))
            sent[entry_id] = {"sent_at": now.isoformat(), "candidate_key": entry.get("candidate_key")}
            delivered += 1
        except Exception as exc:
            failures.append({"entry_id": entry_id, "reason": f"{type(exc).__name__}:{str(exc)[:120]}"})

    state = {
        "version": 1,
        "updated_at": now.isoformat(),
        "configured": configured,
        "attempted": attempted,
        "delivered": delivered,
        "failures": failures[-20:],
        "sent": sent,
    }
    _write(state_path, state)
    print("GENESIS_TELEGRAM", {"configured": configured, "attempted": attempted, "delivered": delivered})
    return state


def main() -> None:
    run()


if __name__ == "__main__":
    main()
