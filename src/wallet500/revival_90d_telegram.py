from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import revival_deep_intelligence as deep_intelligence
from .telegram_alerts import _fmt_israel_time, _fmt_money, _load, _send, _write

MODE = "ACTIONABLE_REVIVAL_90D_15K_REAL_ALERT_V2"
SOURCE = "revival-1000-latest.json"
STATE = "revival-90d-telegram-state.json"
REPORT = "revival-90d-telegram-report.json"
MIN_AGE_DAYS = 90.0
MIN_LIQUIDITY_USD = 15_000.0
MIN_REVIVAL_SCORE = 65.0
MIN_VOLUME_H1_USD = 15_000.0
MIN_TXNS_H1 = 30


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _i(v: Any, d: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def _norm_chain(v: Any) -> str:
    c = str(v or "").lower()
    return "ethereum" if c in {"eth", "ethereum"} else "bsc" if c in {"bnb", "bsc"} else "solana" if c in {"sol", "solana"} else c


def _same_identity(chain: str, a: Any, b: Any) -> bool:
    a, b = str(a or ""), str(b or "")
    return bool(a and b and (a.lower() == b.lower() if chain in {"ethereum", "bsc", "arbitrum", "base"} else a == b))


def _created_at(row: dict) -> datetime | None:
    try:
        x = float(row.get("pair_created_at"))
        x = x / 1000.0 if x > 10_000_000_000 else x
        return datetime.fromtimestamp(x, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _expanded_identity_verified(row: dict, chain: str, token: str, pair: str) -> bool:
    return bool(
        chain == "solana"
        and token
        and pair
        and row.get("network_verified") is True
        and row.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
        and str(row.get("dex_pair_address") or "") == pair
    )


def _static_prefilter(row: object, now: datetime) -> bool:
    """Cheap fail-closed filter before any live provider call."""
    if not isinstance(row, dict):
        return False
    chain = _norm_chain(row.get("chain") or row.get("network"))
    token = str(row.get("token") or row.get("token_address") or "")
    base = str(row.get("base_token_address") or "")
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or "")
    if not chain or not token or not pair:
        return False
    if not (bool(base and _same_identity(chain, token, base)) or _expanded_identity_verified(row, chain, token, pair)):
        return False

    created = _created_at(row)
    verified_age = row.get("market_age_verified") is True
    explicit_age = _f(row.get("market_age_min_days"), -1.0)
    age = explicit_age if verified_age and explicit_age >= 0 else ((now - created).total_seconds() / 86400.0 if created else 0.0)
    if age < MIN_AGE_DAYS:
        return False
    if _f(row.get("liquidity_usd") or row.get("dex_pair_liquidity_usd")) < MIN_LIQUIDITY_USD:
        return False
    if _f(row.get("revival_score") or row.get("revival_score_verified")) < MIN_REVIVAL_SCORE:
        return False
    display_gate = row.get("active_display_gate")
    if isinstance(display_gate, dict) and display_gate.get("pass") is not True:
        return False
    if str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper() in {"HIGH", "CRITICAL"}:
        return False
    return True


def _eligibility(row: object, now: datetime) -> tuple[bool, dict[str, Any]]:
    if not isinstance(row, dict):
        return False, {"blockers": ["ROW_INVALID"]}

    chain = _norm_chain(row.get("chain") or row.get("network"))
    token = str(row.get("token") or row.get("token_address") or "")
    base = str(row.get("base_token_address") or "")
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or "")

    created = _created_at(row)
    verified_age = row.get("market_age_verified") is True
    explicit_age = _f(row.get("market_age_min_days"), -1.0)
    age = explicit_age if verified_age and explicit_age >= 0 else ((now - created).total_seconds() / 86400.0 if created else 0.0)

    liq = _f(row.get("liquidity_usd") or row.get("dex_pair_liquidity_usd"))
    score = _f(row.get("revival_score") or row.get("revival_score_verified"))
    flow = row.get("order_flow_absorption") or {}
    live = row.get("live_h1") or {}
    vol = _f(row.get("volume_h1") or live.get("volume_h1") or flow.get("volume_h1_usd"))
    buys = _i(row.get("buys_h1") or live.get("buys_h1") or flow.get("buys_h1"))
    sells = _i(row.get("sells_h1") or live.get("sells_h1") or flow.get("sells_h1"))
    tx = buys + sells

    blockers: list[str] = []
    if not chain or not token or not pair:
        blockers.append("IDENTITY_OR_PAIR_MISSING")

    classic_identity = bool(base and _same_identity(chain, token, base))
    expanded_identity = _expanded_identity_verified(row, chain, token, pair)
    if not (classic_identity or expanded_identity):
        blockers.append("BASE_TOKEN_IDENTITY_NOT_VERIFIED")

    if verified_age:
        if age < MIN_AGE_DAYS:
            blockers.append("MARKET_AGE_LT_90D")
    elif created is None or age < MIN_AGE_DAYS:
        blockers.append("PAIR_AGE_LT_90D_OR_UNKNOWN")

    if liq < MIN_LIQUIDITY_USD:
        blockers.append("LIQUIDITY_LT_15K")
    if score < MIN_REVIVAL_SCORE:
        blockers.append("REVIVAL_SCORE_LT_65")
    if vol < MIN_VOLUME_H1_USD:
        blockers.append("VOLUME_H1_LT_15K")
    if tx < MIN_TXNS_H1:
        blockers.append("TXNS_H1_LT_30")

    display_gate = row.get("active_display_gate")
    if isinstance(display_gate, dict) and display_gate.get("pass") is not True:
        blockers.append("ACTIVE_DISPLAY_GATE_NOT_PASSED")

    if str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper() in {"HIGH", "CRITICAL"}:
        blockers.append("HIGH_OR_CRITICAL_RISK")

    return not blockers, {
        "chain": chain,
        "token_address": token,
        "pair_address": pair,
        "market_age_days": round(age, 2),
        "market_age_verified": verified_age or created is not None,
        "liquidity_usd": liq,
        "revival_score": score,
        "volume_h1_usd": vol,
        "buys_h1": buys,
        "sells_h1": sells,
        "txns_h1": tx,
        "blockers": blockers,
    }


