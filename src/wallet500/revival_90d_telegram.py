from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .telegram_alerts import _fmt_israel_time, _fmt_money, _load, _send, _write

MODE = "RESEARCH_ONLY_REVIVAL_90D_15K_TELEGRAM_V1"
SOURCE = "revival-radar.json"
STATE = "revival-90d-telegram-state.json"
REPORT = "revival-90d-telegram-report.json"
MIN_AGE_DAYS = 90.0
MIN_LIQUIDITY_USD = 15_000.0
MIN_REVIVAL_SCORE = 65.0
MIN_VOLUME_H1_USD = 15_000.0
MIN_TXNS_H1 = 50


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _norm_chain(v: Any) -> str:
    c = str(v or "").lower()
    if c in {"eth", "ethereum"}:
        return "ethereum"
    if c in {"bnb", "bsc"}:
        return "bsc"
    if c in {"sol", "solana"}:
        return "solana"
    return c


def _same_identity(chain: str, left: Any, right: Any) -> bool:
    a, b = str(left or ""), str(right or "")
    if not a or not b:
        return False
    return a.lower() == b.lower() if chain in {"ethereum", "bsc", "arbitrum", "base"} else a == b


def _created_at(row: dict) -> datetime | None:
    raw = row.get("pair_created_at")
    if raw is None:
        return None
    try:
        x = float(raw)
        if x > 10_000_000_000:
            x /= 1000.0
        return datetime.fromtimestamp(x, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _eligibility(row: object, now: datetime) -> tuple[bool, dict[str, Any]]:
    if not isinstance(row, dict):
        return False, {"blockers": ["ROW_INVALID"]}
    chain = _norm_chain(row.get("chain"))
    token = str(row.get("token") or row.get("token_address") or "")
    base = str(row.get("base_token_address") or "")
    pair = str(row.get("pair_address") or "")
    created = _created_at(row)
    age = (now - created).total_seconds() / 86400.0 if created else 0.0
    liq = _f(row.get("liquidity_usd"))
    score = _f(row.get("revival_score"))
    volume = _f(row.get("volume_h1"))
    buys = _i(row.get("buys_h1"))
    sells = _i(row.get("sells_h1"))
    txns = buys + sells
    blockers: list[str] = []
    if not chain or not token or not pair:
        blockers.append("IDENTITY_OR_PAIR_MISSING")
    if not _same_identity(chain, token, base):
        blockers.append("BASE_TOKEN_IDENTITY_NOT_VERIFIED")
    if created is None or age < MIN_AGE_DAYS:
        blockers.append("PAIR_AGE_LT_90D_OR_UNKNOWN")
    if liq < MIN_LIQUIDITY_USD:
        blockers.append("LIQUIDITY_LT_15K")
    if score < MIN_REVIVAL_SCORE:
        blockers.append("REVIVAL_SCORE_LT_65")
    if volume < MIN_VOLUME_H1_USD:
        blockers.append("VOLUME_H1_LT_15K")
    if txns < MIN_TXNS_H1:
        blockers.append("TXNS_H1_LT_50")
    risk = str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper()
    if risk in {"HIGH", "CRITICAL"}:
        blockers.append("HIGH_OR_CRITICAL_RISK")
    return not blockers, {
        "chain": chain,
        "token_address": token,
        "pair_address": pair,
        "market_age_days": round(age, 2),
        "liquidity_usd": liq,
        "revival_score": score,
        "volume_h1_usd": volume,
        "txns_h1": txns,
        "blockers": blockers,
    }


def _key(meta: dict[str, Any]) -> str:
    chain = str(meta.get("chain") or "")
    token = str(meta.get("token_address") or "")
    pair = str(meta.get("pair_address") or "")
    if chain in {"ethereum", "bsc", "arbitrum", "base"}:
        token, pair = token.lower(), pair.lower()
    return f"{chain}:{token}:{pair}"


def _event_id(key: str, sent_at: str) -> str:
    return "R90-" + hashlib.sha256(f"{key}|{sent_at}".encode()).hexdigest()[:12].upper()


def _message(row: dict, meta: dict[str, Any], sent_at: str, event_id: str) -> str:
    symbol = str(row.get("base_token_symbol") or row.get("symbol") or "UNKNOWN")
    url = str(row.get("url") or row.get("dex_url") or "")
    lines = [
        "🔥🔥🔥 REVIVAL 90D / 15K — WALLET500",
        "🆕 התעוררות חדשה במסלול המורחב",
        f"📅 זמן התראה (ישראל): {_fmt_israel_time(sent_at)}",
        f"🧾 Alert ID: {event_id}",
        "⚠️ RESEARCH ONLY — MANUAL DECISION — NO AUTOMATIC TRADE",
        f"Token: {symbol}",
        f"Chain: {str(meta['chain']).upper().replace('BSC', 'BNB')}",
        f"Contract: {meta['token_address']}",
        f"Pair: {meta['pair_address']}",
        "Exact token identity: VERIFIED ✅",
        "Exact pair: LOCKED ✅",
        f"Market age: {meta['market_age_days']:.1f}d ✅ min 90d",
        f"Liquidity: {_fmt_money(meta['liquidity_usd'])} ✅ min $15K",
        f"Revival score: {meta['revival_score']:.1f}/100 ✅ min 65",
        f"Volume H1: {_fmt_money(meta['volume_h1_usd'])} ✅ min $15K",
        f"Activity H1: {meta['txns_h1']} tx ✅ min 50",
        "Production 180d/$50K gate: UNCHANGED",
        "Verified Intelligence. The Pure Truth.",
    ]
    if url:
        lines.append(f"🔗 OPEN DEX: {url}")
    return "\n".join(lines)


def run(output_dir: str | None = None, now: datetime | None = None) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    source = _load(out / SOURCE, [])
    rows = [x for x in source if isinstance(x, dict)] if isinstance(source, list) else []

    eligible: list[tuple[dict, dict]] = []
    for row in rows:
        ok, meta = _eligibility(row, now_dt)
        if ok:
            eligible.append((row, meta))

    state = _load(out / STATE, {})
    if not isinstance(state, dict):
        state = {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}
    active = {_key(meta) for _, meta in eligible}

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(token and chat_id)
    delivered, errors = [], []

    if configured:
        for row, meta in eligible:
            key = _key(meta)
            prev = sent.get(key) if isinstance(sent.get(key), dict) else {}
            if prev.get("active") is True:
                continue
            event_id = _event_id(key, now_iso)
            try:
                mid, attempts = _send(token, chat_id, _message(row, meta, now_iso, event_id))
                info = {
                    "active": True,
                    "sent_at": now_iso,
                    "event_id": event_id,
                    "telegram_message_id": mid,
                    "attempts": attempts,
                    "symbol": row.get("base_token_symbol") or row.get("symbol"),
                    "pair_address": meta["pair_address"],
                }
                sent[key] = info
                delivered.append({"key": key, **info})
            except Exception as exc:
                errors.append({"key": key, "error": f"{type(exc).__name__}: {exc}"[:300]})

        for key, info in list(sent.items()):
            if isinstance(info, dict) and info.get("active") is True and key not in active:
                info["active"] = False
                info["cleared_at"] = now_iso
                sent[key] = info

        _write(out / STATE, {"version": 1, "updated_at": now_iso, "sent": sent})

    report = {
        "version": 1,
        "mode": MODE,
        "updated_at": now_iso,
        "configured": configured,
        "source": SOURCE,
        "source_rows": len(rows),
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "delivered": delivered,
        "errors": errors,
        "truth_contract": {
            "research_only": True,
            "production_portfolio_impact": "NONE",
            "production_gate_changed": False,
            "automatic_buy": False,
            "minimum_pair_age_days": MIN_AGE_DAYS,
            "minimum_liquidity_usd": MIN_LIQUIDITY_USD,
            "minimum_revival_score": MIN_REVIVAL_SCORE,
            "minimum_volume_h1_usd": MIN_VOLUME_H1_USD,
            "minimum_txns_h1": MIN_TXNS_H1,
            "exact_pair_required": True,
            "exact_base_token_identity_required": True,
            "notification_marker": "🔥🔥🔥",
            "dedupe": "one alert per exact chain+token+pair active transition; re-arm after leaving eligibility",
            "no_hindsight": True,
        },
    }
    _write(out / REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
