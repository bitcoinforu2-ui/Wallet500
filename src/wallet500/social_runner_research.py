from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping

MODE = "RESEARCH_ONLY_SOCIAL_RUNNER_INTELLIGENCE_V1"
VERSION = 1
WINDOW_HOURS = {"3h": 3.0, "24h": 24.0, "3d": 72.0, "7d": 168.0, "21d": 504.0}
DEFAULT_THRESHOLDS = {
    "attention_jump_min": 3.0,
    "velocity_3d_vs_21d_min": 2.0,
    "organic_share_min": 0.65,
    "first_time_ratio_min": 0.20,
    "unique_communities_min": 3,
    "coordination_max": 0.50,
    "hard_coordination_max": 0.75,
    "false_social_organic_max": 0.20,
    "late_pre_24h_return_pct": 25.0,
    "late_pre_72h_return_pct": 60.0,
    "volume_ratio_confirm": 1.50,
    "buy_sell_imbalance_confirm": 0.15,
    "liquidity_change_confirm_pct": 5.0,
    "new_holder_change_confirm_pct": 3.0,
    "smart_wallet_confirm": 60.0,
    "exchange_inflow_distribution": 70.0,
    "distribution_sell_imbalance": -0.15,
}
OUTCOME_TARGETS = {
    "RUNNER_24H": {"horizon_hours": 24.0, "target_pct": 25.0, "max_pre_hit_drawdown_pct": -12.0},
    "RUNNER_72H": {"horizon_hours": 72.0, "target_pct": 40.0, "max_pre_hit_drawdown_pct": -15.0},
    "MOONSHOT_7D": {"horizon_hours": 168.0, "target_pct": 100.0, "max_pre_hit_drawdown_pct": -20.0},
}


def _n(value: Any, default: float | None = 0.0) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den else default


def coverage_adjusted_rate(mentions: Any, indexed_communities: Any, hours: float) -> dict:
    """Mentions per 10k indexed communities per hour.

    Coverage normalization is only claimed when a positive source-universe count is
    supplied. Missing coverage never receives a synthetic denominator.
    """
    m = max(0.0, _n(mentions, 0.0) or 0.0)
    coverage = _n(indexed_communities, None)
    h = max(float(hours), 1e-9)
    raw_per_hour = m / h
    if coverage is None or coverage <= 0:
        return {
            "mentions": m,
            "hours": h,
            "indexed_communities": None,
            "raw_per_hour": round(raw_per_hour, 8),
            "coverage_adjusted": False,
            "mentions_per_10k_communities_per_hour": None,
        }
    adjusted = (m / coverage) * 10000.0 / h
    return {
        "mentions": m,
        "hours": h,
        "indexed_communities": coverage,
        "raw_per_hour": round(raw_per_hour, 8),
        "coverage_adjusted": True,
        "mentions_per_10k_communities_per_hour": round(adjusted, 8),
    }


def _window_rate(window: Mapping[str, Any] | None, label: str) -> dict:
    row = window if isinstance(window, Mapping) else {}
    return coverage_adjusted_rate(row.get("mentions"), row.get("indexed_communities"), WINDOW_HOURS[label])


def _comparable_rate(row: Mapping[str, Any]) -> float:
    adjusted = _n(row.get("mentions_per_10k_communities_per_hour"), None)
    if adjusted is not None:
        return adjusted
    return _n(row.get("raw_per_hour"), 0.0) or 0.0


def _ratio_with_floor(current: float, baseline: float) -> float:
    if current <= 0:
        return 0.0
    floor = max(1e-9, min(0.25, current * 0.25))
    return current / max(baseline, floor)


