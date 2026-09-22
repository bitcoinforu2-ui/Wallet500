from __future__ import annotations

import argparse
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import resilient_unified_watch_runner as resilient_runner
import unified_watch_engine as engine
import user_watch_final_buy as gate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = Path("/tmp/wallet500-hot-recheck-plan.json")

# These blockers can change from a fresh market observation alone. Anything
# outside this set remains fail-closed and does not consume the hot recheck lane.
MARKET_RECOVERABLE_BLOCKERS = {
    "NEED_SECOND_VERIFIED_SCAN",
    "REBOUND_FROM_WATCH_LOW_NOT_CONFIRMED",
    "SHORT_TERM_PRICE_RECLAIM_NOT_CONFIRMED",
    "SHORT_TERM_CHASE_RISK",
    "EXTENDED_MOVE_WAIT_FOR_RESET",
    "LIQUIDITY_BELOW_FINAL_BUY_FLOOR",
    "VOLUME_H1_TOO_LOW",
    "ACTIVITY_H1_TOO_LOW",
    "BUY_FLOW_NOT_CONFIRMED",
    "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET",
    "PRICE_SOURCE_REDUNDANCY_MISSING",
}

# A 3-minute market refresh cannot repair these safely. They require a later
# intelligence/identity/provider cycle and must not be promoted by rechecking.
NON_RECHECKABLE_BLOCKERS = {
    "EXACT_IDENTITY_MISSING",
    "MARKET_STATE_MISSING",
    "WATCH_REPORT_ROW_MISSING",
    "EXACT_PAIR_NOT_VERIFIED_THIS_SCAN",
    "WATCH_REPORT_STALE_OR_UNTIMED",
    "MARKET_SNAPSHOT_STALE_OR_UNTIMED",
    "MARKET_IDENTITY_MISMATCH",
    "PRICE_MISSING",
    "INTELLIGENCE_NOT_CURRENT",
    "INTELLIGENCE_STALE_OR_UNTIMED",
    "CURRENT_EVIDENCE_TOO_LOW",
    "HARD_RISK_PRESENT",
    "MARKET_MICROSTRUCTURE_NOT_POSITIVE",
    "CEX_DEX_PRICE_DIVERGENCE",
}


