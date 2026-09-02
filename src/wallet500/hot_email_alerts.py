from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

HOT_MIN_SCORE = 75
HOT_MIN_CONFIRMATIONS = 2
DEFAULT_RECIPIENT = "bitcoinforu2@gmail.com"


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_hot(row: dict) -> bool:
    score = float(row.get("cex_revival_score") or row.get("score") or 0)
    confirmations = int(row.get("confirmations") or 0)
    return score >= HOT_MIN_SCORE and confirmations >= HOT_MIN_CONFIRMATIONS


def _best_market(row: dict) -> dict:
    markets = [m for m in (row.get("markets") or []) if isinstance(m, dict)]
    if not markets:
        return {}
    return max(markets, key=lambda m: float(m.get("volume_24h") or 0))


def _exact_dex_identity(row: dict) -> dict:
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    locked = str(row.get("locked_pair_address") or "").strip()
    dex = str(row.get("dex") or "").strip()
    url = str(row.get("url") or row.get("dexscreener_url") or "").strip()
    locked_ok = bool(pair and locked and pair.lower() == locked.lower() and row.get("pair_identity_locked") is True)
    verified = bool(token and locked_ok and dex)
    return {
        "verified": verified,
        "token_address": token or None,
        "pair_address": pair or None,
        "dex": dex or None,
        "dexscreener_url": url or None,
    }


def _milestone_time(row: dict, key: str) -> str:
    milestone = (row.get("milestones") or {}).get(key) or {}
    return str(milestone.get("observed_at") or "n/a")


def _fingerprint(row: dict) -> str:
    symbol = str(row.get("symbol") or "UNKNOWN")
    first_alert = _milestone_time(row, "first_alert")
    return f"{symbol}:{first_alert}"


def _build_message(row: dict, recipient: str, sender: str) -> EmailMessage:
    symbol = str(row.get("symbol") or "UNKNOWN")
    score = float(row.get("cex_revival_score") or row.get("score") or 0)
    confirmations = int(row.get("confirmations") or 0)
    market = _best_market(row)
    identity = _exact_dex_identity(row)
    status = "EXACT DEX VERIFIED" if identity["verified"] else "DEX IDENTITY UNRESOLVED — RESEARCH ONLY"
    subject = f"🔥 Wallet500 HOT: {symbol} · {score:.0f}/100"
    reasons = "\n".join(f"- {x}" for x in (row.get("reasons") or [])[:6]) or "- Active HOT signal"
    exchanges = ", ".join(row.get("exchanges") or []) or "n/a"
    body = f"""Wallet500 HOT alert

Symbol: {symbol}
Score: {score:.0f}/100
Confirmations: {confirmations}
Archetype: {row.get('archetype') or 'n/a'}
Status: {status}

Current CEX reference
Exchange: {market.get('exchange') or 'n/a'}
Price: {market.get('price') if market.get('price') is not None else 'n/a'}
24h change: {row.get('change_24h_max_pct') if row.get('change_24h_max_pct') is not None else 'n/a'}%
Volume 24h: {market.get('volume_24h') if market.get('volume_24h') is not None else 'n/a'}
Exchanges: {exchanges}

Detection timeline
FIRST SEEN: {_milestone_time(row, 'first_seen')}
FIRST ANOMALY: {_milestone_time(row, 'first_anomaly')}
FIRST ALERT: {_milestone_time(row, 'first_alert')}

Exact DEX identity
Token / Contract / Mint: {identity['token_address'] or 'NOT VERIFIED'}
Exact Pair: {identity['pair_address'] or 'NOT VERIFIED'}
DEX: {identity['dex'] or 'NOT VERIFIED'}
DexScreener: {identity['dexscreener_url'] or 'NOT VERIFIED'}

Why HOT
{reasons}

IMPORTANT: If exact DEX identity is NOT VERIFIED, Wallet500 has not proven which on-chain token/pair corresponds to the CEX symbol. Do not infer or trade from symbol matching alone.

Verified Intelligence. The Pure Truth.
"""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def run() -> dict:
    out = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
    radar = _load(out / "cex-revival-radar.json", {})
    alerts = radar.get("alerts") if isinstance(radar, dict) else []
    if not isinstance(alerts, list):
        alerts = []

    recipient = os.getenv("HOT_ALERT_EMAIL_TO", DEFAULT_RECIPIENT).strip() or DEFAULT_RECIPIENT
    sender = os.getenv("HOT_ALERT_SMTP_USER", "").strip()
    password = os.getenv("HOT_ALERT_SMTP_PASSWORD", "").strip()
    host = os.getenv("HOT_ALERT_SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("HOT_ALERT_SMTP_PORT", "465"))
    configured = bool(recipient and sender and password)

    state_path = out / "hot-email-alert-state.json"
    state = _load(state_path, {})
    if not isinstance(state, dict):
        state = {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}

    now = datetime.now(timezone.utc).isoformat()
    hot = [row for row in alerts if isinstance(row, dict) and _is_hot(row)]
    delivered, skipped, errors = [], [], []

    smtp = None
    try:
        if configured:
            smtp = smtplib.SMTP_SSL(host, port, timeout=20)
            smtp.login(sender, password)
        for row in hot:
            fp = _fingerprint(row)
            symbol = str(row.get("symbol") or "UNKNOWN")
            if fp in sent:
                skipped.append({"symbol": symbol, "reason": "already_sent"})
                continue
            if not configured:
                skipped.append({"symbol": symbol, "reason": "smtp_not_configured"})
                continue
            try:
                smtp.send_message(_build_message(row, recipient, sender))
                sent[fp] = {"symbol": symbol, "sent_at": now}
                delivered.append({"symbol": symbol, "fingerprint": fp})
            except Exception as exc:
                errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"[:300]})
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass

    if len(sent) > 5000:
        sent = dict(list(sent.items())[-5000:])
    _write(state_path, {"updated_at": now, "sent": sent})
    report = {
        "version": 1,
        "updated_at": now,
        "recipient": recipient,
        "configured": configured,
        "hot_rule": {"min_score": HOT_MIN_SCORE, "min_confirmations": HOT_MIN_CONFIRMATIONS},
        "hot_count": len(hot),
        "delivered_count": len(delivered),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "delivered": delivered,
        "skipped": skipped,
        "errors": errors,
        "identity_policy": "NEVER_INFER_DEX_TOKEN_OR_PAIR_FROM_SYMBOL_ONLY",
    }
    _write(out / "hot-email-alert-report.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
