from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

USD_LIKE_QUOTES = {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI"}
MIN_GROSS_SPREAD_PCT_SHADOW = 3.0
EXTREME_SPREAD_PCT_SHADOW = 20.0


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


def build_snapshots(state: dict) -> dict[str, list[dict]]:
    grouped: dict[str, dict[str, list[dict]]] = {}
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
            quote = str(point.get("quote_symbol") or "USDT").upper()
            price = _f(point.get("price"))
            if not observed_at or quote not in USD_LIKE_QUOTES or price <= 0:
                continue
            grouped.setdefault(symbol, {}).setdefault(observed_at, []).append({**meta, **point})
    return {
        symbol: [{"observed_at": ts, "rows": rows} for ts, rows in sorted(points.items())]
        for symbol, points in grouped.items()
    }


def _route_lookup(routes: dict, symbol: str, buy_exchange: str, sell_exchange: str) -> dict | None:
    rows = routes.get("routes") if isinstance(routes.get("routes"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").upper() != symbol.upper():
            continue
        if str(row.get("from_exchange") or "").lower() != buy_exchange.lower():
            continue
        if str(row.get("to_exchange") or "").lower() != sell_exchange.lower():
            continue
        return row
    return None


def analyze_snapshot(symbol: str, observed_at: str, rows: list[dict], routes: dict | None = None) -> dict | None:
    by_exchange = {}
    for row in rows:
        exchange = str(row.get("exchange") or "").lower()
        price = _f(row.get("price"))
        if exchange and price > 0:
            by_exchange[exchange] = row
    if len(by_exchange) < 2:
        return None

    buy = min(by_exchange.values(), key=lambda x: _f(x.get("price")))
    sell = max(by_exchange.values(), key=lambda x: _f(x.get("price")))
    buy_price = _f(buy.get("price"))
    sell_price = _f(sell.get("price"))
    if buy_price <= 0 or sell_price <= buy_price:
        return None

    gross_pct = (sell_price / buy_price - 1.0) * 100.0
    if gross_pct < MIN_GROSS_SPREAD_PCT_SHADOW:
        return None

    buy_exchange = str(buy.get("exchange") or "").lower()
    sell_exchange = str(sell.get("exchange") or "").lower()
    route = _route_lookup(routes or {}, symbol, buy_exchange, sell_exchange)
    route_verified = bool(
        route
        and route.get("withdraw_enabled") is True
        and route.get("deposit_enabled") is True
        and route.get("same_asset_identity_verified") is True
        and route.get("network")
    )

    blockers = []
    if not route_verified:
        blockers.append("TRANSFER_ROUTE_UNVERIFIED")
    # Current CEX state contains market snapshots, not executable bid/ask depth.
    # Never claim arbitrage execution from last-price proxies alone.
    blockers.append("EXECUTABLE_ORDERBOOK_QUOTES_MISSING")

    return {
        "symbol": symbol,
        "observed_at": observed_at,
        "buy_exchange": buy_exchange,
        "sell_exchange": sell_exchange,
        "buy_price_proxy": round(buy_price, 12),
        "sell_price_proxy": round(sell_price, 12),
        "gross_spread_pct_proxy": round(gross_pct, 4),
        "extreme_dislocation_shadow": gross_pct >= EXTREME_SPREAD_PCT_SHADOW,
        "buy_market_id": buy.get("market_id"),
        "sell_market_id": sell.get("market_id"),
        "route_verified": route_verified,
        "network": route.get("network") if route_verified else None,
        "transfer_feasibility": "ROUTE_VERIFIED_EXECUTION_UNVERIFIED" if route_verified else "UNVERIFIED",
        "blockers": blockers,
        "research_opportunity": True,
        "shadow_only": True,
        "affects_score": False,
        "actionable": False,
        "automatic_buy": False,
        "automatic_sell": False,
        "automatic_transfer": False,
        "manual_decision_only": True,
    }


def _latest_candidates(snapshots: dict[str, list[dict]], routes: dict) -> list[dict]:
    out = []
    for symbol, points in snapshots.items():
        if not points:
            continue
        latest = points[-1]
        row = analyze_snapshot(symbol, str(latest.get("observed_at") or ""), latest.get("rows") or [], routes)
        if row:
            out.append(row)
    return sorted(out, key=lambda x: _f(x.get("gross_spread_pct_proxy")), reverse=True)


def _update_forward_state(previous: dict, candidates: list[dict], now: str) -> dict:
    first = previous.get("first_transfer_dislocation") if isinstance(previous.get("first_transfer_dislocation"), dict) else {}
    first = {k: dict(v) if isinstance(v, dict) else {} for k, v in first.items()}
    added = 0
    for row in candidates:
        symbol = str(row.get("symbol") or "")
        if not symbol or symbol in first:
            continue
        first[symbol] = {
            "observed_at": row.get("observed_at") or now,
            "buy_exchange": row.get("buy_exchange"),
            "sell_exchange": row.get("sell_exchange"),
            "gross_spread_pct_proxy": row.get("gross_spread_pct_proxy"),
            "route_verified": row.get("route_verified"),
            "immutable": True,
        }
        added += 1
    return {
        "version": 1,
        "updated_at": now,
        "mode": "FORWARD_ONLY_CEX_TRANSFER_ARBITRAGE_SHADOW_STATE_V1",
        "research_only": True,
        "production_effect": False,
        "automatic_transfer": False,
        "new_events": added,
        "first_transfer_dislocation": first,
    }


def run(out: Path, now: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc).isoformat()
    state = _read_state(out / "cex-spot-state.json")
    routes = _read_json(out / "cex-transfer-routes.json", {})
    previous = _read_json(out / "cex-transfer-arbitrage-shadow-state.json", {})
    snapshots = build_snapshots(state)
    candidates = _latest_candidates(snapshots, routes)
    forward = _update_forward_state(previous, candidates, now)

    (out / "cex-transfer-arbitrage-shadow-state.json").write_text(json.dumps(forward, indent=2), encoding="utf-8")
    payload = {
        "version": 1,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_CEX_TRANSFER_ARBITRAGE_SHADOW_V1",
        "production_effect": False,
        "affects_score": False,
        "actionable": False,
        "automatic_buy": False,
        "automatic_sell": False,
        "automatic_transfer": False,
        "manual_decision_only": True,
        "production_thresholds_modified": False,
        "liquidity_minimum_modified": False,
        "identity_rules_modified": False,
        "truth_contract": {
            "last_price_is_proxy_not_executable_quote": True,
            "cross_exchange_transfer_requires_verified_same_asset_identity": True,
            "cross_exchange_transfer_requires_withdraw_and_deposit_enabled": True,
            "cross_exchange_transfer_requires_same_verified_network": True,
            "executable_orderbook_bid_ask_and_depth_required_before_actionable": True,
            "fees_slippage_transfer_time_and_withdrawal_cost_required_before_net_profit_claim": True,
            "missing_route_or_execution_data_fails_closed": True,
            "first_forward_dislocation_is_immutable": True,
            "no_hindsight": True,
        },
        "thresholds_shadow_only": {
            "minimum_gross_spread_pct_proxy": MIN_GROSS_SPREAD_PCT_SHADOW,
            "extreme_dislocation_pct_proxy": EXTREME_SPREAD_PCT_SHADOW,
        },
        "candidate_count": len(candidates),
        "extreme_count": sum(1 for x in candidates if x.get("extreme_dislocation_shadow")),
        "route_verified_count": sum(1 for x in candidates if x.get("route_verified")),
        "new_forward_events": forward.get("new_events", 0),
        "current_shadow_candidates": candidates[:100],
    }
    (out / "cex-transfer-arbitrage-shadow.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(Path("data")), indent=2))
