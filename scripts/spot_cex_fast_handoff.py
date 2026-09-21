from __future__ import annotations

import json
import os
from pathlib import Path

import unified_watch_engine as engine

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/cex-sensor-handoff.json"
IDENTITY_RADAR = ROOT / "data/cex-spot-identity-radar.json"
NATIVE_REGISTRY = ROOT / "data/native-asset-identity-registry.json"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _f(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _i(value, default=999) -> int:
    try:
        out = int(float(value))
        return out if out > 0 else default
    except (TypeError, ValueError):
        return default


def _native_asset_identity(symbol: str, coingecko_id: str, registry: dict | None = None) -> dict | None:
    registry = registry if isinstance(registry, dict) else _load(NATIVE_REGISTRY, {})
    row = (registry.get("assets") or {}).get(str(coingecko_id or "").strip())
    if not isinstance(row, dict):
        return None
    if str(row.get("symbol") or "").upper().strip() != str(symbol or "").upper().strip():
        return None
    if str(row.get("representation_type") or "") != "CANONICAL_WRAPPED_NATIVE":
        return None
    chain = str(row.get("chain") or "").lower().strip()
    wrapper = str(row.get("token_address") or "").strip()
    if not chain or not wrapper:
        return None
    return {
        "asset_identity_verified": True,
        "asset_identity_scope": "CURATED_NATIVE_ASSET_PLUS_CANONICAL_WRAPPER",
        "asset_network": chain,
        "canonical_wrapper_contract": wrapper,
        "native_asset_evidence_source": row.get("evidence_source"),
        "native_asset_evidence_url": row.get("evidence_url"),
        "execution_identity_verified": False,
    }


def _freshest_milestone(row: dict) -> dict:
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    candidates = []
    for name in (
        "first_cross_venue_slow_ignition",
        "first_shadow_watch",
        "first_alert",
        "first_watch",
        "first_anomaly",
        "first_seen",
    ):
        item = milestones.get(name)
        if not isinstance(item, dict):
            continue
        observed = str(item.get("observed_at") or "")
        if observed:
            candidates.append((observed, item))
    return max(candidates, key=lambda x: x[0])[1] if candidates else {}


def _max_cex_turnover(row: dict) -> float:
    values = [_f(row.get("leaderboard_volume_24h_max"))]
    for market in row.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if market.get("regional_market") is True or market.get("volume_comparable_usd_like") is False:
            continue
        values.append(_f(market.get("volume_24h")))
    return max(values, default=0.0)


def _median_cex_price(row: dict) -> float:
    values = []
    for market in row.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if market.get("regional_market") is True or market.get("volume_comparable_usd_like") is False:
            continue
        price = _f(market.get("price"))
        if price > 0:
            values.append(price)
    values.sort()
    if not values:
        return _f(row.get("cex_reference_price_usd"))
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2.0


def _pending_identity_candidates(doc: dict | None = None) -> list[dict]:
    """Keep high-quality CEX discoveries alive while exact on-chain identity is unresolved.

    This lane is internal-only and cannot satisfy BUY/actionability. It exists solely to
    prevent identity latency from silencing momentum, volume and rank sensors.
    """
    doc = doc if isinstance(doc, dict) else _load(IDENTITY_RADAR, {})
    native_registry = _load(NATIVE_REGISTRY, {})
    out = []
    seen = set()
    for row in doc.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("identity_status") or "")
        if status not in {"IDENTITY_PENDING", "IDENTITY_RESOLVED_PAIR_PENDING"}:
            continue
        cid = str(row.get("coingecko_id") or "").strip()
        symbol = str(row.get("base_symbol") or row.get("symbol") or "").upper().replace("USDT", "")
        if not cid or not symbol or row.get("market_age_verified") is not True:
            continue
        coherent = _i(row.get("current_coherent_confirmations") or row.get("coherent_confirmations"), 0)
        rank = _i(row.get("leaderboard_best_rank") or row.get("positive_gainer_rank"))
        if coherent < 2 and rank > 15:
            continue
        key = f"{cid}:{symbol}"
        if key in seen:
            continue
        seen.add(key)
        milestone = _freshest_milestone(row)
        native_identity = _native_asset_identity(symbol, cid, native_registry) or {}
        out.append({
            "symbol": symbol,
            "candidate_type": "CEX_IDENTITY_PENDING",
            "dynamic_spot_candidate": True,
            "identity_pending_candidate": True,
            "coingecko_id": cid,
            "identity_status": status,
            "identity_blocker": row.get("identity_blocker"),
            "market_age_verified": True,
            **native_identity,
            "coherent_confirmations": coherent,
            "quote_volume_24h_usd": _max_cex_turnover(row),
            "positive_gainer_rank": None if rank >= 999 else rank,
            "change_24h_pct": _f(row.get("current_change_24h_max_pct") or row.get("change_24h_max_pct")),
            "cex_reference_price_usd": _median_cex_price(row),
            "first_seen_at": (row.get("milestones") or {}).get("first_seen", {}).get("observed_at"),
            "discovery_price": milestone.get("reference_price"),
            "signal_at": milestone.get("observed_at"),
        })
    return out