def build_features(snapshot: Mapping[str, Any]) -> dict:
    """Build no-hindsight features from a single t0 research snapshot."""
    windows = snapshot.get("windows") if isinstance(snapshot.get("windows"), Mapping) else {}
    rates = {label: _window_rate(windows.get(label), label) for label in WINDOW_HOURS}
    comparable = {label: _comparable_rate(row) for label, row in rates.items()}
    coverage_ready = all(rates[label]["coverage_adjusted"] for label in ("3d", "7d", "21d"))

    raw_mentions = _n(snapshot.get("raw_mentions_24h"), None)
    organic_mentions = _n(snapshot.get("organic_mentions_24h"), None)
    organic_share = _n(snapshot.get("organic_share"), None)
    if organic_share is None and raw_mentions is not None and raw_mentions > 0 and organic_mentions is not None:
        organic_share = organic_mentions / raw_mentions
    if organic_share is not None:
        organic_share = max(0.0, min(1.0, organic_share))

    unique_communities = _i(snapshot.get("unique_communities"), 0)
    first_time_communities = _i(snapshot.get("first_time_communities"), 0)
    first_time_ratio = _safe_div(first_time_communities, unique_communities, 0.0)

    reach_current = _n(snapshot.get("reach_current"), None)
    reach_baseline = _n(snapshot.get("reach_baseline"), None)
    reach_acceleration = None
    if reach_current is not None and reach_baseline is not None and reach_baseline > 0:
        reach_acceleration = reach_current / reach_baseline

    large_current = _n(snapshot.get("large_channel_mentions"), 0.0) or 0.0
    large_baseline = _n(snapshot.get("large_channel_baseline"), 0.0) or 0.0
    large_channel_emergence = max(0.0, large_current - large_baseline)

    platform_mentions = snapshot.get("platform_mentions") if isinstance(snapshot.get("platform_mentions"), Mapping) else {}
    platform_count = sum(1 for p in ("telegram", "x", "reddit") if (_n(platform_mentions.get(p), 0.0) or 0.0) > 0)

    coordination_ratio = max(0.0, min(1.0, _n(snapshot.get("coordination_ratio"), 0.0) or 0.0))
    market = snapshot.get("market") if isinstance(snapshot.get("market"), Mapping) else {}
    onchain = snapshot.get("onchain") if isinstance(snapshot.get("onchain"), Mapping) else {}

    return {
        "observed_at": snapshot.get("observed_at"),
        "chain": snapshot.get("chain"),
        "contract": snapshot.get("contract") or snapshot.get("token_address") or snapshot.get("mint"),
        "symbol": snapshot.get("symbol"),
        "coverage_ready": coverage_ready,
        "window_rates": rates,
        "attention_jump_3h_vs_21d": round(_ratio_with_floor(comparable["3h"], comparable["21d"]), 4),
        "velocity_24h_vs_7d": round(_ratio_with_floor(comparable["24h"], comparable["7d"]), 4),
        "velocity_3d_vs_21d": round(_ratio_with_floor(comparable["3d"], comparable["21d"]), 4),
        "velocity_7d_vs_21d": round(_ratio_with_floor(comparable["7d"], comparable["21d"]), 4),
        "organic_share": None if organic_share is None else round(organic_share, 4),
        "unique_communities": unique_communities,
        "first_time_communities": first_time_communities,
        "first_time_community_ratio": round(first_time_ratio, 4),
        "reach_acceleration": None if reach_acceleration is None else round(reach_acceleration, 4),
        "large_channel_emergence": round(large_channel_emergence, 4),
        "cross_platform_count": platform_count,
        "platform_mentions": {k: _i(platform_mentions.get(k), 0) for k in ("telegram", "x", "reddit")},
        "coordination_ratio": round(coordination_ratio, 4),
        "pre_24h_return_pct": _n(market.get("pre_24h_return_pct"), None),
        "pre_72h_return_pct": _n(market.get("pre_72h_return_pct"), None),
        "volume_ratio": _n(market.get("volume_ratio"), None),
        "buy_sell_imbalance": _n(market.get("buy_sell_imbalance"), None),
        "liquidity_change_pct": _n(market.get("liquidity_change_pct"), None),
        "new_holder_change_pct": _n(onchain.get("new_holder_change_pct"), None),
        "smart_wallet_accumulation_score": _n(onchain.get("smart_wallet_accumulation_score"), None),
        "exchange_inflow_score": _n(onchain.get("exchange_inflow_score"), None),
        "catalyst_confirmed": bool(snapshot.get("catalyst_confirmed") or snapshot.get("news_confirmed")),
        "source": snapshot.get("source") or "UNKNOWN",
    }


