from __future__ import annotations

import json
from pathlib import Path

import unified_watch_engine as engine

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/cex-sensor-handoff.json"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _spot_key(target: dict) -> str:
    identity = engine.exact_identity_key(target)
    return f"SPOT:{identity}" if identity else ""


def _should_refresh(previous: dict, sensor: dict) -> bool:
    last = previous.get("last_internal_escalation") if isinstance(previous, dict) else {}
    if not isinstance(last, dict) or not last:
        return True
    last_multiple = float(last.get("cex_relative_volume_multiple") or 0)
    last_rank = int(last.get("positive_gainer_rank") or 999)
    current_multiple = float(sensor.get("baseline_multiple") or 0)
    current_rank = int(sensor.get("current_rank") or 999)
    return current_multiple >= max(4.0, last_multiple * 1.5) or current_rank < last_rank


def main() -> int:
    cfg = _load(engine.CONFIG, {})
    state = _load(engine.STATE, {"version": 4, "tokens": {}})
    state["version"] = max(4, int(state.get("version") or 0))
    tokens = state.setdefault("tokens", {})
    spread = float((cfg.get("data_integrity") or {}).get("max_price_source_spread_pct", 2))

    evaluated = 0
    escalated = 0
    pending_exact_pair = 0
    rows = []

    for target in engine.dynamic_candidates():
        if not target.get("dynamic_spot_candidate"):
            continue
        key = _spot_key(target)
        if not key:
            continue
        evaluated += 1
        previous = tokens.get(key) if isinstance(tokens.get(key), dict) else {}
        sensor = engine.spot_cex_sensor(target, previous)

        current = dict(previous)
        current.update({
            "symbol": str(target.get("symbol") or "").upper(),
            "network": target.get("network"),
            "contract": target.get("contract"),
            "pair": target.get("pair"),
            "identity_key": engine.exact_identity_key(target),
            "candidate_type": target.get("candidate_type") or "GATE_SPOT_DISCOVERY",
            "dynamic_spot_candidate": True,
            "first_seen_at": target.get("first_seen_at") or previous.get("first_seen_at"),
            "discovery_price": target.get("discovery_price") if target.get("discovery_price") is not None else previous.get("discovery_price"),
            "cex_quote_volume_24h_usd": sensor["current_volume_usd"],
            "cex_quote_volume_baseline_usd": sensor["baseline_volume_usd"],
            "cex_relative_volume_multiple": sensor["baseline_multiple"],
            "cex_scan_volume_multiple": sensor["scan_multiple"],
            "positive_gainer_rank": sensor["current_rank"],
            "cex_led_revival": sensor["cex_led"],
        })

        result = {
            "symbol": current["symbol"],
            "identity_key": current["identity_key"],
            "cex_sensor": sensor,
            "status": "BASELINE_TRACKING",
        }

        if sensor["cex_led"] and _should_refresh(previous, sensor):
            try:
                live = engine.live_exact_pair(target, spread)
                current.update({
                    "price": live["price"],
                    "liquidity": live["liquidity"],
                    "volume_h1": live["volume_h1"],
                    "volume_h24": live["volume_h24"],
                    "buys_h1": live["buys_h1"],
                    "sells_h1": live["sells_h1"],
                    "spread_pct": live["spread_pct"],
                    "observed_at": live["observed_at"],
                    "close_watch_mode": "CEX_LED_REVIVAL",
                })
                current["last_internal_escalation"] = {
                    "sent_at": live["observed_at"],
                    "price": live["price"],
                    "liquidity": live["liquidity"],
                    "volume_h1": live["volume_h1"],
                    "buys_h1": live["buys_h1"],
                    "sells_h1": live["sells_h1"],
                    "triggers": list(sensor["triggers"]),
                    "cex_quote_volume_24h_usd": sensor["current_volume_usd"],
                    "cex_quote_volume_baseline_usd": sensor["baseline_volume_usd"],
                    "cex_relative_volume_multiple": sensor["baseline_multiple"],
                    "cex_scan_volume_multiple": sensor["scan_multiple"],
                    "positive_gainer_rank": sensor["current_rank"],
                    "internal_only": True,
                    "telegram_suppressed_by_policy": "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE",
                }
                result.update({
                    "status": "CEX_LED_REVIVAL_CLOSE_WATCH",
                    "verified_price": live["price"],
                    "verified_liquidity": live["liquidity"],
                    "verified_volume_h1": live["volume_h1"],
                    "observed_at": live["observed_at"],
                })
                escalated += 1
            except Exception as exc:
                current["close_watch_mode"] = "CEX_LED_REVIVAL_PENDING_EXACT_PAIR"
                current["cex_handoff_error"] = f"{type(exc).__name__}: {exc}"[:240]
                result.update({
                    "status": "CEX_LED_REVIVAL_PENDING_EXACT_PAIR",
                    "error": current["cex_handoff_error"],
                })
                pending_exact_pair += 1

        tokens[key] = current
        rows.append(result)

    state["updated_at"] = engine.now_iso()
    engine.STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    report = {
        "version": 1,
        "generated_at": engine.now_iso(),
        "mode": "CEX_SENSOR_FAST_HANDOFF_INTERNAL_ONLY",
        "evaluated_spot_candidates": evaluated,
        "escalated_close_watch": escalated,
        "pending_exact_pair": pending_exact_pair,
        "telegram_delivery_enabled": False,
        "telegram_policy": "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE",
        "rows": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
