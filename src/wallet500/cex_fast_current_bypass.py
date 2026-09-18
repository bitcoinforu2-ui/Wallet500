from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .cex_fast_promotion import (
    OUTPUT_FILE,
    REPORT_FILE,
    _eligibility,
    _event_id,
    _f,
    _i,
    _identity_key,
    _load,
    _message,
    _send,
    _strict_dex_resolve,
    _write,
)

DATA = Path("data")
RADAR_FILE = "cex-spot-revival-radar.json"
STATE_FILE = "cex-fast-current-bypass-state.json"
MAX_STRICT_RESOLVES_PER_RUN = 16
MAX_DELIVER_PER_RUN = 6
MIN_PRIORITY_SCORE = 35
MAX_PRE_RESOLVE_24H_CHANGE_PCT = 45.0


def _milestone_score(row: dict) -> int:
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    alert = milestones.get("first_alert") if isinstance(milestones.get("first_alert"), dict) else {}
    watch = milestones.get("first_watch") if isinstance(milestones.get("first_watch"), dict) else {}
    return max(
        _i(row.get("spot_revival_score")),
        _i(alert.get("score")),
        _i(watch.get("score")),
    )


def _priority_candidates(radar: dict) -> list[dict]:
    rows = [dict(x) for x in (radar.get("watchlist") or []) if isinstance(x, dict)]
    selected = []
    for row in rows:
        if row.get("leveraged_product") is True:
            continue
        score = _milestone_score(row)
        change = _f(row.get("change_24h_max_pct"))
        if score < MIN_PRIORITY_SCORE:
            continue
        if change > MAX_PRE_RESOLVE_24H_CHANGE_PCT:
            continue
        markets = [x for x in (row.get("markets") or []) if isinstance(x, dict) and _f(x.get("price")) > 0]
        if not markets:
            continue
        row["_fast_priority_score"] = score
        selected.append(row)

    selected.sort(
        key=lambda x: (
            _i(x.get("coherent_confirmations")),
            _i(x.get("_fast_priority_score")),
            -_f(x.get("change_24h_max_pct")),
            max((_f(m.get("volume_24h")) for m in x.get("markets") or [] if isinstance(m, dict)), default=0.0),
        ),
        reverse=True,
    )
    return selected[:MAX_STRICT_RESOLVES_PER_RUN]