def _load(path: Path, default: Any) -> Any:
    return gate.load(path, default)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _target_map(config: dict, dynamic: dict, watch_state: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for target in gate.eligible_targets(config, dynamic, watch_state):
        key = gate.identity_key(target)
        if key:
            out[key] = target
    return out


def _current_intelligence_safe(decision: dict, policy: dict) -> bool:
    intel = decision.get("intelligence") if isinstance(decision.get("intelligence"), dict) else {}
    if str(intel.get("status") or "").upper() != "CURRENT":
        return False
    if intel.get("hard_risks"):
        return False
    try:
        evidence = int(intel.get("current_evidence_count") or 0)
    except (TypeError, ValueError):
        evidence = 0
    if evidence < int(policy.get("min_current_evidence", 2)):
        return False
    try:
        micro = float(intel.get("market_microstructure_score") or 0)
    except (TypeError, ValueError):
        micro = 0.0
    if micro <= 0:
        return False
    age = gate.num(intel.get("evidence_age_minutes"))
    max_age_minutes = float(policy.get("max_snapshot_age_seconds", 2100)) / 60.0
    return age is not None and 0 <= age <= max_age_minutes


def build_plan(
    config: dict,
    dynamic: dict,
    watch_state: dict,
    final_report: dict,
    *,
    generated_at: datetime | None = None,
) -> dict:
    now = (generated_at or gate.now_utc()).astimezone(timezone.utc)
    policy = gate._policy(config)
    targets = _target_map(config, dynamic, watch_state)
    decisions = {
        str(x.get("identity_key") or ""): x
        for x in (final_report.get("decisions") or [])
        if isinstance(x, dict) and x.get("identity_key")
    }
    candidates: list[dict] = []

    for key, target in targets.items():
        decision = decisions.get(key)
        if not isinstance(decision, dict):
            continue

        blockers = {str(x) for x in (decision.get("blockers") or []) if str(x)}
        ctype = str(target.get("candidate_type") or "").upper()
        quarter = decision.get("quarter_wave_revalidation")
        quarter = quarter if isinstance(quarter, dict) else {}
        quarter_enabled = bool(
            quarter.get("enabled_for_target")
            or target.get("quarter_wave_revalidation_lane") is True
        )

        if decision.get("pre_buy") is True:
            if not _current_intelligence_safe(decision, policy):
                continue
            if blockers & NON_RECHECKABLE_BLOCKERS:
                continue
            candidates.append({
                "identity_key": key,
                "symbol": str(target.get("symbol") or decision.get("symbol") or "").upper(),
                "candidate_type": ctype,
                "priority": 0,
                "reason": "PRE_BUY_CONFIRMATION_PENDING",
                "blockers": sorted(blockers),
            })
            continue

        if blockers & NON_RECHECKABLE_BLOCKERS:
            continue
        if not _current_intelligence_safe(decision, policy):
            continue

        # Quarter-wave candidates are worth an accelerated market refresh when
        # only a small number of market/timing gates remain. New-chain bootstrap
        # candidates get the same treatment only when intelligence confluence is
        # already present; the recheck never substitutes for deeper research.
        if quarter_enabled:
            if blockers and not blockers.issubset(MARKET_RECOVERABLE_BLOCKERS):
                continue
            if len(blockers) > 3:
                continue
            gain = gate.num(quarter.get("gain_from_anchor_pct"), 0.0) or 0.0
            candidates.append({
                "identity_key": key,
                "symbol": str(target.get("symbol") or decision.get("symbol") or "").upper(),
                "candidate_type": ctype,
                "priority": 1,
                "reason": "QUARTER_WAVE_CLOSE_WATCH",
                "quarter_wave_gain_pct": gain,
                "blockers": sorted(blockers),
            })
            continue

        if ctype == "NEW_CHAIN_BOOTSTRAP":
            if "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET" in blockers:
                continue
            if blockers and not blockers.issubset(MARKET_RECOVERABLE_BLOCKERS):
                continue
            if len(blockers) > 2:
                continue
            candidates.append({
                "identity_key": key,
                "symbol": str(target.get("symbol") or decision.get("symbol") or "").upper(),
                "candidate_type": ctype,
                "priority": 2,
                "reason": "NEW_CHAIN_CLOSE_WATCH",
                "blockers": sorted(blockers),
            })

    candidates.sort(
        key=lambda x: (
            int(x.get("priority") or 0),
            -float(x.get("quarter_wave_gain_pct") or 0),
            str(x.get("symbol") or ""),
        )
    )
    cap = max(1, int(policy.get("hot_recheck_max_targets", 8)))
    chosen = candidates[:cap]
    return {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": "HOT_CANDIDATE_FAST_RECHECK_V1",
        "count": len(chosen),
        "candidate_count_before_cap": len(candidates),
        "max_targets": cap,
        "delay_seconds": max(0, int(policy.get("hot_recheck_delay_seconds", 180))),
        "min_confirmation_spacing_seconds": max(
            0, int(policy.get("min_qualified_scan_spacing_seconds", 180))
        ),
        "targets": chosen,
        "truth_contract": {
            "no_extra_github_workflow_run": True,
            "recheck_runs_inside_existing_unified_watch_job": True,
            "pre_buy_is_highest_priority": True,
            "hard_risk_or_stale_intelligence_never_enters_recheck": True,
            "recheck_never_weakens_final_buy_gates": True,
            "second_qualified_scan_requires_real_time_spacing": True,
        },
    }


def _advance_intelligence_age(row: dict | None, report: dict, now: datetime) -> dict | None:
    if not isinstance(row, dict):
        return row
    out = dict(row)
    intel = out.get("intelligence")
    if isinstance(intel, dict):
        intel = dict(intel)
        original_age = gate.num(intel.get("evidence_age_minutes"))
        base_time = gate.parse_dt(out.get("observed_at") or report.get("updated_at"))
        if original_age is not None and base_time is not None:
            elapsed = max(0.0, (now - base_time).total_seconds() / 60.0)
            intel["evidence_age_minutes"] = round(original_age + elapsed, 6)
        out["intelligence"] = intel
    return out


def _refresh_market(target: dict, previous: dict, config: dict) -> dict:
    spread_limit = float((config.get("data_integrity") or {}).get("max_price_source_spread_pct", 2))
    ctype = str(target.get("candidate_type") or "").upper()
    scan_target = dict(target)
    is_spot = ctype in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY"}
    scan_target["dynamic_spot_candidate"] = is_spot
    scan_target["dynamic_cex_market_candidate"] = ctype == "CEX_MARKET_DISCOVERY"

    if ctype == "CEX_MARKET_DISCOVERY" or str(target.get("execution_identity_scope") or "").upper() == "EXACT_CEX_MARKET":
        live = engine.live_cex_market(scan_target)
    else:
        live = engine.live_exact_pair(scan_target, spread_limit)
        if str(target.get("exchange") or "").lower() == "gate" and target.get("currency_pair"):
            try:
                cex_snap = engine.gate_execution_snapshot(target.get("currency_pair"))
                live.update(cex_snap)
                cex_price = float(cex_snap.get("cex_price") or 0)
                dex_price = float(live.get("price") or 0)
                if cex_price > 0 and dex_price > 0:
                    med = statistics.median([cex_price, dex_price])
                    live["cex_market_price_spread_pct"] = (
                        abs(cex_price - dex_price) / med * 100.0 if med else 999.0
                    )
            except Exception as exc:
                live["cex_execution_verified"] = False
                live["cex_execution_error"] = f"{type(exc).__name__}:{str(exc)[:160]}"

    cex_sensor = engine.spot_cex_sensor(scan_target, previous)
    quarter_wave = {}
    if target.get("quarter_wave_revalidation_lane") is True:
        quarter_wave = engine.quarter_wave_revalidation(
            previous,
            float(live.get("price") or 0),
            live.get("observed_at"),
            anchor_price=(
                target.get("quarter_wave_anchor_price_usd")
                or target.get("first_seen_price")
                or target.get("discovery_price")
                or previous.get("first_verified_price")
            ),
            anchor_change_24h_pct=(
                target.get("first_seen_change_24h_pct")
                if target.get("first_seen_change_24h_pct") is not None
                else previous.get("first_seen_change_24h_pct")
            ),
            anchor_at=target.get("first_seen_at") or previous.get("first_verified_at"),
        )

    current = {
        **previous,
        "symbol": str(target.get("symbol") or previous.get("symbol") or "").upper(),
        "network": target.get("network") or previous.get("network") or "",
        "contract": target.get("contract") or previous.get("contract") or "",
        "pair": target.get("pair") or previous.get("pair") or "",
        "exchange": target.get("exchange") or previous.get("exchange"),
        "currency_pair": target.get("currency_pair") or previous.get("currency_pair"),
        "execution_identity_scope": target.get("execution_identity_scope") or previous.get("execution_identity_scope"),
        "dex_url": target.get("dex_url") or previous.get("dex_url") or "",
        "identity_key": gate.identity_key(target),
        "price": live.get("price"),
        "liquidity": live.get("liquidity"),
        "volume_h1": live.get("volume_h1"),
        "volume_h24": live.get("volume_h24"),
        "buys_h1": live.get("buys_h1"),
        "sells_h1": live.get("sells_h1"),
        "spread_pct": live.get("spread_pct"),
        "price_source_count": int(
            live.get("price_source_count")
            or (1 if ctype == "CEX_MARKET_DISCOVERY" else 0)
        ),
        "price_sources": list(
            live.get("price_sources")
            or (["gate"] if ctype == "CEX_MARKET_DISCOVERY" else [])
        ),
        "single_source_degraded": bool(live.get("single_source_degraded")),
        "single_source_error": live.get("single_source_error"),
        "observed_at": live.get("observed_at") or engine.now_iso(),
        "cex_execution_verified": live.get("cex_execution_verified"),
        "cex_execution_scope": live.get("cex_execution_scope"),
        "cex_price": live.get("cex_price"),
        "cex_market_price_spread_pct": live.get("cex_market_price_spread_pct"),
        "cex_orderbook_spread_pct": live.get("cex_orderbook_spread_pct"),
        "cex_bid_depth_1pct_usd": live.get("cex_bid_depth_1pct_usd"),
        "cex_ask_depth_1pct_usd": live.get("cex_ask_depth_1pct_usd"),
        "cex_depth_1pct_usd": live.get("cex_depth_1pct_usd"),
        "cex_bid_ask_depth_ratio": live.get("cex_bid_ask_depth_ratio"),
        "candidate_type": ctype or previous.get("candidate_type") or "CONFIGURED",
        "dynamic_spot_candidate": is_spot,
        "cex_quote_volume_24h_usd": cex_sensor.get("current_volume_usd"),
        "cex_quote_volume_baseline_usd": cex_sensor.get("baseline_volume_usd"),
        "cex_relative_volume_multiple": cex_sensor.get("baseline_multiple"),
        "cex_scan_volume_multiple": cex_sensor.get("scan_multiple"),
        "positive_gainer_rank": cex_sensor.get("current_rank"),
        "cex_led_revival": cex_sensor.get("cex_led"),
        "hot_recheck": True,
        **quarter_wave,
    }
    return current


def _merge_decisions(previous: list[dict], updates: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for row in previous:
        if not isinstance(row, dict):
            continue
        key = str(row.get("identity_key") or "")
        if key and key in updates:
            out.append(updates[key])
            seen.add(key)
        else:
            out.append(row)
            if key:
                seen.add(key)
    for key, row in updates.items():
        if key not in seen:
            out.append(row)
    return out


def execute_plan(plan: dict) -> dict:
    if int(plan.get("count") or 0) <= 0:
        return {
            "status": "NO_HOT_TARGETS",
            "count": 0,
            "evaluated": 0,
            "delivered": 0,
            "pre_buy_delivered": 0,
            "errors": [],
        }

    config = _load(gate.CONFIG, {})
    dynamic = _load(gate.DYNAMIC, {"candidates": []})
    watch_state = _load(gate.WATCH_STATE, {"version": 4, "tokens": {}})
    watch_report = _load(gate.WATCH_REPORT, {"targets": []})
    persistent = _load(gate.STATE, {"version": 1, "targets": {}})
    prior_report = _load(gate.REPORT, {"decisions": []})
    policy = gate._policy(config)
    targets = _target_map(config, dynamic, watch_state)

    engine.http_json = resilient_runner.resilient_http_json

    target_state = persistent.get("targets") if isinstance(persistent.get("targets"), dict) else {}
    target_state = dict(target_state)
    token_state = watch_state.get("tokens") if isinstance(watch_state.get("tokens"), dict) else {}
    token_state = dict(token_state)

    updates: dict[str, dict] = {}
    delivered: list[str] = []
    pre_buy_delivered: list[str] = []
    errors: list[dict] = []
    evaluated = 0
    started_at = gate.now_utc()

    for item in plan.get("targets") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("identity_key") or "")
        target = targets.get(key)
        if not key or not isinstance(target, dict):
            errors.append({"identity_key": key, "event": "HOT_RECHECK", "error": "TARGET_NOT_RESOLVED"})
            continue

        previous_market = gate.market_row(watch_state, key) or {}
        report_row = gate.report_row(watch_report, key)
        now = gate.now_utc()

        try:
            market = _refresh_market(target, previous_market, config)
            token_state[f"HOTRECHECK:{key}"] = market
            eval_report = _advance_intelligence_age(report_row, watch_report, now)
            if isinstance(eval_report, dict):
                eval_report = dict(eval_report)
                eval_report["market_verified"] = True
                eval_report["observed_at"] = market.get("observed_at") or now.isoformat()
                eval_report["_report_age_seconds"] = 0.0

            decision, next_state = gate.evaluate(
                target,
                market,
                eval_report,
                target_state.get(key),
                policy,
                now=now,
            )
            decision["hot_recheck"] = {
                "performed": True,
                "reason": item.get("reason"),
                "planned_at": plan.get("generated_at"),
                "rechecked_at": now.isoformat(),
            }
            evaluated += 1

            if decision.get("pre_buy_alert") is True:
                try:
                    gate.send_telegram(gate.telegram_message(target, decision))
                    pre_buy_delivered.append(key)
                    next_state["last_pre_buy_delivery_status"] = "DELIVERED"
                except Exception as exc:
                    next_state["pre_buy_armed"] = True
                    next_state.pop("last_pre_buy_alert_at", None)
                    next_state.pop("last_pre_buy_alert_price", None)
                    next_state["pre_buy_episode_count"] = int((target_state.get(key) or {}).get("pre_buy_episode_count") or 0)
                    next_state["last_pre_buy_delivery_status"] = f"ERROR:{type(exc).__name__}"
                    decision["pre_buy_alert"] = False
                    decision["pre_buy_delivery_error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
                    errors.append({"identity_key": key, "event": "PRE_BUY", "error": decision["pre_buy_delivery_error"]})

            if decision.get("alert") is True:
                try:
                    gate.send_telegram(gate.telegram_message(target, decision))
                    delivered.append(key)
                    next_state["last_delivery_status"] = "DELIVERED"
                except Exception as exc:
                    next_state["armed"] = True
                    next_state.pop("last_alert_at", None)
                    next_state.pop("last_alert_price", None)
                    next_state["buy_episode_count"] = int((target_state.get(key) or {}).get("buy_episode_count") or 0)
                    next_state["last_delivery_status"] = f"ERROR:{type(exc).__name__}"
                    decision["alert"] = False
                    decision["delivery_error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
                    errors.append({"identity_key": key, "event": "FINAL_BUY", "error": decision["delivery_error"]})

            target_state[key] = next_state
            updates[key] = decision
        except Exception as exc:
            errors.append({
                "identity_key": key,
                "event": "HOT_RECHECK_MARKET",
                "error": f"{type(exc).__name__}:{str(exc)[:220]}",
            })
            # Fail closed per target. Preserve the prior decision/state and do not
            # manufacture confirmation from an unavailable fresh market snapshot.
            continue

    watch_state["version"] = max(4, int(watch_state.get("version") or 0))
    watch_state["tokens"] = token_state
    gate.write(gate.WATCH_STATE, watch_state)

    persistent = {
        "version": 1,
        "updated_at": gate.now_iso(),
        "mode": gate.POLICY_MODE,
        "targets": target_state,
    }
    gate.write(gate.STATE, persistent)

    merged_decisions = _merge_decisions(
        [x for x in (prior_report.get("decisions") or []) if isinstance(x, dict)],
        updates,
    )
    existing_delivered = list(prior_report.get("delivered") or [])
    existing_pre_buy_delivered = list(prior_report.get("pre_buy_delivered") or [])
    existing_errors = list(prior_report.get("errors") or [])
    all_delivered = list(dict.fromkeys([*existing_delivered, *delivered]))
    all_prebuy = list(dict.fromkeys([*existing_pre_buy_delivered, *pre_buy_delivered]))
    all_errors = [*existing_errors, *errors]

    report = dict(prior_report)
    report["generated_at"] = gate.now_iso()
    report["decisions"] = merged_decisions
    report["buy_zone_count"] = sum(1 for x in merged_decisions if x.get("state") == "BUY_ZONE")
    report["pre_buy_count"] = sum(1 for x in merged_decisions if x.get("pre_buy") is True)
    report["delivered"] = all_delivered
    report["delivered_count"] = len(all_delivered)
    report["pre_buy_delivered"] = all_prebuy
    report["pre_buy_delivered_count"] = len(all_prebuy)
    report["errors"] = all_errors
    report["error_count"] = len(all_errors)
    report["last_hot_recheck"] = {
        "mode": "HOT_CANDIDATE_FAST_RECHECK_V1",
        "started_at": started_at.isoformat(),
        "completed_at": gate.now_iso(),
        "planned_count": int(plan.get("count") or 0),
        "evaluated_count": evaluated,
        "delivered_count": len(delivered),
        "pre_buy_delivered_count": len(pre_buy_delivered),
        "error_count": len(errors),
        "delay_seconds": int(plan.get("delay_seconds") or 0),
        "min_confirmation_spacing_seconds": int(plan.get("min_confirmation_spacing_seconds") or 0),
        "targets": [
            {
                "identity_key": x.get("identity_key"),
                "symbol": x.get("symbol"),
                "reason": x.get("reason"),
            }
            for x in (plan.get("targets") or [])
            if isinstance(x, dict)
        ],
    }
    gate.write(gate.REPORT, report)

    return {
        "status": "DELIVERY_ERROR" if any(x.get("event") in {"PRE_BUY", "FINAL_BUY"} for x in errors) else "OK",
        "count": int(plan.get("count") or 0),
        "evaluated": evaluated,
        "delivered": len(delivered),
        "pre_buy_delivered": len(pre_buy_delivered),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Wallet500 hot-candidate targeted fast recheck")
    parser.add_argument("command", choices=("plan", "execute"))
    parser.add_argument("--plan-path", default=str(DEFAULT_PLAN))
    args = parser.parse_args()
    plan_path = Path(args.plan_path)

    if args.command == "plan":
        config = _load(gate.CONFIG, {})
        dynamic = _load(gate.DYNAMIC, {"candidates": []})
        watch_state = _load(gate.WATCH_STATE, {"version": 4, "tokens": {}})
        final_report = _load(gate.REPORT, {"decisions": []})
        plan = build_plan(config, dynamic, watch_state, final_report)
        _write(plan_path, plan)
        print(json.dumps({
            "status": "PLAN_READY",
            "count": plan["count"],
            "delay_seconds": plan["delay_seconds"],
            "targets": [
                {"symbol": x.get("symbol"), "reason": x.get("reason")}
                for x in plan.get("targets") or []
            ],
        }, ensure_ascii=False))
        return 0

    plan = _load(plan_path, {"count": 0, "targets": []})
    result = execute_plan(plan)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("status") == "DELIVERY_ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
