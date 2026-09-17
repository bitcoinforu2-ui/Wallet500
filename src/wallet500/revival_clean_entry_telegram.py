from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import revival_90d_telegram as revival

MODE = "REVIVAL_CLEAN_ENTRY_RESEARCH_ONLY_V2"
SOURCE = revival.SOURCE
STATE = "revival-clean-entry-telegram-state.json"
REPORT = "revival-clean-entry-telegram-report.json"
FRAGMENTATION = "cex-market-fragmentation-research.json"
MIN_BUY_SELL_RATIO = float(os.getenv("REVIVAL_CLEAN_MIN_BUY_SELL_RATIO", "1.10"))
MAX_SOURCE_LIVE_PRICE_DIFF_PCT = float(os.getenv("REVIVAL_CLEAN_MAX_SOURCE_LIVE_PRICE_DIFF_PCT", "3.0"))
MAX_FRAGMENTATION_AGE_SECONDS = int(os.getenv("REVIVAL_CLEAN_MAX_FRAGMENTATION_AGE_SECONDS", "3600"))
USD_QUOTES = ("USDT", "USDC", "USD", "BUSD", "FDUSD", "TUSD", "DAI")


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _symbol(row: dict[str, Any]) -> str:
    return str(row.get("base_token_symbol") or row.get("symbol") or "UNKNOWN").upper().strip()


def _fragmentation_symbol_matches(candidate: Any, base: str) -> bool:
    raw = str(candidate or "").upper().replace("/", "").replace("-", "").replace("_", "")
    base = base.upper().strip()
    if not raw or not base:
        return False
    return raw == base or any(raw == base + quote for quote in USD_QUOTES)


def _fragmentation_veto(out: Path, base_symbol: str, now: datetime) -> tuple[bool, dict[str, Any]]:
    payload = revival._load(out / FRAGMENTATION, {})
    if not isinstance(payload, dict) or not payload:
        return False, {"status": "NO_FRESH_FRAGMENTATION_SIGNAL"}
    generated = _parse_time(payload.get("generated_at"))
    if generated is None:
        return False, {"status": "NO_FRESH_FRAGMENTATION_SIGNAL"}
    age = (now - generated).total_seconds()
    if age < -60 or age > MAX_FRAGMENTATION_AGE_SECONDS:
        return False, {"status": "NO_FRESH_FRAGMENTATION_SIGNAL", "age_seconds": round(age, 1)}
    rows = payload.get("current_shadow_candidates") if isinstance(payload.get("current_shadow_candidates"), list) else []
    for item in rows:
        if not isinstance(item, dict) or not _fragmentation_symbol_matches(item.get("symbol"), base_symbol):
            continue
        features = [str(x) for x in (item.get("shadow_features") or [])]
        dangerous = {
            "CROSS_VENUE_PRICE_DISPERSION_SHADOW",
            "MARKET_FRAGMENTATION_COMPOSITE_SHADOW",
        }
        hit = sorted(dangerous.intersection(features))
        if hit:
            return True, {
                "status": "FRESH_CROSS_VENUE_PRICE_RISK",
                "features": hit,
                "observed_at": item.get("observed_at") or payload.get("generated_at"),
                "price_dispersion_pct": item.get("price_dispersion_pct"),
            }
    return False, {"status": "CLEAR", "generated_at": payload.get("generated_at")}


def _source_price(row: dict[str, Any]) -> float:
    for key in ("price_usd", "dex_pair_price_usd", "current_price_usd", "priceUsd"):
        value = revival._f(row.get(key))
        if value > 0:
            return value
    return 0.0