def _dex_live(row: dict) -> dict[str, Any]:
    if os.getenv("REVIVAL_90D_LIVE_REFRESH", "1").strip().lower() in {"0", "false", "no"}:
        return {}
    chain = _norm_chain(row.get("chain") or row.get("network"))
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or "").strip()
    if not chain or not pair:
        return {}
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair}"
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500-Revival90D/2.1"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        pairs = payload.get("pairs") or [] if isinstance(payload, dict) else []
        exact = next((x for x in pairs if str(x.get("pairAddress") or "") == pair), None)
        if not isinstance(exact, dict):
            return {}
        txns = (exact.get("txns") or {}).get("h1") or {}
        return {
            "volume_h1": _f((exact.get("volume") or {}).get("h1")),
            "buys_h1": _i(txns.get("buys")),
            "sells_h1": _i(txns.get("sells")),
            "price_usd": _f(exact.get("priceUsd")),
            "liquidity_usd": _f((exact.get("liquidity") or {}).get("usd")),
            "base_token_address": str((exact.get("baseToken") or {}).get("address") or ""),
        }
    except Exception as exc:
        return {"refresh_error": f"{type(exc).__name__}: {exc}"[:240]}


def _with_live(row: dict) -> dict:
    row = dict(row)
    live = _dex_live(row)
    if live and not live.get("refresh_error"):
        expected = str(row.get("token_address") or row.get("token") or "")
        got = str(live.get("base_token_address") or "")
        chain = _norm_chain(row.get("network") or row.get("chain"))
        if not _same_identity(chain, expected, got):
            row["risk_level"] = "CRITICAL"
            row["live_identity_error"] = "DEX_LIVE_BASE_TOKEN_MISMATCH"
        row["live_h1"] = live
        if live.get("liquidity_usd"):
            row["liquidity_usd"] = live["liquidity_usd"]
    elif live.get("refresh_error"):
        row["live_refresh_error"] = live["refresh_error"]
    return row


def _key(m: dict[str, Any]) -> str:
    c = str(m.get("chain") or "")
    t = str(m.get("token_address") or "")
    p = str(m.get("pair_address") or "")
    if c in {"ethereum", "bsc", "arbitrum", "base"}:
        t, p = t.lower(), p.lower()
    return f"{c}:{t}:{p}"


def _event_id(k: str, ts: str) -> str:
    return "R90-" + hashlib.sha256(f"{k}|{ts}".encode()).hexdigest()[:12].upper()