def _spot_key(target: dict) -> str:
    identity = engine.candidate_identity_key(target)
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
    identity_pending_evaluated = 0
    identity_pending_escalated = 0
    rows = []

    all_dynamic = engine.dynamic_candidates(tokens)
    critical_candidates = [x for x in all_dynamic if x.get("dynamic_spot_candidate")]
    queue_meta = state.setdefault("critical_cex_queue", {})
    critical_limit = max(
        4, int(os.environ.get("WALLET500_CRITICAL_CEX_MAX_PER_SCAN", "24"))
    )
    selected_critical, next_cursor, queue_stats = engine.bounded_fair_cex_queue(
        critical_candidates,
        queue_meta.get("cursor", 0),
        critical_limit,
    )
    queue_meta.update({
        **queue_stats,
        "cursor": next_cursor,
        "selected_identity_keys": [
            engine.candidate_identity_key(x) for x in selected_critical
            if engine.candidate_identity_key(x)
        ],
        "selection_source": "CEX_FAST_HANDOFF",
        "selected_at": engine.now_iso(),
        "limit": critical_limit,
    })

    for target in selected_critical:
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
            "exchange": target.get("exchange"),
            "currency_pair": target.get("currency_pair"),
            "execution_identity_scope": target.get("execution_identity_scope"),
            "identity_key": engine.candidate_identity_key(target),
            "candidate_type": target.get("candidate_type") or "GATE_SPOT_DISCOVERY",
            "dynamic_spot_candidate": True,
            "dynamic_cex_market_candidate": bool(target.get("dynamic_cex_market_candidate")),
            "first_seen_at": target.get("first_seen_at") or previous.get("first_seen_at"),
            "first_seen_price": target.get("first_seen_price") if target.get("first_seen_price") is not None else previous.get("first_seen_price"),
            "first_seen_change_24h_pct": target.get("first_seen_change_24h_pct") if target.get("first_seen_change_24h_pct") is not None else previous.get("first_seen_change_24h_pct"),
            "first_seen_quote_volume_24h_usd": target.get("first_seen_quote_volume_24h_usd") if target.get("first_seen_quote_volume_24h_usd") is not None else previous.get("first_seen_quote_volume_24h_usd"),
            "discovery_price": previous.get("discovery_price") if previous.get("discovery_price") is not None else target.get("discovery_price"),
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
                if target.get("dynamic_cex_market_candidate"):
                    live = engine.live_cex_market(target)
                else:
                    live = engine.live_exact_pair(target, spread)
                    if str(target.get("exchange") or "").lower() == "gate" and target.get("currency_pair"):
                        try:
                            cex_snap = engine.gate_execution_snapshot(target.get("currency_pair"))
                            live.update(cex_snap)
                            cex_price = float(cex_snap.get("cex_price") or 0)
                            dex_price = float(live.get("price") or 0)
                            if cex_price > 0 and dex_price > 0:
                                med = (cex_price + dex_price) / 2.0
                                live["cex_market_price_spread_pct"] = (
                                    abs(cex_price - dex_price) / med * 100.0 if med else 999.0
                                )
                        except Exception as cex_exc:
                            live["cex_execution_verified"] = False
                            live["cex_execution_error"] = f"{type(cex_exc).__name__}:{str(cex_exc)[:160]}"
                quarter_wave = engine.quarter_wave_revalidation(
                    previous,
                    live["price"],
                    live["observed_at"],
                    anchor_price=target.get("first_seen_price") or target.get("discovery_price"),
                    anchor_change_24h_pct=target.get("first_seen_change_24h_pct"),
                    anchor_at=target.get("first_seen_at"),
                )
                current.update({
                    "price": live["price"],
                    "liquidity": live["liquidity"],
                    "volume_h1": live["volume_h1"],
                    "volume_h24": live["volume_h24"],
                    "buys_h1": live["buys_h1"],
                    "sells_h1": live["sells_h1"],
                    "spread_pct": live["spread_pct"],
                    "price_source_count": int(live.get("price_source_count") or (1 if target.get("dynamic_cex_market_candidate") else 0)),
                    "price_sources": list(live.get("price_sources") or (["gate"] if target.get("dynamic_cex_market_candidate") else [])),
                    "single_source_degraded": bool(live.get("single_source_degraded")),
                    "single_source_error": live.get("single_source_error"),
                    "observed_at": live["observed_at"],
                    "cex_execution_verified": live.get("cex_execution_verified"),
                    "cex_execution_scope": live.get("cex_execution_scope"),
                    "cex_price": live.get("cex_price"),
                    "cex_market_price_spread_pct": live.get("cex_market_price_spread_pct"),
                    "cex_orderbook_spread_pct": live.get("cex_orderbook_spread_pct"),
                    "cex_bid_depth_1pct_usd": live.get("cex_bid_depth_1pct_usd"),
                    "cex_ask_depth_1pct_usd": live.get("cex_ask_depth_1pct_usd"),
                    "cex_depth_1pct_usd": live.get("cex_depth_1pct_usd"),
                    "cex_bid_ask_depth_ratio": live.get("cex_bid_ask_depth_ratio"),
                    "close_watch_mode": "CEX_LED_REVIVAL",
                    **quarter_wave,
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
                    "quarter_wave_revalidation_armed": bool(
                        current.get("quarter_wave_revalidation_armed")
                    ),
                    "gain_from_first_verified_pct": current.get(
                        "gain_from_first_verified_pct"
                    ),
                    "first_verified_price": current.get("first_verified_price"),
                    "quarter_wave_revalidation_basis": current.get("quarter_wave_revalidation_basis"),
                    "cex_execution_verified": current.get("cex_execution_verified"),
                    "cex_depth_1pct_usd": current.get("cex_depth_1pct_usd"),
                    "cex_orderbook_spread_pct": current.get("cex_orderbook_spread_pct"),
                    "cex_bid_ask_depth_ratio": current.get("cex_bid_ask_depth_ratio"),
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

    for target in _pending_identity_candidates():
        symbol = str(target.get("symbol") or "").upper()
        cid = str(target.get("coingecko_id") or "")
        key = f"CEX_PENDING:{cid}:{symbol}"
        identity_pending_evaluated += 1
        previous = tokens.get(key) if isinstance(tokens.get(key), dict) else {}
        sensor = engine.spot_cex_sensor(target, previous)
        rank = _i(target.get("positive_gainer_rank"))
        change = _f(target.get("change_24h_pct"))
        coherent = _i(target.get("coherent_confirmations"), 0)
        if change >= 20.0 and rank <= 10 and coherent >= 2:
            if "CEX_IDENTITY_PENDING_MOMENTUM" not in sensor["triggers"]:
                sensor["triggers"].append("CEX_IDENTITY_PENDING_MOMENTUM")
            sensor["cex_led"] = True

        current = dict(previous)
        native_asset_verified = target.get("asset_identity_verified") is True
        current.update({
            "symbol": symbol,
            "coingecko_id": cid,
            "candidate_type": "CEX_NATIVE_ASSET" if native_asset_verified else "CEX_IDENTITY_PENDING",
            "identity_status": target.get("identity_status"),
            "identity_blocker": target.get("identity_blocker"),
            "asset_identity_verified": native_asset_verified,
            "asset_identity_scope": target.get("asset_identity_scope"),
            "asset_network": target.get("asset_network"),
            "canonical_wrapper_contract": target.get("canonical_wrapper_contract"),
            "native_asset_evidence_source": target.get("native_asset_evidence_source"),
            "native_asset_evidence_url": target.get("native_asset_evidence_url"),
            "asset_identity_resolution_required": not native_asset_verified,
            "execution_identity_required": True,
            "execution_identity_verified": False,
            "buy_eligible": False,
            "telegram_delivery_enabled": False,
            "first_seen_at": target.get("first_seen_at") or previous.get("first_seen_at"),
            "discovery_price": previous.get("discovery_price") if previous.get("discovery_price") is not None else target.get("discovery_price"),
            "cex_reference_price_usd": target.get("cex_reference_price_usd"),
            "current_change_24h_pct": change,
            "coherent_confirmations": coherent,
            "cex_quote_volume_24h_usd": sensor["current_volume_usd"],
            "cex_quote_volume_baseline_usd": sensor["baseline_volume_usd"],
            "cex_relative_volume_multiple": sensor["baseline_multiple"],
            "cex_scan_volume_multiple": sensor["scan_multiple"],
            "positive_gainer_rank": sensor["current_rank"],
            "cex_led_revival": sensor["cex_led"],
        })
        result = {
            "symbol": symbol,
            "coingecko_id": cid,
            "status": "CEX_NATIVE_ASSET_BASELINE" if native_asset_verified else "CEX_IDENTITY_PENDING_BASELINE",
            "identity_status": current["identity_status"],
            "identity_blocker": current["identity_blocker"],
            "asset_identity_verified": native_asset_verified,
            "asset_identity_scope": current.get("asset_identity_scope"),
            "asset_network": current.get("asset_network"),
            "canonical_wrapper_contract": current.get("canonical_wrapper_contract"),
            "execution_identity_verified": False,
            "cex_sensor": sensor,
            "buy_eligible": False,
            "telegram_delivery_enabled": False,
        }
        if sensor["cex_led"] and _should_refresh(previous, sensor):
            observed = engine.now_iso()
            current["close_watch_mode"] = "CEX_NATIVE_ASSET_CLOSE_WATCH" if native_asset_verified else "CEX_IDENTITY_PENDING_CLOSE_WATCH"
            current["last_internal_escalation"] = {
                "sent_at": observed,
                "cex_reference_price_usd": target.get("cex_reference_price_usd"),
                "current_change_24h_pct": change,
                "coherent_confirmations": coherent,
                "triggers": list(sensor["triggers"]),
                "cex_quote_volume_24h_usd": sensor["current_volume_usd"],
                "cex_quote_volume_baseline_usd": sensor["baseline_volume_usd"],
                "cex_relative_volume_multiple": sensor["baseline_multiple"],
                "cex_scan_volume_multiple": sensor["scan_multiple"],
                "positive_gainer_rank": sensor["current_rank"],
                "asset_identity_verified": native_asset_verified,
                "asset_identity_scope": current.get("asset_identity_scope"),
                "execution_identity_required": True,
                "execution_identity_verified": False,
                "buy_eligible": False,
                "internal_only": True,
                "telegram_suppressed_by_policy": "IDENTITY_PENDING_NEVER_USER_FACING",
            }
            result.update({
                "status": "CEX_NATIVE_ASSET_CLOSE_WATCH" if native_asset_verified else "CEX_IDENTITY_PENDING_CLOSE_WATCH",
                "observed_at": observed,
                "cex_reference_price_usd": target.get("cex_reference_price_usd"),
            })
            identity_pending_escalated += 1
        tokens[key] = current
        rows.append(result)

    state["updated_at"] = engine.now_iso()
    engine.STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    report = {
        "version": 3,
        "generated_at": engine.now_iso(),
        "mode": "CEX_SENSOR_FAST_HANDOFF_WITH_ASSET_IDENTITY_EXECUTION_SEPARATION",
        "evaluated_spot_candidates": evaluated,
        "critical_queue_input": len(critical_candidates),
        "critical_queue_selected": len(selected_critical),
        "critical_queue_deferred": max(0, len(critical_candidates) - len(selected_critical)),
        "critical_queue_limit": critical_limit,
        "critical_queue_next_cursor": next_cursor,
        "escalated_close_watch": escalated,
        "pending_exact_pair": pending_exact_pair,
        "identity_pending_evaluated": identity_pending_evaluated,
        "identity_pending_escalated": identity_pending_escalated,
        "identity_pending_buy_eligible": False,
        "asset_identity_close_watch_buy_eligible": False,
        "asset_identity_does_not_satisfy_execution_identity": True,
        "telegram_delivery_enabled": False,
        "telegram_policy": "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE",
        "rows": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