def classify_features(features: Mapping[str, Any], thresholds: Mapping[str, Any] | None = None) -> dict:
    t = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        t.update(thresholds)

    organic = _n(features.get("organic_share"), None)
    unique = _i(features.get("unique_communities"), 0)
    first_ratio = _n(features.get("first_time_community_ratio"), 0.0) or 0.0
    coordination = _n(features.get("coordination_ratio"), 0.0) or 0.0
    jump = _n(features.get("attention_jump_3h_vs_21d"), 0.0) or 0.0
    v3 = _n(features.get("velocity_3d_vs_21d"), 0.0) or 0.0
    pre24 = _n(features.get("pre_24h_return_pct"), None)
    pre72 = _n(features.get("pre_72h_return_pct"), None)

    reasons: list[str] = []
    attention = jump >= t["attention_jump_min"] or v3 >= t["velocity_3d_vs_21d_min"]
    quality_known = organic is not None
    quality = quality_known and organic >= t["organic_share_min"] and coordination <= t["coordination_max"]
    breadth = unique >= t["unique_communities_min"] and first_ratio >= t["first_time_ratio_min"]
    late = (pre24 is not None and pre24 >= t["late_pre_24h_return_pct"]) or (
        pre72 is not None and pre72 >= t["late_pre_72h_return_pct"]
    )
    false_social = coordination >= t["hard_coordination_max"] or (
        organic is not None and organic <= t["false_social_organic_max"] and coordination >= t["coordination_max"]
    )

    buy_sell = _n(features.get("buy_sell_imbalance"), None)
    exchange_inflow = _n(features.get("exchange_inflow_score"), None)
    volume_ratio = _n(features.get("volume_ratio"), None)
    liquidity_change = _n(features.get("liquidity_change_pct"), None)
    distribution = (
        exchange_inflow is not None
        and exchange_inflow >= t["exchange_inflow_distribution"]
        and buy_sell is not None
        and buy_sell <= t["distribution_sell_imbalance"]
    ) or (
        volume_ratio is not None
        and volume_ratio >= 2.0
        and buy_sell is not None
        and buy_sell <= -0.25
        and liquidity_change is not None
        and liquidity_change < 0
    )

    market_confirmations = 0
    if volume_ratio is not None and volume_ratio >= t["volume_ratio_confirm"]:
        market_confirmations += 1
        reasons.append("VOLUME_ACCELERATION")
    if buy_sell is not None and buy_sell >= t["buy_sell_imbalance_confirm"]:
        market_confirmations += 1
        reasons.append("BUY_IMBALANCE")
    if liquidity_change is not None and liquidity_change >= t["liquidity_change_confirm_pct"]:
        market_confirmations += 1
        reasons.append("LIQUIDITY_EXPANSION")

    onchain_confirmations = 0
    holder_change = _n(features.get("new_holder_change_pct"), None)
    smart_wallet = _n(features.get("smart_wallet_accumulation_score"), None)
    if holder_change is not None and holder_change >= t["new_holder_change_confirm_pct"]:
        onchain_confirmations += 1
        reasons.append("HOLDER_GROWTH")
    if smart_wallet is not None and smart_wallet >= t["smart_wallet_confirm"]:
        onchain_confirmations += 1
        reasons.append("SMART_WALLET_ACCUMULATION")
    if features.get("catalyst_confirmed"):
        reasons.append("CATALYST_CONFIRMED")

    if attention:
        reasons.append("ATTENTION_ACCELERATION")
    if breadth:
        reasons.append("FIRST_TIME_COMMUNITY_SPREAD")
    if quality:
        reasons.append("ORGANIC_QUALITY")
    if _i(features.get("cross_platform_count"), 0) >= 2:
        reasons.append("CROSS_PLATFORM_CONFIRMATION")

    if false_social:
        state = "DISTRIBUTION_FALSE_SOCIAL"
        reasons.append("COORDINATED_OR_LOW_ORGANIC_SOCIAL")
    elif distribution:
        state = "DISTRIBUTION_FALSE_SOCIAL"
        reasons.append("DISTRIBUTION_FLOW")
    elif late:
        state = "LATE_ATTENTION"
        reasons.append("PRICE_MOVED_BEFORE_ATTENTION")
    elif not quality_known:
        state = "INSUFFICIENT_EVIDENCE"
        reasons.append("ORGANIC_QUALITY_UNKNOWN")
    elif attention and quality and breadth and market_confirmations >= 2 and onchain_confirmations >= 1:
        state = "CONFIRMED_RUNNER"
    elif attention and quality and breadth:
        state = "EARLY_RUNNER"
    else:
        state = "INSUFFICIENT_EVIDENCE"
        reasons.append("NO_CLEAN_CONFLUENCE_YET")

    return {
        "state": state,
        "reasons": sorted(set(reasons)),
        "market_confirmations": market_confirmations,
        "onchain_confirmations": onchain_confirmations,
        "late_attention_penalty": late,
        "distribution_risk": distribution,
        "false_social_risk": false_social,
        "thresholds_are_research_hypotheses": True,
        "research_only": True,
        "actionable": False,
        "automatic_buy": False,
        "production_effect": False,
    }