def _clean_meta(raw: dict[str, Any], out: Path, now: datetime) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    row = dict(raw)
    blockers: list[str] = []

    if not revival._static_prefilter(row, now):
        return False, row, {"blockers": ["REVIVAL_BASELINE_PREFILTER_NOT_PASSED"]}

    source_price = _source_price(row)
    row = revival._with_live(row)
    if row.get("live_refresh_error"):
        blockers.append("LIVE_EXACT_PAIR_REFRESH_FAILED")
    if row.get("live_identity_error"):
        blockers.append("LIVE_EXACT_PAIR_IDENTITY_MISMATCH")

    live = row.get("live_h1") if isinstance(row.get("live_h1"), dict) else {}
    live_price = revival._f(live.get("price_usd"))
    if live_price <= 0:
        blockers.append("LIVE_EXACT_PAIR_PRICE_REQUIRED")

    revival_ok, meta = revival._eligibility(row, now)
    if not revival_ok:
        blockers.extend(str(x) for x in (meta.get("blockers") or []))

    buys = revival._i(meta.get("buys_h1"))
    sells = revival._i(meta.get("sells_h1"))
    ratio = (buys / sells) if sells > 0 else (999.0 if buys > 0 else 0.0)
    if buys <= sells:
        blockers.append("BUYERS_NOT_LEADING_H1")
    if ratio < MIN_BUY_SELL_RATIO:
        blockers.append("BUY_SELL_RATIO_BELOW_CLEAN_THRESHOLD")

    source_live_diff_pct = None
    if source_price > 0 and live_price > 0:
        source_live_diff_pct = abs(source_price - live_price) / live_price * 100.0
        if source_live_diff_pct > MAX_SOURCE_LIVE_PRICE_DIFF_PCT:
            blockers.append("SOURCE_LIVE_PRICE_DIVERGENCE")

    frag_veto, frag = _fragmentation_veto(out, _symbol(row), now)
    if frag_veto:
        blockers.append("FRESH_CROSS_VENUE_PRICE_RISK")

    risk_level = str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper()
    if risk_level in {"HIGH", "CRITICAL", "CRITICAL_DOWNSIDE_LEAD"}:
        blockers.append("ACTIVE_HIGH_OR_CRITICAL_RISK")

    clean = {
        **meta,
        "live_price_usd": live_price,
        "quote_source": "DEXSCREENER_EXACT_PAIR_LIVE",
        "quote_observed_at": now.isoformat(),
        "buy_sell_ratio_h1": round(ratio, 4),
        "minimum_buy_sell_ratio": MIN_BUY_SELL_RATIO,
        "source_price_usd": source_price or None,
        "source_live_price_diff_pct": None if source_live_diff_pct is None else round(source_live_diff_pct, 4),
        "max_source_live_price_diff_pct": MAX_SOURCE_LIVE_PRICE_DIFF_PCT,
        "cross_venue_check": frag,
        "blockers": sorted(set(blockers)),
    }
    return not blockers, row, clean


def _event_id(key: str, ts: str) -> str:
    return "RCE-" + hashlib.sha256(f"{key}|{ts}".encode()).hexdigest()[:12].upper()


def _message(row: dict[str, Any], meta: dict[str, Any], ts: str, eid: str) -> str:
    symbol = _symbol(row)
    url = str(row.get("url") or row.get("dex_url") or row.get("dex_link") or "")
    diff = meta.get("source_live_price_diff_pct")
    cross = meta.get("cross_venue_check") or {}
    lines = [
        "🟢 CLEAN ENTRY CANDIDATE — REVIVAL — WALLET500",
        "✅ כניסה נקייה יותר אושרה לפי נתוני LIVE — החלטה ידנית בלבד",
        f"📅 זמן אימות (ישראל): {revival._fmt_israel_time(ts)}",
        f"🧾 Alert ID: {eid}",
        "✅ MANUAL DECISION — NO AUTOMATIC TRADE",
        f"Token: {symbol}",
        f"Chain: {str(meta['chain']).upper().replace('BSC', 'BNB')}",
        f"Contract: {meta['token_address']}",
        f"Pair: {meta['pair_address']}",
        "Exact token identity: VERIFIED ✅",
        "Exact pair: LOCKED ✅",
        f"LIVE exact-pair price: ${meta['live_price_usd']:.10g} ✅",
        "Price source: DEXSCREENER EXACT PAIR LIVE ✅",
        f"Quote observed: {meta['quote_observed_at']}",
        f"Liquidity: {revival._fmt_money(meta['liquidity_usd'])} ✅",
        f"Revival score: {meta['revival_score']:.1f}/100 ✅",
        f"Volume H1: {revival._fmt_money(meta['volume_h1_usd'])} ✅",
        f"Activity H1: {meta['txns_h1']} tx ✅",
        f"Buy/Sell H1: {meta['buys_h1']}/{meta['sells_h1']} — ratio {meta['buy_sell_ratio_h1']:.2f}x ✅ min {MIN_BUY_SELL_RATIO:.2f}x",
        f"Cross-venue price risk: {cross.get('status', 'NO_FRESH_FRAGMENTATION_SIGNAL')} ✅",
        "Signal type: CLEAN ENTRY CANDIDATE — not BUY NOW",
        "Verified Intelligence. The Pure Truth.",
    ]
    if diff is not None:
        lines.insert(14, f"Source/LIVE price gap: {diff:.2f}% ✅ max {MAX_SOURCE_LIVE_PRICE_DIFF_PCT:.2f}%")
    if url:
        lines.append(f"🔗 OPEN DEX: {url}")
    return "\n".join(lines)


