from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

LEVERAGED_SUFFIXES = ("2L", "2S", "3L", "3S", "4L", "4S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN")
POSTMORTEM_MOVE_PCT = 50.0
MISS_CLASSES = (
    "DISCOVERY_MISS",
    "PROMOTION_MISS",
    "IDENTITY_BLOCKED",
    "LIQUIDITY_BLOCKED",
    "INTENTIONAL_EXCLUSION",
)


def _f(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _read_state(path: Path):
    gz = Path(str(path) + ".gz")
    try:
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _base_symbol(symbol: str) -> str:
    value = str(symbol or "").upper().strip().replace("-", "").replace("_", "").replace("/", "")
    return value[:-4] if value.endswith("USDT") else value


def leveraged_underlying(symbol: str) -> str | None:
    base = _base_symbol(symbol)
    for suffix in LEVERAGED_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            return base[: -len(suffix)]
    return None


def classify_postmortem(*, observed: bool, promoted: bool, intentional_exclusion: bool = False,
                        identity_verified: bool | None = None, liquidity_gate: bool | None = None) -> str:
    if intentional_exclusion:
        return "INTENTIONAL_EXCLUSION"
    if not observed:
        return "DISCOVERY_MISS"
    if not promoted:
        return "PROMOTION_MISS"
    if identity_verified is False:
        return "IDENTITY_BLOCKED"
    if identity_verified is True and liquidity_gate is False:
        return "LIQUIDITY_BLOCKED"
    return "PROMOTED_RESEARCH"


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _identity_index(payload: dict) -> dict[str, dict]:
    indexed = {}
    for row in _walk_dicts(payload):
        symbol = str(row.get("symbol") or "").upper()
        if not symbol.endswith("USDT"):
            continue
        if any(key in row for key in ("identity_status", "identity_verified", "liquidity_execution_gate_eligible")):
            indexed[symbol] = row
    return indexed


def _parse_market_key(key: str):
    parts = str(key).split(":", 3)
    if len(parts) != 4 or parts[0] != "spot":
        return None
    return {"exchange": parts[1], "symbol": parts[2], "market_id": parts[3]}


def _latest_rows(state: dict) -> list[dict]:
    rows = []
    markets = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    for key, history in markets.items():
        meta = _parse_market_key(key)
        if meta is None or not isinstance(history, list) or not history:
            continue
        latest = history[-1] if isinstance(history[-1], dict) else {}
        rows.append({"key": key, **meta, **latest})
    return rows


def _update_immutable_ledger(state: dict, previous: dict, now: str) -> dict:
    entries = previous.get("markets") if isinstance(previous.get("markets"), dict) else {}
    entries = dict(entries)
    histories = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    added = 0
    for key, history in histories.items():
        if key in entries or not isinstance(history, list) or not history:
            continue
        meta = _parse_market_key(key)
        if meta is None:
            continue
        first = next((x for x in history if isinstance(x, dict) and _f(x.get("price")) > 0), None)
        if not first:
            continue
        exact = len(history) == 1
        entries[key] = {
            **meta,
            "base_symbol": _base_symbol(meta["symbol"]),
            "first_observed_at": first.get("observed_at"),
            "first_observed_price": _f(first.get("price")),
            "first_observed_volume_24h": _f(first.get("volume_24h")),
            "quote_symbol": first.get("quote_symbol"),
            "first_seen_exact": exact,
            "source": "LIVE_FIRST_OBSERVATION" if exact else "MIGRATED_RETAINED_HISTORY_LOWER_BOUND",
            "immutable": True,
        }
        added += 1
    return {
        "version": 1,
        "updated_at": now,
        "mode": "IMMUTABLE_CEX_SPOT_OBSERVATION_LEDGER_V1",
        "truth_contract": {
            "existing_first_observation_never_rewritten": True,
            "retained_history_migration_never_claimed_as_exact_first_seen": True,
            "no_hindsight": True,
            "production_effect": False,
        },
        "market_count": len(entries),
        "new_markets_added": added,
        "markets": entries,
    }


def _leveraged_shadow(latest: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in latest:
        underlying = leveraged_underlying(row.get("symbol"))
        if not underlying:
            continue
        bucket = grouped.setdefault(underlying, {
            "underlying": underlying,
            "products": set(),
            "exchanges": set(),
            "max_change_24h_pct": 0.0,
            "max_abs_change_24h_pct": 0.0,
            "max_volume_24h": 0.0,
        })
        change = _f(row.get("change_24h_pct"))
        bucket["products"].add(row.get("symbol"))
        bucket["exchanges"].add(row.get("exchange"))
        if abs(change) >= bucket["max_abs_change_24h_pct"]:
            bucket["max_abs_change_24h_pct"] = abs(change)
            bucket["max_change_24h_pct"] = change
        bucket["max_volume_24h"] = max(bucket["max_volume_24h"], _f(row.get("volume_24h")))
    out = []
    for bucket in grouped.values():
        out.append({
            "underlying": bucket["underlying"],
            "products": sorted(x for x in bucket["products"] if x),
            "exchanges": sorted(x for x in bucket["exchanges"] if x),
            "max_change_24h_pct": round(bucket["max_change_24h_pct"], 6),
            "max_abs_change_24h_pct": round(bucket["max_abs_change_24h_pct"], 6),
            "max_volume_24h": round(bucket["max_volume_24h"], 6),
            "shadow_only": True,
            "affects_score": False,
            "actionable": False,
            "production_effect": False,
        })
    return sorted(out, key=lambda x: (x["max_abs_change_24h_pct"], len(x["products"])), reverse=True)


def build_observation_intel(out: Path, now: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc).isoformat()
    state = _read_state(out / "cex-spot-state.json")
    radar = _read_json(out / "cex-spot-revival-radar.json", {})
    identity = _read_json(out / "cex-spot-identity-radar.json", {})
    previous_ledger = _read_json(out / "cex-spot-observation-ledger.json", {})

    ledger = _update_immutable_ledger(state, previous_ledger, now)
    (out / "cex-spot-observation-ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    latest = _latest_rows(state)
    watch_symbols = {
        str(x.get("symbol") or "").upper()
        for lane in (radar.get("watchlist", []), radar.get("alerts", []))
        if isinstance(lane, list)
        for x in lane
        if isinstance(x, dict)
    }
    identity_by_symbol = _identity_index(identity)
    milestones_by_symbol = state.get("signal_milestones") if isinstance(state.get("signal_milestones"), dict) else {}

    current_symbols: dict[str, list[dict]] = {}
    diagnostics = []
    for row in latest:
        symbol = str(row.get("symbol") or "").upper()
        current_symbols.setdefault(symbol, []).append(row)

    for symbol, rows in current_symbols.items():
        underlying = leveraged_underlying(symbol)
        max_change = max((_f(x.get("change_24h_pct")) for x in rows), default=0.0)
        if underlying:
            if abs(max_change) >= POSTMORTEM_MOVE_PCT:
                diagnostics.append({
                    "symbol": symbol,
                    "underlying": underlying,
                    "change_24h_max_pct": round(max_change, 6),
                    "class": "INTENTIONAL_EXCLUSION",
                    "reason": "LEVERAGED_CEX_PRODUCT_RESEARCH_SENSOR_ONLY",
                })
            continue
        if max_change < POSTMORTEM_MOVE_PCT:
            continue
        ident = identity_by_symbol.get(symbol, {})
        milestones = milestones_by_symbol.get(symbol) if isinstance(milestones_by_symbol.get(symbol), dict) else {}
        immutable_promotion = bool(
            isinstance(milestones.get("first_watch"), dict)
            or isinstance(milestones.get("first_alert"), dict)
        )
        promoted = symbol in watch_symbols or immutable_promotion
        identity_verified = ident.get("identity_verified") if "identity_verified" in ident else None
        liquidity_gate = ident.get("liquidity_execution_gate_eligible") if "liquidity_execution_gate_eligible" in ident else None
        cls = classify_postmortem(
            observed=True,
            promoted=promoted,
            identity_verified=identity_verified,
            liquidity_gate=liquidity_gate,
        )
        diagnostics.append({
            "symbol": symbol,
            "change_24h_max_pct": round(max_change, 6),
            "class": cls,
            "promoted_to_research_watch": promoted,
            "current_watch_membership": symbol in watch_symbols,
            "immutable_promotion_milestone": immutable_promotion,
            "identity_verified": identity_verified,
            "liquidity_execution_gate_eligible": liquidity_gate,
            "identity_status": ident.get("identity_status"),
            "blocker": ident.get("blocker") or ident.get("reason"),
        })

    shadow = _leveraged_shadow(latest)
    payload = {
        "version": 1,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_CEX_OBSERVATION_INTELLIGENCE_V1",
        "production_effect": False,
        "automatic_buy": False,
        "production_thresholds_modified": False,
        "liquidity_minimum_modified": False,
        "identity_rules_modified": False,
        "truth_contract": {
            "leveraged_products_remain_excluded_from_production": True,
            "leveraged_underlying_evidence_shadow_only": True,
            "shadow_evidence_never_changes_score": True,
            "immutable_first_observation_ledger": True,
            "migration_bounds_are_not_relabelled_exact": True,
            "no_hindsight_for_production": True,
            "fail_closed": True,
        },
        "miss_taxonomy": list(MISS_CLASSES),
        "discovery_miss_note": "DISCOVERY_MISS requires an external benchmark asset absent from the observation ledger; it is never inferred from observed assets.",
        "postmortem_move_threshold_24h_pct": POSTMORTEM_MOVE_PCT,
        "observation_market_count": ledger.get("market_count", 0),
        "observation_new_markets_added": ledger.get("new_markets_added", 0),
        "leveraged_underlying_shadow_count": len(shadow),
        "leveraged_underlying_shadow": shadow[:100],
        "mover_diagnostics_count": len(diagnostics),
        "mover_diagnostics": sorted(diagnostics, key=lambda x: abs(_f(x.get("change_24h_max_pct"))), reverse=True),
    }
    (out / "cex-spot-observation-intel.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_observation_intel(Path("data")), indent=2))
