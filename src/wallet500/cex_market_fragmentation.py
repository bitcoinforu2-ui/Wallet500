from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

USD_LIKE_QUOTES = {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI"}
DISPERSION_RATIO_SHADOW = 1.25
REGIONAL_LEAD_GAP_PCT_SHADOW = 10.0
VOLUME_STEP_MULTIPLE_SHADOW = 1.5
FOCUS_SYMBOL = "LSKUSDT"


def _f(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _read_state(path: Path) -> dict:
    gz = Path(str(path) + ".gz")
    try:
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _market_meta(key: str):
    parts = str(key).split(":", 3)
    if len(parts) != 4 or parts[0] != "spot":
        return None
    return {"exchange": parts[1], "symbol": parts[2], "market_id": parts[3]}


def build_timeline(state: dict) -> dict[str, list[dict]]:
    by_symbol: dict[str, dict[str, list[dict]]] = {}
    markets = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    for key, history in markets.items():
        meta = _market_meta(key)
        if meta is None or not isinstance(history, list):
            continue
        symbol = str(meta["symbol"]).upper()
        for point in history:
            if not isinstance(point, dict):
                continue
            observed_at = str(point.get("observed_at") or "")
            if not observed_at:
                continue
            by_symbol.setdefault(symbol, {}).setdefault(observed_at, []).append({**meta, **point})
    return {
        symbol: [{"observed_at": ts, "rows": rows} for ts, rows in sorted(points.items())]
        for symbol, points in by_symbol.items()
    }


def _snapshot_metrics(rows: list[dict]) -> dict:
    usd_rows = [
        x for x in rows
        if str(x.get("quote_symbol") or "USDT").upper() in USD_LIKE_QUOTES and _f(x.get("price")) > 0
    ]
    regional_rows = [
        x for x in rows
        if str(x.get("quote_symbol") or "USDT").upper() not in USD_LIKE_QUOTES
    ]

    prices = [_f(x.get("price")) for x in usd_rows]
    min_price = min(prices) if prices else 0.0
    max_price = max(prices) if prices else 0.0
    ratio = max_price / min_price if len(prices) >= 2 and min_price > 0 else 0.0

    nonregional_changes = [_f(x.get("change_24h_pct")) for x in usd_rows]
    regional_changes = [_f(x.get("change_24h_pct")) for x in regional_rows]
    nonregional_median = median(nonregional_changes) if nonregional_changes else 0.0
    regional_max = max(regional_changes) if regional_changes else 0.0
    regional_gap = regional_max - nonregional_median if regional_changes and nonregional_changes else 0.0

    return {
        "usd_like_venues": len({x.get("exchange") for x in usd_rows if x.get("exchange")}),
        "regional_venues": len({x.get("exchange") for x in regional_rows if x.get("exchange")}),
        "min_usd_like_price": round(min_price, 12),
        "max_usd_like_price": round(max_price, 12),
        "price_dispersion_ratio": round(ratio, 6),
        "price_dispersion_pct": round((ratio - 1.0) * 100.0, 4) if ratio else 0.0,
        "nonregional_change_median_pct": round(nonregional_median, 4),
        "regional_change_max_pct": round(regional_max, 4),
        "regional_lead_gap_pct": round(regional_gap, 4),
        "usd_like_volume_24h_sum": round(sum(_f(x.get("volume_24h")) for x in usd_rows), 6),
        "exchanges": sorted({str(x.get("exchange")) for x in rows if x.get("exchange")}),
    }


def analyze_symbol(points: list[dict]) -> list[dict]:
    out = []
    previous_volume = 0.0
    for point in points:
        metrics = _snapshot_metrics(point.get("rows") or [])
        volume = _f(metrics.get("usd_like_volume_24h_sum"))
        volume_multiple = volume / previous_volume if previous_volume > 0 and volume > 0 else 0.0
        features = []
        if metrics["usd_like_venues"] >= 2 and metrics["price_dispersion_ratio"] >= DISPERSION_RATIO_SHADOW:
            features.append("CROSS_VENUE_PRICE_DISPERSION_SHADOW")
        if (
            metrics["regional_venues"] >= 1
            and metrics["regional_change_max_pct"] >= REGIONAL_LEAD_GAP_PCT_SHADOW
            and metrics["regional_lead_gap_pct"] >= REGIONAL_LEAD_GAP_PCT_SHADOW
        ):
            features.append("REGIONAL_LEAD_DISLOCATION_SHADOW")
        if volume_multiple >= VOLUME_STEP_MULTIPLE_SHADOW:
            features.append("TURNOVER_STEP_EXPANSION_SHADOW")
        if "CROSS_VENUE_PRICE_DISPERSION_SHADOW" in features and len(features) >= 2:
            features.append("MARKET_FRAGMENTATION_COMPOSITE_SHADOW")
        out.append({
            "observed_at": point.get("observed_at"),
            **metrics,
            "volume_step_multiple": round(volume_multiple, 6),
            "shadow_features": features,
            "shadow_only": True,
            "affects_score": False,
            "actionable": False,
        })
        if volume > 0:
            previous_volume = volume
    return out


def _latest_feature_rows(timeline: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for symbol, points in timeline.items():
        analyzed = analyze_symbol(points)
        if not analyzed:
            continue
        latest = analyzed[-1]
        if not latest.get("shadow_features"):
            continue
        rows.append({"symbol": symbol, **latest})
    return sorted(
        rows,
        key=lambda x: (
            len(x.get("shadow_features") or []),
            _f(x.get("price_dispersion_ratio")),
            _f(x.get("regional_lead_gap_pct")),
            _f(x.get("volume_step_multiple")),
        ),
        reverse=True,
    )


def _update_forward_state(previous: dict, latest_rows: list[dict], now: str) -> dict:
    first = previous.get("first_feature_observed") if isinstance(previous.get("first_feature_observed"), dict) else {}
    first = {k: dict(v) if isinstance(v, dict) else {} for k, v in first.items()}
    new_events = 0
    for row in latest_rows:
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        bucket = first.setdefault(symbol, {})
        for feature in row.get("shadow_features") or []:
            if feature in bucket:
                continue
            bucket[feature] = {
                "observed_at": row.get("observed_at") or now,
                "price_dispersion_ratio": row.get("price_dispersion_ratio"),
                "regional_lead_gap_pct": row.get("regional_lead_gap_pct"),
                "volume_step_multiple": row.get("volume_step_multiple"),
                "immutable": True,
            }
            new_events += 1
    return {
        "version": 1,
        "updated_at": now,
        "mode": "FORWARD_ONLY_CEX_MARKET_FRAGMENTATION_SHADOW_STATE_V1",
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "new_feature_events": new_events,
        "first_feature_observed": first,
    }


def _focus_case(timeline: dict[str, list[dict]]) -> dict:
    analyzed = analyze_symbol(timeline.get(FOCUS_SYMBOL, []))
    feature_rows = [x for x in analyzed if x.get("shadow_features")]
    first_by_feature = {}
    for row in feature_rows:
        for feature in row.get("shadow_features") or []:
            first_by_feature.setdefault(feature, {
                "observed_at": row.get("observed_at"),
                "price_dispersion_ratio": row.get("price_dispersion_ratio"),
                "price_dispersion_pct": row.get("price_dispersion_pct"),
                "regional_lead_gap_pct": row.get("regional_lead_gap_pct"),
                "volume_step_multiple": row.get("volume_step_multiple"),
            })
    return {
        "symbol": FOCUS_SYMBOL,
        "retrospective_only": True,
        "production_claim_allowed": False,
        "reason": "LSK case study uses retained historical observations only; it may teach feature design but cannot rewrite prior production decisions.",
        "timeline_points": len(analyzed),
        "first_retained_observation_at": analyzed[0]["observed_at"] if analyzed else None,
        "first_retained_feature_by_type": first_by_feature,
        "latest": analyzed[-1] if analyzed else None,
        "feature_rows_tail": feature_rows[-12:],
    }


def run(out: Path, now: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc).isoformat()
    state = _read_state(out / "cex-spot-state.json")
    previous = _read_json(out / "cex-market-fragmentation-state.json", {})
    timeline = build_timeline(state)
    latest_rows = _latest_feature_rows(timeline)
    forward_state = _update_forward_state(previous, latest_rows, now)
    (out / "cex-market-fragmentation-state.json").write_text(json.dumps(forward_state, indent=2), encoding="utf-8")

    payload = {
        "version": 1,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_CEX_MARKET_FRAGMENTATION_V1",
        "production_effect": False,
        "automatic_buy": False,
        "production_thresholds_modified": False,
        "liquidity_gate_modified": False,
        "identity_rules_modified": False,
        "truth_contract": {
            "usd_like_prices_only_used_for_cross_venue_dispersion": True,
            "regional_native_quotes_never_compared_directly_to_usd_prices": True,
            "shadow_features_never_change_score": True,
            "forward_first_feature_state_is_immutable": True,
            "retrospective_case_study_never_rewrites_production_history": True,
            "exact_pair_and_identity_rules_unchanged": True,
            "no_hindsight": True,
        },
        "thresholds_shadow_only": {
            "cross_venue_price_dispersion_ratio": DISPERSION_RATIO_SHADOW,
            "regional_lead_gap_pct": REGIONAL_LEAD_GAP_PCT_SHADOW,
            "volume_step_multiple": VOLUME_STEP_MULTIPLE_SHADOW,
        },
        "symbols_with_current_shadow_features": len(latest_rows),
        "current_shadow_candidates": latest_rows[:100],
        "forward_state_new_feature_events": forward_state.get("new_feature_events", 0),
        "focus_case": _focus_case(timeline),
    }
    (out / "cex-market-fragmentation-research.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(Path("data")), indent=2))