def _message(row: dict, m: dict[str, Any], ts: str, eid: str) -> str:
    symbol = str(row.get("base_token_symbol") or row.get("symbol") or "UNKNOWN")
    url = str(row.get("url") or row.get("dex_url") or row.get("dex_link") or "")
    price = _f((row.get("live_h1") or {}).get("price_usd") or row.get("price_usd"))
    deep = m.get("deep_intelligence") if isinstance(m.get("deep_intelligence"), dict) else {}
    wallet = deep.get("wallet_intel") if isinstance(deep.get("wallet_intel"), dict) else {}
    flow = deep.get("flow_quality") if isinstance(deep.get("flow_quality"), dict) else {}
    liq = deep.get("liquidity_quality") if isinstance(deep.get("liquidity_quality"), dict) else {}
    security = deep.get("contract_security") if isinstance(deep.get("contract_security"), dict) else {}
    fusion = deep.get("intelligence_context") if isinstance(deep.get("intelligence_context"), dict) else {}
    hard = deep.get("hard_blockers") or []
    lines = [
        "🔥🔥🔥 REAL ALERT — REVIVAL 90D / 15K — WALLET500",
        "🆕 התעוררות חדשה שעברה Revival + Deep Intelligence אוטומטי",
        f"📅 זמן התראה (ישראל): {_fmt_israel_time(ts)}",
        f"🧾 Alert ID: {eid}",
        "✅ ACTIONABLE MANUAL DECISION — NO AUTOMATIC TRADE",
        f"Token: {symbol}",
        f"Chain: {str(m['chain']).upper().replace('BSC', 'BNB')}",
        f"Contract: {m['token_address']}",
        f"Pair: {m['pair_address']}",
        "Exact token identity: VERIFIED ✅",
        "Exact pair: LOCKED ✅",
        f"Deep Check: {deep.get('status', 'UNKNOWN')}",
        f"Revival score: {m['revival_score']:.1f}/100",
        f"Confirmation score: {_f(deep.get('confirmation_score')):.1f}/100",
        f"Wallet Intel: {wallet.get('status', 'UNKNOWN')} | Smart Money: {wallet.get('smart_money', 'UNAVAILABLE')}",
        f"Flow Quality: {flow.get('status', 'UNAVAILABLE')}",
        f"Liquidity Quality: {liq.get('status', 'UNAVAILABLE')}",
        f"Contract Security: {security.get('status', 'UNAVAILABLE')}",
        f"Intelligence Fusion: {fusion.get('status', 'NOT_AVAILABLE')}",
        f"Hard Blockers: {'NONE' if not hard else ', '.join(str(x) for x in hard)}",
        f"Decision: {deep.get('decision', 'WATCH — MANUAL REVIEW')}",
        f"Market age: {m['market_age_days']:.1f}d ✅ min 90d",
        f"Liquidity: {_fmt_money(m['liquidity_usd'])} ✅ min $15K",
        f"Volume H1: {_fmt_money(m['volume_h1_usd'])} ✅ min $15K",
        f"Activity H1: {m['txns_h1']} tx ✅ min 30",
        f"Buy/Sell H1: {m['buys_h1']}/{m['sells_h1']}",
        "Canonical Revival lane: 90d / $15K ✅",
        "Flow note: transaction-count imbalance is not claimed as organic USD flow.",
    ]
    if price > 0:
        lines.insert(11, f"Current price: ${price:.10g}")
    if url:
        lines.append(f"🔗 OPEN DEX: {url}")
    return "\n".join(lines)


def _source_rows(src: object) -> list[dict]:
    if isinstance(src, dict):
        rows = src.get("coins") or src.get("alerts") or []
    elif isinstance(src, list):
        rows = src
    else:
        rows = []
    return [x for x in rows if isinstance(x, dict)]