def _price_points(path: Iterable[Mapping[str, Any]], baseline_price: float) -> list[dict]:
    points = []
    for row in path:
        h = _n(row.get("hours_from_t0"), None)
        p = _n(row.get("price"), None)
        if h is None or p is None or h < 0 or p <= 0:
            continue
        points.append({"hours_from_t0": h, "price": p, "return_pct": (p / baseline_price - 1.0) * 100.0})
    points.sort(key=lambda x: x["hours_from_t0"])
    return points


def _checkpoint(points: list[dict], horizon: float) -> float | None:
    eligible = [p for p in points if p["hours_from_t0"] <= horizon]
    if not eligible:
        return None
    return round(eligible[-1]["return_pct"], 4)


def _target_result(points: list[dict], cfg: Mapping[str, Any]) -> dict:
    horizon = float(cfg["horizon_hours"])
    target = float(cfg["target_pct"])
    max_dd = float(cfg["max_pre_hit_drawdown_pct"])
    eligible = [p for p in points if p["hours_from_t0"] <= horizon]
    hit = None
    running_min = 0.0
    for p in eligible:
        running_min = min(running_min, p["return_pct"])
        if p["return_pct"] >= target:
            hit = p
            break
    qualified = bool(hit is not None and running_min >= max_dd)
    return {
        "qualified": qualified,
        "target_pct": target,
        "horizon_hours": horizon,
        "max_pre_hit_drawdown_pct": max_dd,
        "time_to_hit_hours": None if hit is None else round(hit["hours_from_t0"], 4),
        "pre_hit_mae_pct": None if hit is None else round(running_min, 4),
        "hit_target_but_drawdown_failed": bool(hit is not None and not qualified),
    }


def label_outcome(baseline_price: Any, price_path: Iterable[Mapping[str, Any]]) -> dict:
    base = _n(baseline_price, None)
    if base is None or base <= 0:
        return {"valid": False, "reason": "INVALID_BASELINE_PRICE"}
    points = _price_points(price_path, base)
    if not points:
        return {"valid": False, "reason": "NO_VALID_POST_T0_PRICES"}
    upto7d = [p for p in points if p["hours_from_t0"] <= 168.0]
    returns = [p["return_pct"] for p in upto7d]
    targets = {name: _target_result(points, cfg) for name, cfg in OUTCOME_TARGETS.items()}
    return {
        "valid": True,
        "baseline_price": base,
        "checkpoints_pct": {str(int(h)): _checkpoint(points, h) for h in (1.0, 4.0, 24.0, 72.0, 168.0)},
        "mfe_7d_pct": round(max(returns), 4) if returns else None,
        "mae_7d_pct": round(min(returns), 4) if returns else None,
        "targets": targets,
        "runner_24h": targets["RUNNER_24H"]["qualified"],
        "runner_72h": targets["RUNNER_72H"]["qualified"],
        "moonshot_7d": targets["MOONSHOT_7D"]["qualified"],
    }