def _resolve_many(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    resolved = []
    failures = []
    if not rows:
        return resolved, failures
    with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
        futures = {pool.submit(_strict_dex_resolve, row): row for row in rows}
        for fut in as_completed(futures):
            source = futures[fut]
            symbol = str(source.get("symbol") or "")
            try:
                item = fut.result()
                if item:
                    item["fast_identity_bypass"] = True
                    item["fast_identity_bypass_source"] = "CURRENT_CEX_SPOT_WATCHLIST_STRICT_DEX_RESOLUTION"
                    resolved.append(item)
                else:
                    failures.append({"symbol": symbol, "reason": "STRICT_EXACT_IDENTITY_NOT_RESOLVED"})
            except Exception as exc:
                failures.append({"symbol": symbol, "reason": f"{type(exc).__name__}: {exc}"[:240]})
    return resolved, failures


def run(output_dir: str | None = None, now: datetime | None = None) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", str(DATA)))
    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    radar = _load(out / RADAR_FILE, {})
    priority = _priority_candidates(radar if isinstance(radar, dict) else {})
    resolved, resolve_failures = _resolve_many(priority)

    state_path = out / STATE_FILE
    previous_state = _load(state_path, {})
    previous = previous_state.get("active") if isinstance(previous_state, dict) and isinstance(previous_state.get("active"), dict) else {}
    active_now: dict[str, dict] = {}

    alert_payload = _load(out / OUTPUT_FILE, {})
    existing_alerts = [dict(x) for x in (alert_payload.get("alerts") or []) if isinstance(x, dict)]
    existing_keys = {
        _identity_key(x): i
        for i, x in enumerate(existing_alerts)
        if x.get("chain") and x.get("token_address") and x.get("pair_address")
    }

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(token and chat_id)
    delivered = []
    errors = []
    evaluated = []
    eligible = []

    for row in resolved:
        ok, metrics = _eligibility(row)
        item = {
            "symbol": metrics.get("symbol") or row.get("symbol"),
            "chain": row.get("chain"),
            "token_address": row.get("token_address"),
            "pair_address": row.get("pair_address"),
            "dex": row.get("dex"),
            "dex_url": row.get("dex_url") or row.get("url"),
            "status": "REAL_ALERT" if ok else "BLOCKED",
            "alert_class": "CEX_FAST_CURRENT_BYPASS_REAL_ALERT" if ok else "CEX_FAST_CURRENT_BYPASS_BLOCKED",
            "research_only": False if ok else True,
            "actionable": bool(ok),
            "actionable_research_alert": bool(ok),
            "manual_decision_only": True,
            "automatic_buy": False,
            "fast_identity_bypass": True,
            "fast_identity_bypass_source": row.get("fast_identity_bypass_source"),
            **metrics,
        }
        evaluated.append(item)
        if not ok:
            continue
        eligible.append((row, item))

    eligible.sort(
        key=lambda pair: (
            _i(pair[1].get("signal_score")),
            _i(pair[1].get("coherent_confirmations")),
            _f(pair[1].get("cex_turnover_usd")),
        ),
        reverse=True,
    )

    sends_this_run = 0
    for row, item in eligible:
        key = _identity_key(row)
        if not key.strip(":"):
            continue
        prev = previous.get(key) if isinstance(previous.get(key), dict) else {}
        info = dict(prev)
        info.update({
            "active": True,
            "last_seen_at": now_iso,
            "symbol": item.get("symbol"),
            "pair_address": row.get("pair_address"),
        })

        if key in existing_keys:
            existing_alerts[existing_keys[key]].update(item)
        else:
            existing_keys[key] = len(existing_alerts)
            existing_alerts.append(item)

        if prev.get("active") is not True and sends_this_run < MAX_DELIVER_PER_RUN:
            event_id = _event_id(key, now_iso)
            item["alert_event_id"] = event_id
            item["promoted_at"] = now_iso
            # Keep the bypass candidate in the engine, but never deliver it directly.
            info["telegram_suppressed_by_policy"] = True
            info["suppression_policy"] = "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE"
        active_now[key] = info

    current_keys = set(active_now)
    for key, old in previous.items():
        if key in current_keys or not isinstance(old, dict):
            continue
        cleared = dict(old)
        if old.get("active") is True:
            cleared["active"] = False
            cleared["cleared_at"] = now_iso
        active_now[key] = cleared

    _write(state_path, {"version": 1, "updated_at": now_iso, "active": active_now})

    alert_payload["alerts"] = existing_alerts
    alert_payload["count"] = len(existing_alerts)
    truth = alert_payload.get("truth_contract") if isinstance(alert_payload.get("truth_contract"), dict) else {}
    truth.update({
        "current_watch_identity_queue_bypass_enabled": True,
        "current_watch_bypass_requires_strict_dex_identity": True,
        "current_watch_bypass_symbol_only_never_actionable": True,
        "current_watch_strict_resolve_limit_per_run": MAX_STRICT_RESOLVES_PER_RUN,
        "current_watch_max_telegram_deliveries_per_run": 0,
        "direct_telegram_delivery_disabled": True,
    })
    alert_payload["truth_contract"] = truth
    _write(out / OUTPUT_FILE, alert_payload)

    report = _load(out / REPORT_FILE, {})
    report["current_watch_bypass"] = {
        "priority_candidates": len(priority),
        "strict_resolved": len(resolved),
        "eligible": len(eligible),
        "delivered": len(delivered),
        "resolve_failures": resolve_failures[:30],
        "errors": errors,
        "resolve_limit": MAX_STRICT_RESOLVES_PER_RUN,
        "delivery_cap": 0,
        "telegram_delivery_enabled": False,
    }
    report["eligible_count"] = int(report.get("eligible_count") or 0) + len([
        1 for _, item in eligible if _identity_key(item) not in set()
    ])
    report["delivered_count"] = int(report.get("delivered_count") or 0) + len(delivered)
    report["error_count"] = int(report.get("error_count") or 0) + len(errors)
    report["delivered"] = list(report.get("delivered") or []) + delivered
    report["errors"] = list(report.get("errors") or []) + errors
    report["telegram_delivery_enabled"] = False
    report["telegram_delivery_policy"] = "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE"
    report["truth_contract"] = truth
    _write(out / REPORT_FILE, report)

    result = {
        "priority_candidates": len(priority),
        "strict_resolved": len(resolved),
        "eligible": len(eligible),
        "delivered": len(delivered),
        "errors": len(errors),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    run()