def run(output_dir: str | None = None, now: datetime | None = None) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    src = _load(out / SOURCE, {})
    rows = _source_rows(src)

    baseline_eligible: list[tuple[dict, dict[str, Any]]] = []
    blocked: list[dict[str, Any]] = []
    live_refresh_candidates = 0
    live_refresh_errors = 0
    for raw in rows:
        row = dict(raw)
        if _static_prefilter(row, now_dt):
            live_refresh_candidates += 1
            row = _with_live(row)
            if row.get("live_refresh_error"):
                live_refresh_errors += 1
        ok, m = _eligibility(row, now_dt)
        if ok:
            baseline_eligible.append((row, m))
        else:
            blocked.append({"symbol": row.get("symbol"), "token": row.get("token_address") or row.get("token"), "blockers": m.get("blockers")})

    deep_report = deep_intelligence.investigate_candidates(baseline_eligible, out, now_dt)
    deep_by_key = deep_intelligence.result_index(deep_report)
    eligible: list[tuple[dict, dict[str, Any]]] = []
    for row, m in baseline_eligible:
        deep = deep_by_key.get(_key(m))
        if isinstance(deep, dict) and deep.get("status") == "PASS" and deep.get("actionable") is True:
            enriched = dict(m)
            enriched["deep_intelligence"] = deep
            eligible.append((row, enriched))
        else:
            blocked.append({
                "symbol": row.get("base_token_symbol") or row.get("symbol"),
                "token": m.get("token_address"),
                "blockers": [f"DEEP_INTELLIGENCE_{str((deep or {}).get('status') or 'MISSING')}"] + list((deep or {}).get("hard_blockers") or []) + list((deep or {}).get("critical_missing") or []),
            })

    active = {_key(m) for _, m in eligible}
    state_exists = (out / STATE).exists()
    state = _load(out / STATE, {}) if state_exists else {}
    sent = state.get("sent") if isinstance(state, dict) and isinstance(state.get("sent"), dict) else {}
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(token and chat)
    delivered: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    baseline_count = 0

    if configured and not state_exists:
        for row, m in eligible:
            k = _key(m)
            sent[k] = {
                "active": True,
                "baseline_at": now_iso,
                "symbol": row.get("base_token_symbol") or row.get("symbol"),
                "pair_address": m["pair_address"],
                "source": "FORWARD_ONLY_BASELINE_NO_SEND",
                "confirmation_score": (m.get("deep_intelligence") or {}).get("confirmation_score"),
            }
            baseline_count += 1
        _write(out / STATE, {"version": 3, "updated_at": now_iso, "forward_started_at": now_iso, "sent": sent})
    elif configured:
        for row, m in eligible:
            k = _key(m)
            prev = sent.get(k) if isinstance(sent.get(k), dict) else {}
            if prev.get("active") is True:
                continue
            eid = _event_id(k, now_iso)
            try:
                mid, attempts = _send(token, chat, _message(row, m, now_iso, eid))
                info = {
                    "active": True,
                    "sent_at": now_iso,
                    "event_id": eid,
                    "telegram_message_id": mid,
                    "attempts": attempts,
                    "symbol": row.get("base_token_symbol") or row.get("symbol"),
                    "pair_address": m["pair_address"],
                    "actionable": True,
                    "real_alert_lane": "REVIVAL_90D_15K",
                    "deep_check": "PASS",
                    "revival_score": m.get("revival_score"),
                    "confirmation_score": (m.get("deep_intelligence") or {}).get("confirmation_score"),
                }
                sent[k] = info
                delivered.append({"key": k, **info})
            except Exception as exc:
                errors.append({"key": k, "error": f"{type(exc).__name__}: {exc}"[:300]})
        for k, info in list(sent.items()):
            if isinstance(info, dict) and info.get("active") is True and k not in active:
                info["active"] = False
                info["cleared_at"] = now_iso
                sent[k] = info
        _write(out / STATE, {"version": 3, "updated_at": now_iso, "forward_started_at": state.get("forward_started_at") or now_iso, "sent": sent})

    report = {
        "version": 3,
        "mode": MODE,
        "updated_at": now_iso,
        "configured": configured,
        "source": SOURCE,
        "source_rows": len(rows),
        "live_refresh_candidates": live_refresh_candidates,
        "live_refresh_errors": live_refresh_errors,
        "baseline_eligible_before_deep_check": len(baseline_eligible),
        "deep_check_pass_count": deep_report.get("pass_count", 0),
        "deep_check_watch_count": deep_report.get("watch_count", 0),
        "deep_check_reject_count": deep_report.get("reject_count", 0),
        "eligible_count": len(eligible),
        "blocked_count": len(blocked),
        "baseline_count": baseline_count,
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "delivered": delivered,
        "errors": errors,
        "truth_contract": {
            "research_only": False,
            "actionable_only": True,
            "real_alert_lane": "REVIVAL_90D_15K",
            "production_portfolio_impact": "ALERT_ONLY_MANUAL_DECISION",
            "automatic_buy": False,
            "minimum_market_age_days": MIN_AGE_DAYS,
            "minimum_liquidity_usd": MIN_LIQUIDITY_USD,
            "minimum_revival_score": MIN_REVIVAL_SCORE,
            "minimum_volume_h1_usd": MIN_VOLUME_H1_USD,
            "minimum_txns_h1": MIN_TXNS_H1,
            "exact_pair_required": True,
            "exact_base_token_identity_required": True,
            "expanded_source_required": SOURCE,
            "live_pair_refresh_before_delivery": True,
            "live_refresh_prefiltered": True,
            "automatic_deep_intelligence_before_delivery": True,
            "deep_check_pass_required_for_actionable_alert": True,
            "revival_score_separate_from_confirmation_score": True,
            "critical_deep_source_failure_cannot_pass": True,
            "hard_blocker_overrides_confirmation_score": True,
            "deep_intelligence_report": deep_intelligence.REPORT,
            "notification_marker": "🔥🔥🔥",
            "dedupe": "one alert per exact chain+token+pair active transition; re-arm after leaving eligibility",
            "no_historical_backfill": True,
            "no_hindsight": True,
        },
    }
    _write(out / REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
