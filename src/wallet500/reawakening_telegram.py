from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .telegram_alerts import _fmt_money, _send

SOURCE = "reawakening-shadow.json"
STATE = "reawakening-telegram-state.json"
REPORT = "reawakening-telegram-report.json"
MAX_TRIGGER_AGE_MINUTES = 30.0


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dt(value):
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fingerprint(row: dict) -> str:
    return f"{row.get('token_key')}:{row.get('triggered_at')}:{row.get('pair_address')}"


def _message(row: dict) -> str:
    chain = str(row.get("chain") or "unknown").upper().replace("BSC", "BNB")
    metrics = row.get("metrics") or {}
    token = str(row.get("token") or "unknown")
    pair = str(row.get("pair_address") or "unknown")
    dex = f"https://dexscreener.com/{str(row.get('chain') or '').lower()}/{pair}"
    return "\n".join([
        "🔥 WALLET500 — SURVIVOR REAWAKENING",
        "⚠️ התראת מחקר חמה — עדיין לא BUY",
        f"רשת: {chain}",
        f"Token: {token}",
        f"Exact Pair: {pair}",
        f"מחיר טריגר: {_fmt_money(row.get('price_usd'))}",
        f"נזילות: {_fmt_money(metrics.get('liquidity_usd'))}",
        f"תשואה מ-T0 בעת הטריגר: {float(metrics.get('return_pct') or 0):+.1f}%",
        f"Turnover 1H: {float(metrics.get('turnover_h1') or 0):.2f}x",
        f"Buy/Sell 1H: {float(metrics.get('buy_sell_ratio_h1') or 0):.2f}x",
        f"פעילות 1H: {int(metrics.get('activity_h1') or 0)}",
        f"אישורים רצופים: {int(row.get('confirmation_observations') or 0)}",
        "Exact-pair survivor: מאומת ✅",
        "Holder/Cluster · LP · Exit Depth: עדיין דורשים אימות",
        "החסם המקורי לא בוטל; זהו מסלול Reawakening נפרד.",
        f"DexScreener: {dex}",
    ])


def run(output_dir: str | None = None, now: datetime | None = None, sender=_send) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    payload = _load(out / SOURCE, {})
    state = _load(out / STATE, {"sent": {}})
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(bot_token and chat_id)
    reference = now or datetime.now(timezone.utc)
    delivered = []
    stale = []
    errors = []
    eligible = []
    for row in payload.get("targets") or []:
        if not isinstance(row, dict) or row.get("status") != "SURVIVOR_REAWAKENING_SHADOW_WATCH":
            continue
        triggered = _dt(row.get("triggered_at"))
        if triggered is None:
            continue
        age_min = max(0.0, (reference - triggered).total_seconds() / 60.0)
        fp = _fingerprint(row)
        if age_min > MAX_TRIGGER_AGE_MINUTES:
            stale.append({"fingerprint": fp, "age_minutes": round(age_min, 2)})
            continue
        eligible.append({"fingerprint": fp, "age_minutes": round(age_min, 2)})
        if fp in sent or not configured:
            continue
        try:
            sender(bot_token, chat_id, _message(row))
            sent[fp] = {"sent_at": reference.isoformat(), "token_key": row.get("token_key")}
            delivered.append({"fingerprint": fp, "token_key": row.get("token_key")})
        except Exception as exc:
            errors.append({"fingerprint": fp, "error": f"{type(exc).__name__}: {exc}"[:300]})
    if len(sent) > 5000:
        sent = dict(list(sent.items())[-5000:])
    report = {
        "version": 1,
        "updated_at": reference.isoformat(),
        "source": SOURCE,
        "configured": configured,
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "stale_suppressed_count": len(stale),
        "error_count": len(errors),
        "eligible": eligible,
        "delivered": delivered,
        "errors": errors,
        "policy": {
            "only_status": "SURVIVOR_REAWAKENING_SHADOW_WATCH",
            "max_trigger_age_minutes": MAX_TRIGGER_AGE_MINUTES,
            "dedupe": "one message per token+triggered_at+exact_pair fingerprint",
            "historical_triggers_are_never_sent_as_new alerts": True,
            "classification": "RESEARCH_HOT_NOT_BUY",
        },
    }
    _write(out / STATE, {"version": 1, "updated_at": reference.isoformat(), "sent": sent})
    _write(out / REPORT, report)
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
