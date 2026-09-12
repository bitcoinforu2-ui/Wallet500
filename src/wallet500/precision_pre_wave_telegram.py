from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path("data")
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fmt_money(v) -> str:
    try:
        n = float(v)
    except Exception:
        return "n/a"
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.1f}K"
    if abs(n) >= 1:
        return f"${n:.4f}".rstrip("0").rstrip(".")
    return f"${n:.8f}".rstrip("0").rstrip(".")


def _fmt_time(v) -> str:
    raw = str(v or "").strip()
    if not raw:
        return "n/a"
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return raw


def _key(row: dict) -> str:
    return ":".join([
        str(row.get("chain") or "").lower(),
        str(row.get("token_address") or "").lower(),
        str(row.get("pair_address") or "").lower(),
    ])


def _event_id(key: str, sent_at: str) -> str:
    return hashlib.sha256(f"PRECISION_PRE_WAVE|{key}|{sent_at}".encode()).hexdigest()[:16]


def _message(row: dict, sent_at: str, event_id: str) -> str:
    missing = row.get("only_missing_gate") or "STRONG_DECISION_LANE"
    lines = [
        "🔥🔥🔥 PRECISION PRE-WAVE — WALLET500",
        "⚠️ MANUAL REVIEW ONLY — NOT A BUY ORDER — NO AUTOMATIC TRADE",
        f"📅 נשלח (ישראל): {_fmt_time(sent_at)}",
        f"🕒 אות מוקדם ראשון: {_fmt_time(row.get('first_alert_at'))}",
        f"🧾 Alert ID: {event_id}",
        f"Token: {row.get('symbol')}",
        f"Chain: {str(row.get('chain') or '').upper()}",
        f"Contract: {row.get('token_address')}",
        f"Pair: {row.get('pair_address')}",
        "Exact identity + pair: PASS ✅",
        "Readiness: 6/7",
        f"Only missing: {missing}",
        f"Early signal price: {_fmt_money(row.get('first_alert_reference_price'))}",
        f"Current price: {_fmt_money(row.get('current_price_usd'))}",
        f"Move from early signal: {row.get('move_from_first_alert_pct') if row.get('move_from_first_alert_pct') is not None else 'n/a'}%",
        f"Current CEX 24H move: {row.get('current_change_24h_max_pct') if row.get('current_change_24h_max_pct') is not None else 'n/a'}%",
        f"Liquidity: {_fmt_money(row.get('execution_pool_liquidity_usd'))}",
        f"DEX Volume 1H: {_fmt_money(row.get('dex_volume_h1'))}",
        f"Turnover 1H: {float(row.get('turnover_h1') or 0):.3f}x",
        f"Buys/Sells 1H: {int(row.get('buys_h1') or 0)}/{int(row.get('sells_h1') or 0)}",
        f"Independent source lanes: {int(row.get('source_lane_count') or 0)}",
        f"Timing: {row.get('timing')}",
        "Verified Intelligence. The Pure Truth.",
    ]
    if row.get("dex_url"):
        lines.append(f"🔗 OPEN DEX: {row.get('dex_url')}")
    return "\n".join(lines)


def _send(token: str, chat_id: str, text: str) -> int | None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
        if payload.get("ok") is not True:
            raise RuntimeError("Telegram API returned ok=false")
        result = payload.get("result") or {}
        return int(result["message_id"]) if result.get("message_id") is not None else None


def run(data_dir: str | Path = DATA) -> dict:
    data = Path(data_dir)
    payload = _load(data / "precision-pre-wave.json", {})
    state_path = data / "precision-pre-wave-telegram-state.json"
    report_path = data / "precision-pre-wave-telegram-report.json"
    state = _load(state_path, {})
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        report = {"status": "SKIPPED_UNCONFIGURED", "delivered_count": 0, "eligible_count": 0}
        print(json.dumps(report, ensure_ascii=False))
        return report

    now = datetime.now(timezone.utc).isoformat()
    delivered, eligible, errors = [], [], []
    active = set()
    for row in payload.get("candidates") or []:
        if not isinstance(row, dict) or row.get("user_alert_eligible") is not True:
            continue
        if row.get("manual_review_only") is not True or row.get("automatic_buy") is not False or row.get("automatic_trade") is not False:
            continue
        if row.get("timing") not in {"EARLY_REVIEW", "EXTENDED_WAIT_RETEST"}:
            continue
        key = _key(row)
        if not key.strip(":"):
            continue
        active.add(key)
        eligible.append({"symbol": row.get("symbol"), "key": key, "timing": row.get("timing"), "dex_url": row.get("dex_url")})
        previous = sent.get(key) if isinstance(sent.get(key), dict) else {}
        if previous.get("active") is True:
            continue
        event_id = _event_id(key, now)
        try:
            msg_id = _send(token, chat_id, _message(row, now, event_id))
            sent[key] = {"active": True, "sent_at": now, "alert_event_id": event_id, "telegram_message_id": msg_id, "timing": row.get("timing")}
            delivered.append({"symbol": row.get("symbol"), "key": key, "timing": row.get("timing"), "alert_event_id": event_id, "telegram_message_id": msg_id})
        except Exception as exc:
            errors.append({"symbol": row.get("symbol"), "key": key, "error": f"{type(exc).__name__}: {exc}"[:300]})

    for key, info in list(sent.items()):
        if isinstance(info, dict) and info.get("active") is True and key not in active:
            info["active"] = False
            info["cleared_at"] = now
            sent[key] = info

    report = {
        "version": 1,
        "updated_at": now,
        "configured": True,
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "eligible": eligible,
        "delivered": delivered,
        "errors": errors,
        "policy": {
            "manual_review_only": True,
            "late_do_not_chase_never_sent": True,
            "research_only_noise_not_sent": True,
            "real_alert_gate_unchanged": True,
            "dedupe": "exact chain+token+pair; independent of canonical REAL_ALERT so later 7/7 still fires",
        },
    }
    _write(state_path, {"updated_at": now, "sent": sent})
    _write(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
