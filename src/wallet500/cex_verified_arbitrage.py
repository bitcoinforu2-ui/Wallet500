from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TARGET_QUOTE_USD = 1000.0
MIN_NET_PROFIT_PCT = 1.0
SUPPORTED = {"okx", "kucoin", "mexc", "gate"}


def _f(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _json_get(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500-Arbitrage/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _symbol(exchange: str, market_id: str) -> str:
    if exchange in {"okx", "kucoin"}:
        return market_id
    if exchange == "gate":
        return market_id.replace("-", "_")
    return market_id.replace("-", "").replace("_", "")


def fetch_book(exchange: str, market_id: str) -> dict:
    exchange = exchange.lower()
    if exchange not in SUPPORTED:
        raise ValueError("UNSUPPORTED_EXCHANGE")
    m = urllib.parse.quote(_symbol(exchange, market_id), safe="-_")
    if exchange == "okx":
        p = _json_get(f"https://www.okx.com/api/v5/market/books?instId={m}&sz=50")
        d = (p.get("data") or [{}])[0]
        return {"bids": d.get("bids") or [], "asks": d.get("asks") or [], "ts": d.get("ts")}
    if exchange == "kucoin":
        d = (_json_get(f"https://api.kucoin.com/api/v1/market/orderbook/level2_20?symbol={m}").get("data") or {})
        return {"bids": d.get("bids") or [], "asks": d.get("asks") or [], "ts": d.get("time")}
    if exchange == "mexc":
        d = _json_get(f"https://api.mexc.com/api/v3/depth?symbol={m}&limit=50")
        return {"bids": d.get("bids") or [], "asks": d.get("asks") or [], "ts": d.get("lastUpdateId")}
    d = _json_get(f"https://api.gateio.ws/api/v4/spot/order_book?currency_pair={m}&limit=50")
    return {"bids": d.get("bids") or [], "asks": d.get("asks") or [], "ts": d.get("update") or d.get("current")}


def vwap(levels: list, quote_usd: float) -> dict:
    remain = quote_usd
    base = 0.0
    spent = 0.0
    for row in levels:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        px, qty = _f(row[0]), _f(row[1])
        if px <= 0 or qty <= 0:
            continue
        cap = px * qty
        take_quote = min(remain, cap)
        base += take_quote / px
        spent += take_quote
        remain -= take_quote
        if remain <= 1e-9:
            break
    return {"complete": remain <= 1e-9, "quote_usd": round(spent, 8), "base_qty": round(base, 12), "vwap": round(spent / base, 12) if base > 0 else None, "unfilled_quote_usd": round(max(0.0, remain), 8)}


def _sell_vwap(levels: list, base_qty: float) -> dict:
    remain = base_qty
    proceeds = 0.0
    sold = 0.0
    for row in levels:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        px, qty = _f(row[0]), _f(row[1])
        if px <= 0 or qty <= 0:
            continue
        take = min(remain, qty)
        proceeds += take * px
        sold += take
        remain -= take
        if remain <= 1e-12:
            break
    return {"complete": remain <= 1e-12, "base_qty": round(sold, 12), "quote_usd": round(proceeds, 8), "vwap": round(proceeds / sold, 12) if sold > 0 else None, "unfilled_base_qty": round(max(0.0, remain), 12)}


def verify_candidate(candidate: dict, route: dict | None, target_quote_usd: float = TARGET_QUOTE_USD, books: dict | None = None) -> dict:
    buy_ex = str(candidate.get("buy_exchange") or "").lower()
    sell_ex = str(candidate.get("sell_exchange") or "").lower()
    buy_mid = str(candidate.get("buy_market_id") or "")
    sell_mid = str(candidate.get("sell_market_id") or "")
    blockers = []
    route_ok = bool(route and route.get("withdraw_enabled") is True and route.get("deposit_enabled") is True and route.get("same_asset_identity_verified") is True and route.get("network"))
    if not route_ok:
        blockers.append("TRANSFER_ROUTE_UNVERIFIED")
    try:
        bbook = (books or {}).get("buy") or fetch_book(buy_ex, buy_mid)
        sbook = (books or {}).get("sell") or fetch_book(sell_ex, sell_mid)
    except Exception as e:
        return {**candidate, "stage": "EXECUTION_UNVERIFIED", "verified_arbitrage": False, "blockers": blockers + [f"ORDERBOOK_FETCH_FAILED:{type(e).__name__}"], "automatic_trade": False}
    buy = vwap(bbook.get("asks") or [], target_quote_usd)
    if not buy["complete"]:
        blockers.append("BUY_DEPTH_INSUFFICIENT")
    sell = _sell_vwap(sbook.get("bids") or [], _f(buy.get("base_qty")))
    if not sell["complete"]:
        blockers.append("SELL_DEPTH_INSUFFICIENT")
    trading_fee_pct = _f((route or {}).get("trading_fee_pct"))
    withdrawal_fee_usd = _f((route or {}).get("withdrawal_fee_usd"))
    transfer_cost_usd = _f((route or {}).get("transfer_cost_usd"))
    gross = _f(sell.get("quote_usd")) - _f(buy.get("quote_usd"))
    fee_usd = (_f(buy.get("quote_usd")) + _f(sell.get("quote_usd"))) * trading_fee_pct / 100.0
    net = gross - fee_usd - withdrawal_fee_usd - transfer_cost_usd
    net_pct = (net / _f(buy.get("quote_usd")) * 100.0) if _f(buy.get("quote_usd")) > 0 else -100.0
    if route_ok and not (route or {}).get("fees_verified"):
        blockers.append("FEES_UNVERIFIED")
    if route_ok and not (route or {}).get("transfer_time_verified"):
        blockers.append("TRANSFER_TIME_UNVERIFIED")
    if net_pct < MIN_NET_PROFIT_PCT:
        blockers.append("NET_PROFIT_BELOW_THRESHOLD")
    verified = not blockers
    stage = "VERIFIED_ARBITRAGE" if verified else ("ROUTE_BLOCKED" if "TRANSFER_ROUTE_UNVERIFIED" in blockers else "EXECUTION_UNVERIFIED")
    return {**candidate, "stage": stage, "verified_arbitrage": verified, "target_quote_usd": target_quote_usd, "buy_execution": buy, "sell_execution": sell, "route_verified": route_ok, "network": (route or {}).get("network") if route_ok else None, "gross_profit_usd": round(gross, 8), "net_profit_usd": round(net, 8), "net_profit_pct": round(net_pct, 4), "blockers": blockers, "automatic_trade": False, "manual_decision_only": True}


def run(data_dir: Path = Path("data")) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    shadow_path = data_dir / "cex-transfer-arbitrage-shadow.json"
    routes_path = data_dir / "cex-transfer-routes.json"
    shadow = json.loads(shadow_path.read_text()) if shadow_path.exists() else {}
    routes_doc = json.loads(routes_path.read_text()) if routes_path.exists() else {"routes": []}
    route_rows = routes_doc.get("routes") if isinstance(routes_doc.get("routes"), list) else []
    results = []
    for c in (shadow.get("current_shadow_candidates") or [])[:25]:
        route = next((r for r in route_rows if str(r.get("symbol") or "").upper() == str(c.get("symbol") or "").upper() and str(r.get("from_exchange") or "").lower() == str(c.get("buy_exchange") or "").lower() and str(r.get("to_exchange") or "").lower() == str(c.get("sell_exchange") or "").lower()), None)
        results.append(verify_candidate(c, route))
    payload = {"version": 1, "generated_at": now, "mode": "RESEARCH_ONLY_VERIFIED_CEX_ARBITRAGE_V1", "production_effect": False, "automatic_buy": False, "automatic_sell": False, "automatic_transfer": False, "manual_decision_only": True, "target_quote_usd": TARGET_QUOTE_USD, "minimum_net_profit_pct": MIN_NET_PROFIT_PCT, "candidate_count": len(results), "verified_count": sum(1 for r in results if r.get("verified_arbitrage")), "results": results, "truth_contract": {"last_price_never_sufficient": True, "buy_ask_depth_required": True, "sell_bid_depth_required": True, "same_asset_and_network_required": True, "withdraw_and_deposit_open_required": True, "fees_and_transfer_time_required": True, "missing_data_fails_closed": True, "no_automatic_trade": True}}
    (data_dir / "cex-verified-arbitrage.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
