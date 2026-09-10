from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path("data")
MIN_MARKET_AGE_DAYS = 90
MIN_RESEARCH_SCORE = 30
MAX_LEADERBOARD_RANK = 10
REENTRY_COOLDOWN_HOURS = 6
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _f(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _parse_time(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        raw = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fmt_israel(value: object) -> str:
    dt = _parse_time(value)
    return dt.astimezone(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M:%S") if dt else "n/a"


def _fmt_money(value: object) -> str:
    try:
        n = float(value)
    except Exception:
        return "n/a"
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n / 1_000:.1f}K"
    if abs(n) >= 1:
        return f"${n:.2f}"
    if n == 0:
        return "$0"
    return f"${n:.8f}".rstrip("0").rstrip(".")


def _key(row: dict) -> str:
    chain = str(row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or row.get("token") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    if chain in {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "polygon"}:
        token = token.lower()
        pair = pair.lower()
    return f"{chain}:{token}:{pair}"


def _best_market(row: dict) -> dict:
    markets = [x for x in (row.get("markets") or []) if isinstance(x, dict)]
    if not markets:
        return {}
    return max(markets, key=lambda x: (_f(x.get("volume_24h")), _f(x.get("change_24h_pct"))))


def _eligible(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("identity_status") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
        return False
    if row.get("market_age_verified") is not True:
        return False
    try:
        if int(row.get("market_age_min_days") or 0) < MIN_MARKET_AGE_DAYS:
            return False
    except Exception:
        return False
    if row.get("research_only") is not True or row.get("actionable") is not False:
        return False
    if not str(row.get("chain") or "").strip():
        return False
    if not str(row.get("token_address") or row.get("token") or "").strip():
        return False
    if not str(row.get("pair_address") or "").strip():
        return False
    score = int(row.get("spot_revival_score") or 0)
    rank = int(row.get("leaderboard_best_rank") or 9999)
    return score >= MIN_RESEARCH_SCORE or rank <= MAX_LEADERBOARD_RANK


def _first_watch_at(row: dict) -> object:
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    watch = milestones.get("first_watch") if isinstance(milestones.get("first_watch"), dict) else {}
    alert = milestones.get("first_alert") if isinstance(milestones.get("first_alert"), dict) else {}
    return watch.get("observed_at") or alert.get("observed_at")


def _message(row: dict, now: str) -> str:
    best = _best_market(row)
    symbol = str(row.get("symbol") or "UNKNOWN").replace("USDT", "")
    chain = str(row.get("chain") or "unknown").upper()
    token = str(row.get("token_address") or row.get("token") or "unknown")
    pair = str(row.get("pair_address") or "unknown")
    score = int(row.get("spot_revival_score") or 0)
    move = _f(row.get("change_24h_max_pct"))
    rank = int(row.get("leaderboard_best_rank") or 9999)
    exchanges = list(row.get("leaderboard_exchanges") or [])
    all_exchanges = list(row.get("exchanges") or [])
    turnover = max((_f(x.get("volume_24h")) for x in (row.get("markets") or []) if isinstance(x, dict)), default=_f(best.get("volume_24h")))
    price_acc = _f(row.get("price_acceleration_max_pct"))
    volume_acc = _f(row.get("volume_acceleration_max_pct"))
    dex_liq = row.get("execution_pool_liquidity_usd")
    if dex_liq is None:
        dex_liq = row.get("dex_liquidity_usd")
    dex_h1 = row.get("dex_volume_h1")
    first_watch = _first_watch_at(row)
    dex_url = str(row.get("dex_url") or "").strip()
    div = row.get("cex_dex_divergence") if isinstance(row.get("cex_dex_divergence"), dict) else {}
    div_status = str(div.get("status") or "INSUFFICIENT_COVERAGE")
    dex_move = div.get("dex_move_24h_pct")

    lines = [
        "⚡ CEX EARLY WATCH — WALLET500",
        "🟡 RESEARCH ONLY — NOT REAL ALERT / NOT BUY SIGNAL",
        f"📅 נשלח (ישראל): {_fmt_israel(now)}",
        f"🕒 T0 First Watch (ישראל): {_fmt_israel(first_watch)}",
        f"Token: {symbol}",
        f"Chain: {chain}",
        f"Contract: {token}",
        f"Exact pair: {pair}",
        "Identity: EXACT CHAIN + CONTRACT + DEX PAIR ✅",
        f"Market age: ≥{int(row.get('market_age_min_days') or 0)}d ✅",
        f"CEX research score: {score}/100",
        f"CEX 24h move: {move:+.2f}%",
    ]
    if dex_move is not None:
        lines.append(f"DEX exact-pair 24h move: {float(dex_move):+.2f}%")
        lines.append(f"CEX↔DEX: {div_status}")
        if "DIVERGENCE" in div_status:
            lines.append("⚠️ CEX/DEX disagreement — do not interpret CEX momentum alone as confirmation.")
    else:
        lines.append("CEX↔DEX: INSUFFICIENT_COVERAGE")
    if rank <= MAX_LEADERBOARD_RANK:
        lines.append(f"Leaderboard: TOP-{MAX_LEADERBOARD_RANK} / best rank #{rank} ({', '.join(exchanges) or 'CEX'})")
    lines.extend([
        f"CEX confirmations: {int(row.get('confirmations') or 0)} ({', '.join(all_exchanges) or 'n/a'})",
        f"CEX turnover 24h (max venue): {_fmt_money(turnover)}",
        f"Price acceleration / scan: {price_acc:+.2f}%",
        f"Volume acceleration / scan: {volume_acc:+.2f}%",
        f"DEX execution-pool liquidity: {_fmt_money(dex_liq)}",
        f"DEX volume 1H: {_fmt_money(dex_h1)}",
        "⚠️ Low/absent DEX liquidity can block REAL ALERT even when CEX momentum is strong.",
        "Strict REAL ALERT / liquidity / holder / survival gates: UNCHANGED.",
        "Verified Intelligence. The Pure Truth.",
    ])
    if dex_url:
        lines.append(f"🔗 DEX: {dex_url}")
    return "\n".join(lines)


def _send(bot_token: str, chat_id: str, text: str, max_attempts: int = 3) -> tuple[int | None, int]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read().decode("utf-8", errors="replace")
                payload = json.loads(raw) if raw else {}
                if response.status < 200 or response.status >= 300 or payload.get("ok") is not True:
                    raise RuntimeError(f"Telegram delivery rejected: HTTP {response.status}")
                result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                mid = result.get("message_id")
                return (int(mid) if mid is not None else None), attempt
        except urllib.error.HTTPError as exc:
            last_error = exc
            if not (exc.code == 429 or 500 <= exc.code < 600) or attempt >= max_attempts:
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt >= max_attempts:
                raise
        time.sleep(float(attempt))
    raise RuntimeError(f"Telegram delivery failed: {last_error}")


def run(data_dir: Path = DATA, now: datetime | None = None) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    source_path = data_dir / "cex-spot-identity-radar.json"
    state_path = data_dir / "cex-spot-telegram-state.json"
    report_path = data_dir / "cex-spot-telegram-report.json"
    source = _load(source_path, {})
    candidates = [x for x in (source.get("candidates") or []) if _eligible(x)] if isinstance(source, dict) else []
    bot_token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not bot_token or not chat_id:
        existing = _load(report_path, {})
        report = {"status": "SKIPPED_UNCONFIGURED_NO_STATE_WRITE", "reason": "TELEGRAM_SECRETS_MISSING", "eligible_count": len(candidates), "preserved_existing_report": isinstance(existing, dict) and bool(existing)}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return existing if isinstance(existing, dict) and existing else report
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_s = now.isoformat()
    state = _load(state_path, {})
    initialized = bool(state.get("initialized")) if isinstance(state, dict) else False
    records = state.get("records") if isinstance(state, dict) and isinstance(state.get("records"), dict) else {}
    current_keys = {_key(x) for x in candidates}
    for key, rec in list(records.items()):
        if isinstance(rec, dict) and rec.get("active") is True and key not in current_keys:
            rec["active"] = False
            rec["last_exit_at"] = now_s
            records[key] = rec
    delivered, baseline, suppressed, errors = [], [], [], []
    for row in candidates:
        key = _key(row)
        previous = records.get(key) if isinstance(records.get(key), dict) else {}
        was_active = previous.get("active") is True
        last_sent = _parse_time(previous.get("last_sent_at"))
        can_realert = last_sent is None or now - last_sent >= timedelta(hours=REENTRY_COOLDOWN_HOURS)
        if not initialized:
            baseline.append({"key": key, "symbol": row.get("symbol"), "reason": "INITIAL_FORWARD_BASELINE_NO_SEND"})
        elif was_active:
            suppressed.append({"key": key, "symbol": row.get("symbol"), "reason": "STILL_ACTIVE_DEDUPED"})
        elif not can_realert:
            suppressed.append({"key": key, "symbol": row.get("symbol"), "reason": "REENTRY_COOLDOWN_LT_6H"})
        else:
            try:
                mid, attempts = _send(bot_token, chat_id, _message(row, now_s))
                previous["last_sent_at"] = now_s
                previous["telegram_message_id"] = mid
                previous["delivery_attempts"] = attempts
                delivered.append({"key": key, "symbol": row.get("symbol"), "telegram_message_id": mid, "attempts": attempts})
            except Exception as exc:
                errors.append({"key": key, "symbol": row.get("symbol"), "error": f"{type(exc).__name__}: {exc}"[:500]})
        previous.update({"active": True, "symbol": row.get("symbol"), "chain": row.get("chain"), "token_address": row.get("token_address") or row.get("token"), "pair_address": row.get("pair_address"), "last_seen_at": now_s, "score": int(row.get("spot_revival_score") or 0), "leaderboard_best_rank": int(row.get("leaderboard_best_rank") or 9999)})
        records[key] = previous
    _write(state_path, {"version": 1, "initialized": True, "updated_at": now_s, "policy": "FORWARD_ONLY_EXACT_VETERAN_CEX_RESEARCH_WATCH; FIRST_RUN_BASELINES; REENTRY_AFTER_6H_CAN_REALERT", "records": records})
    report = {"version": 2, "generated_at": now_s, "status": "OK" if not errors else "DEGRADED_DELIVERY_ERRORS", "research_only": True, "automatic_buy": False, "strict_real_alert_gates_changed": False, "source_generated_at": source.get("generated_at") if isinstance(source, dict) else None, "eligible_count": len(candidates), "first_run_baseline": not initialized, "baseline_count": len(baseline), "delivered_count": len(delivered), "suppressed_count": len(suppressed), "error_count": len(errors), "baseline": baseline, "delivered": delivered, "suppressed": suppressed, "errors": errors, "truth_contract": {"exact_identity_required": True, "minimum_market_age_days": MIN_MARKET_AGE_DAYS, "cex_early_watch_is_not_real_alert": True, "cex_early_watch_is_not_buy_signal": True, "cex_dex_divergence_is_explicit": True, "dex_liquidity_is_displayed_not_waived_for_real_alert": True, "holder_liquidity_survival_real_alert_gates_unchanged": True}}
    _write(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
