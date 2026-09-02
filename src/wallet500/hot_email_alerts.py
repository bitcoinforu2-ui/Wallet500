from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

HOT_MIN_SCORE = 75
MIN_MARKET_AGE_DAYS = 180
MIN_LIQUIDITY_USD = 50_000.0
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


def _num(value, default=0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _is_hot(row: dict) -> bool:
    """Email is a production-adjacent notification surface: fail closed.

    It consumes only unified REAL ALERT rows and independently rechecks veteran
    age, exact identity/pair and liquidity so a malformed upstream row cannot
    become a HOT email from CEX symbol/score alone.
    """
    return (
        row.get("status") == "REAL_ALERT"
        and row.get("actionable_research_alert") is True
        and row.get("exact_identity_verified") is True
        and row.get("exact_pair_verified") is True
        and row.get("market_age_verified") is True
        and int(row.get("market_age_days") or 0) >= MIN_MARKET_AGE_DAYS
        and _num(row.get("liquidity_usd")) >= MIN_LIQUIDITY_USD
        and _num(row.get("score")) >= HOT_MIN_SCORE
    )


def _exact_dex_identity(row: dict) -> dict:
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    dex = str(row.get("dex") or "").strip()
    url = str(row.get("dex_url") or row.get("url") or row.get("dexscreener_url") or "").strip()
    verified = bool(token and pair and row.get("exact_identity_verified") is True and row.get("exact_pair_verified") is True)
    return {
        "verified": verified,
        "token_address": token or None,
        "pair_address": pair or None,
        "dex": dex or None,
        "dexscreener_url": url or None,
    }


def _fingerprint(row: dict) -> str:
    chain = str(row.get("chain") or "UNKNOWN").lower()
    token = str(row.get("token_address") or "UNKNOWN").lower()
    pair = str(row.get("pair_address") or "UNKNOWN").lower()
    first_alert = str(row.get("first_alert_at") or "n/a")
    return f"{chain}:{token}:{pair}:{first_alert}"


def _build_message(row: dict, recipient: str, sender: str) -> EmailMessage:
    symbol = str(row.get("symbol") or "UNKNOWN")
    score = _num(row.get("score"))
    identity = _exact_dex_identity(row)
    subject = f"🔥 Wallet500 REAL HOT: {symbol} · {score:.0f}/100"
    lanes = ", ".join(row.get("source_lanes") or []) or "n/a"
    blockers = ", ".join(row.get("blockers") or []) or "none"
    body = f"""Wallet500 strict veteran-token REAL ALERT

Symbol: {symbol}
Score: {score:.0f}/100
Status: REAL ALERT — RESEARCH ONLY
Market age: ≥{int(row.get('market_age_days') or 0)} days ✅
Liquidity: ${_num(row.get('liquidity_usd')):,.2f}
Independent lanes: {int(row.get('source_lane_count') or 0)}
Sources: {lanes}
Blockers: {blockers}
First alert: {row.get('first_alert_at') or 'n/a'}

Exact DEX identity
Chain: {row.get('chain') or 'n/a'}
Token / Contract / Mint: {identity['token_address'] or 'NOT VERIFIED'}
Exact Pair: {identity['pair_address'] or 'NOT VERIFIED'}
DEX: {identity['dex'] or 'n/a'}
DEX URL: {identity['dexscreener_url'] or 'n/a'}
Price reference: {row.get('price_usd') if row.get('price_usd') is not None else 'n/a'}

This email is emitted only from data/real-alerts.json after exact identity, exact pair, verified market age >=180d and liquidity >=$50K are independently rechecked. It is research output, not a guarantee of profit or an automatic trade instruction.

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
    feed = _load(out / "real-alerts.json", {})
    alerts = feed.get("alerts") if isinstance(feed, dict) else []
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
        "version": 2,
        "updated_at": now,
        "recipient": recipient,
        "configured": configured,
        "source": "real-alerts.json",
        "hot_rule": {
            "min_score": HOT_MIN_SCORE,
            "market_age_verified": True,
            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "minimum_liquidity_usd": MIN_LIQUIDITY_USD,
            "exact_identity_required": True,
            "exact_pair_required": True,
            "real_alert_status_required": True,
        },
        "hot_count": len(hot),
        "delivered_count": len(delivered),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "delivered": delivered,
        "skipped": skipped,
        "errors": errors,
        "identity_policy": "NEVER_EMAIL_FROM_CEX_SYMBOL_OR_SCORE_ALONE",
    }
    _write(out / "hot-email-alert-report.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