def _summary(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "runner_24h_rate_pct": None, "runner_72h_rate_pct": None, "moonshot_7d_rate_pct": None}
    valid = [r for r in rows if (r.get("outcome") or {}).get("valid")]
    if not valid:
        return {"n": len(rows), "valid_outcomes": 0, "runner_24h_rate_pct": None, "runner_72h_rate_pct": None, "moonshot_7d_rate_pct": None}
    mfes = [r["outcome"]["mfe_7d_pct"] for r in valid if r["outcome"].get("mfe_7d_pct") is not None]
    return {
        "n": len(rows),
        "valid_outcomes": len(valid),
        "runner_24h_rate_pct": round(sum(bool(r["outcome"].get("runner_24h")) for r in valid) / len(valid) * 100.0, 2),
        "runner_72h_rate_pct": round(sum(bool(r["outcome"].get("runner_72h")) for r in valid) / len(valid) * 100.0, 2),
        "moonshot_7d_rate_pct": round(sum(bool(r["outcome"].get("moonshot_7d")) for r in valid) / len(valid) * 100.0, 2),
        "median_mfe_7d_pct": round(median(mfes), 4) if mfes else None,
        "mean_mfe_7d_pct": round(mean(mfes), 4) if mfes else None,
    }


def build_cohort(events: Iterable[Mapping[str, Any]], thresholds: Mapping[str, Any] | None = None) -> dict:
    rows = []
    for event in events:
        snapshot = event.get("snapshot") if isinstance(event.get("snapshot"), Mapping) else event
        features = build_features(snapshot)
        classification = classify_features(features, thresholds)
        outcome = label_outcome(event.get("baseline_price"), event.get("price_path") or [])
        rows.append({
            "event_id": event.get("event_id"),
            "observed_at": features.get("observed_at"),
            "chain": features.get("chain"),
            "contract": features.get("contract"),
            "symbol": features.get("symbol"),
            "features": features,
            "classification": classification,
            "outcome": outcome,
        })

    by_state: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_state[row["classification"]["state"]].append(row)
    return {
        "version": VERSION,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "no_hindsight": True,
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "target_definitions": OUTCOME_TARGETS,
        "thresholds": {**DEFAULT_THRESHOLDS, **(dict(thresholds) if thresholds else {})},
        "counts": dict(Counter(row["classification"]["state"] for row in rows)),
        "state_outcomes": {state: _summary(group) for state, group in sorted(by_state.items())},
        "rows": rows,
    }


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_live_observations(data_dir: Path, snapshots: Iterable[Mapping[str, Any]], thresholds: Mapping[str, Any] | None = None) -> dict:
    """Append deduplicated t0 research observations to a local forward ledger.

    Persistence is intentionally filesystem-local. The caller/workflow is responsible
    for durable storage; this module never commits data or mutates production signals.
    """
    path = data_dir / "social-runner-live-ledger.json"
    ledger = _load(path, {"version": VERSION, "mode": MODE, "observations": []})
    existing = ledger.get("observations") if isinstance(ledger.get("observations"), list) else []
    seen = {str(row.get("observation_id")) for row in existing if isinstance(row, Mapping)}
    added = 0
    for snap in snapshots:
        features = build_features(snap)
        observed = str(features.get("observed_at") or "")
        key = f"{str(features.get('chain') or '').lower()}:{str(features.get('contract') or '').lower()}:{observed}"
        if not observed or key in seen:
            continue
        classification = classify_features(features, thresholds)
        existing.append({
            "observation_id": key,
            "observed_at": observed,
            "features": features,
            "classification": classification,
            "outcome": None,
        })
        seen.add(key)
        added += 1
    ledger.update({
        "version": VERSION,
        "mode": MODE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "observations": existing,
    })
    _write(path, ledger)
    return {"path": str(path), "added": added, "total": len(existing)}


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    feed = _load(data / "social-runner-research-feed.json", {})
    snapshots = feed.get("snapshots") if isinstance(feed, Mapping) else []
    historical = feed.get("historical_events") if isinstance(feed, Mapping) else []
    snapshots = snapshots if isinstance(snapshots, list) else []
    historical = historical if isinstance(historical, list) else []

    live = append_live_observations(data, snapshots)
    cohort = build_cohort(historical)
    cohort["input_status"] = {
        "feed_file": "social-runner-research-feed.json",
        "feed_present": (data / "social-runner-research-feed.json").exists(),
        "snapshots": len(snapshots),
        "historical_events": len(historical),
        "note": "TGMetrics private-beta data may be supplied here when licensed/configured; no undocumented endpoint or HTML scraping is used.",
    }
    out = data / "social-runner-research.json"
    _write(out, cohort)
    return {
        "status": "OK",
        "mode": MODE,
        "research_output": str(out),
        "live_ledger": live,
        "historical_events": len(historical),
        "production_effect": False,
        "automatic_buy": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