def run(output_dir: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    rows = revival._source_rows(revival._load(out / SOURCE, {}))

    clean_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    blocked: list[dict[str, Any]] = []
    for raw in rows:
        ok, row, meta = _clean_meta(raw, out, now_dt)
        if ok:
            clean_rows.append((row, meta))
        elif meta.get("blockers") != ["REVIVAL_BASELINE_PREFILTER_NOT_PASSED"]:
            blocked.append({
                "symbol": _symbol(raw),
                "token": raw.get("token_address") or raw.get("token"),
                "blockers": meta.get("blockers") or [],
                "buy_sell_ratio_h1": meta.get("buy_sell_ratio_h1"),
                "live_price_usd": meta.get("live_price_usd"),
            })

    active = {revival._key(meta) for _, meta in clean_rows}
    state_exists = (out / STATE).exists()
    state = revival._load(out / STATE, {}) if state_exists else {}
    observed = state.get("sent") if isinstance(state, dict) and isinstance(state.get("sent"), dict) else {}
    delivered: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    baseline_count = 0

    # User-facing Telegram delivery is intentionally forbidden in this legacy lane.
    # CLEAN ENTRY remains research evidence only; user-facing delivery belongs to the
    # Unified Watch Engine and only for near-buy / buy-grade events.
    for row, meta in clean_rows:
        key = revival._key(meta)
        prev = observed.get(key) if isinstance(observed.get(key), dict) else {}
        if not prev:
            baseline_count += 1
        observed[key] = {
            **prev,
            "active": True,
            "observed_at": now_iso,
            "symbol": _symbol(row),
            "pair_address": meta["pair_address"],
            "live_price_usd": meta["live_price_usd"],
            "buy_sell_ratio_h1": meta["buy_sell_ratio_h1"],
            "source": "RESEARCH_ONLY_NO_TELEGRAM",
        }
    for key, info in list(observed.items()):
        if isinstance(info, dict) and info.get("active") is True and key not in active:
            info["active"] = False
            info["cleared_at"] = now_iso
            observed[key] = info
    revival._write(
        out / STATE,
        {
            "version": 2,
            "updated_at": now_iso,
            "forward_started_at": state.get("forward_started_at") or now_iso,
            "sent": observed,
            "telegram_delivery": "FORBIDDEN",
            "delivery_lane": "UNIFIED_WATCH_ENGINE_ONLY",
        },
    )
    configured = False

    report = {
        "version": 1,
        "mode": MODE,
        "updated_at": now_iso,
        "configured": configured,
        "source": SOURCE,
        "source_rows": len(rows),
        "clean_count": len(clean_rows),
        "blocked_count": len(blocked),
        "baseline_count": baseline_count,
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "blocked": blocked[:100],
        "delivered": delivered,
        "errors": errors,
        "truth_contract": {
            "research_only": True,
            "actionable_only": False,
            "manual_decision_only": True,
            "automatic_buy": False,
            "exact_pair_live_price_required": True,
            "exact_base_token_identity_required": True,
            "minimum_buy_sell_ratio_h1": MIN_BUY_SELL_RATIO,
            "buyers_must_lead_h1": True,
            "maximum_source_live_price_diff_pct": MAX_SOURCE_LIVE_PRICE_DIFF_PCT,
            "fresh_cross_venue_price_dispersion_veto": True,
            "alert_label": "CLEAN ENTRY CANDIDATE",
            "buy_now_language_forbidden": True,
            "telegram_delivery_forbidden": True,
            "delivery_lane": "UNIFIED_WATCH_ENGINE_ONLY",
            "no_historical_backfill": True,
            "no_hindsight": True,
        },
    }
    revival._write(out / REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
