from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "data/cex-sensor-handoff.json"
IDENTITY = ROOT / "data/cex-spot-identity-radar.json"
REGISTRY = ROOT / "data/native-asset-identity-registry.json"
OUT = ROOT / "data/native-asset-close-watch.json"
GATE = "https://api.gateio.ws/api/v4"
UA = "Wallet500-NativeAssetExecution/1.0"

MIN_SIDE_DEPTH_USD = 15_000.0
MAX_SPREAD_PCT = 1.0
PREBUY_RESEARCH_SCORE = 70.0


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v, default=999) -> int:
    try:
        n = int(float(v))
        return n if n > 0 else default
    except (TypeError, ValueError):
        return default


def _get_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _registry_assets(doc: dict | None = None) -> dict[tuple[str, str], dict]:
    doc = doc if isinstance(doc, dict) else _load(REGISTRY, {})
    out = {}
    for cgid, row in (doc.get("assets") or {}).items():
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        chain = str(row.get("chain") or "").lower().strip()
        wrapper = str(row.get("token_address") or "").strip()
        if (
            symbol
            and chain
            and wrapper
            and str(row.get("representation_type") or "") == "CANONICAL_WRAPPED_NATIVE"
        ):
            out[(str(cgid), symbol)] = {
                "coingecko_id": str(cgid),
                "symbol": symbol,
                "network": chain,
                "canonical_wrapper_contract": wrapper,
                "evidence_source": row.get("evidence_source"),
                "evidence_url": row.get("evidence_url"),
            }
    return out


def _identity_rows(doc: dict | None = None) -> dict[tuple[str, str], dict]:
    doc = doc if isinstance(doc, dict) else _load(IDENTITY, {})
    out = {}
    for row in doc.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        cgid = str(row.get("coingecko_id") or "").strip()
        symbol = str(row.get("base_symbol") or row.get("symbol") or "").upper().replace("USDT", "")
        if cgid and symbol:
            out[(cgid, symbol)] = row
    return out


def _cex_reference_price(row: dict, symbol: str) -> float:
    for field in ("cex_reference_price_usd", "current_price_usd", "reference_price"):
        value = _f(row.get(field))
        if value > 0:
            return value
    for market in row.get("markets") or []:
        if not isinstance(market, dict):
            continue
        market_symbol = str(market.get("symbol") or market.get("market_id") or "").upper().replace("-", "").replace("_", "")
        if market_symbol != f"{symbol}USDT":
            continue
        value = _f(market.get("price"))
        if value > 0:
            return value
    return 0.0


def _gate_pair(row: dict, symbol: str) -> str:
    for market in row.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if str(market.get("exchange") or "").lower() != "gate":
            continue
        market_id = str(market.get("market_id") or "").upper().strip()
        if market_id:
            return market_id
        market_symbol = str(market.get("symbol") or "").upper().replace("-", "").replace("_", "")
        if market_symbol == f"{symbol}USDT":
            return f"{symbol}_USDT"
    return f"{symbol}_USDT"


def _orderbook_execution(currency_pair: str, ref_price: float) -> dict:
    q = urllib.parse.urlencode({"currency_pair": currency_pair, "limit": 100, "with_id": "true"})
    doc = _get_json(f"{GATE}/spot/order_book?{q}")
    if not isinstance(doc, dict):
        return {
            "status": "UNAVAILABLE",
            "execution_verified": False,
            "blocker": "GATE_ORDERBOOK_UNAVAILABLE",
        }
    bids = doc.get("bids") or []
    asks = doc.get("asks") or []
    if not bids or not asks:
        return {
            "status": "UNAVAILABLE",
            "execution_verified": False,
            "blocker": "GATE_ORDERBOOK_EMPTY",
        }
    try:
        best_bid = max(float(x[0]) for x in bids if len(x) >= 2 and float(x[0]) > 0)
        best_ask = min(float(x[0]) for x in asks if len(x) >= 2 and float(x[0]) > 0)
    except Exception:
        return {
            "status": "INVALID",
            "execution_verified": False,
            "blocker": "GATE_ORDERBOOK_SCHEMA",
        }
    mid = (best_bid + best_ask) / 2.0
    spread_pct = (best_ask / best_bid - 1.0) * 100.0 if best_bid > 0 else 999.0
    reference = ref_price if ref_price > 0 else mid
    bid_floor = reference * 0.98
    ask_ceiling = reference * 1.02
    bid_depth = 0.0
    ask_depth = 0.0
    for row in bids:
        try:
            px, units = float(row[0]), float(row[1])
        except Exception:
            continue
        if px >= bid_floor:
            bid_depth += px * units
    for row in asks:
        try:
            px, units = float(row[0]), float(row[1])
        except Exception:
            continue
        if px <= ask_ceiling:
            ask_depth += px * units
    min_depth = min(bid_depth, ask_depth)
    price_error_pct = abs(mid / reference - 1.0) * 100.0 if reference > 0 else 999.0
    verified = bool(
        spread_pct <= MAX_SPREAD_PCT
        and min_depth >= MIN_SIDE_DEPTH_USD
        and price_error_pct <= 2.0
    )
    blockers = []
    if spread_pct > MAX_SPREAD_PCT:
        blockers.append("CEX_SPREAD_TOO_WIDE")
    if min_depth < MIN_SIDE_DEPTH_USD:
        blockers.append("CEX_DEPTH_BELOW_15K_PER_SIDE")
    if price_error_pct > 2.0:
        blockers.append("CEX_ORDERBOOK_PRICE_INCOHERENT")
    return {
        "status": "VERIFIED" if verified else "CAUTION",
        "execution_verified": verified,
        "currency_pair": currency_pair,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid,
        "reference_price": reference,
        "price_error_pct": round(price_error_pct, 4),
        "spread_pct": round(spread_pct, 4),
        "bid_depth_2pct_usd": round(bid_depth, 2),
        "ask_depth_2pct_usd": round(ask_depth, 2),
        "minimum_side_depth_2pct_usd": round(min_depth, 2),
        "blockers": blockers,
    }


def _score(handoff_row: dict, identity_row: dict, execution: dict) -> tuple[float, list[str]]:
    sensor = handoff_row.get("cex_sensor") or {}
    rank = _i(sensor.get("current_rank"))
    multiple = _f(sensor.get("baseline_multiple"))
    change = _f(identity_row.get("current_change_24h_max_pct") or identity_row.get("change_24h_max_pct"))
    coherent = _i(identity_row.get("current_coherent_confirmations") or identity_row.get("coherent_confirmations"), 0)
    score = 0.0
    reasons = []
    if rank <= 3:
        score += 20
        reasons.append("TOP3_CEX_RANK")
    elif rank <= 10:
        score += 12
        reasons.append("TOP10_CEX_RANK")
    if coherent >= 4:
        score += 18
        reasons.append("FOUR_PLUS_COHERENT_CEX")
    elif coherent >= 2:
        score += 10
        reasons.append("MULTI_CEX_COHERENCE")
    if change >= 50:
        score += 18
        reasons.append("CEX_MOMENTUM_50PCT_PLUS")
    elif change >= 20:
        score += 12
        reasons.append("CEX_MOMENTUM_20PCT_PLUS")
    if multiple >= 4:
        score += 18
        reasons.append("RELATIVE_VOLUME_4X_PLUS")
    elif multiple >= 2:
        score += 12
        reasons.append("RELATIVE_VOLUME_2X_PLUS")
    elif multiple >= 1.3:
        score += 6
        reasons.append("RELATIVE_VOLUME_ACCELERATION")
    milestones = identity_row.get("milestones") or {}
    if isinstance(milestones.get("first_watch"), dict):
        score += 6
        reasons.append("IMMUTABLE_FIRST_WATCH")
    if isinstance(milestones.get("first_alert"), dict):
        score += 6
        reasons.append("IMMUTABLE_FIRST_ALERT")
    if execution.get("execution_verified") is True:
        score += 14
        reasons.append("CEX_EXECUTION_DEPTH_VERIFIED")
    return min(100.0, round(score, 2)), reasons


def build(handoff: dict, identity: dict, registry: dict) -> dict:
    assets = _registry_assets(registry)
    identities = _identity_rows(identity)
    rows = []
    for h in handoff.get("rows") or []:
        if not isinstance(h, dict):
            continue
        symbol = str(h.get("symbol") or "").upper().strip()
        cgid = str(h.get("coingecko_id") or "").strip()
        asset = assets.get((cgid, symbol))
        if not asset:
            continue
        sensor = h.get("cex_sensor") or {}
        if sensor.get("cex_led") is not True:
            continue
        ident = identities.get((cgid, symbol), {})
        reference = _f(h.get("cex_reference_price_usd")) or _cex_reference_price(ident, symbol)
        pair = _gate_pair(ident, symbol)
        execution = _orderbook_execution(pair, reference)
        score, reasons = _score(h, ident, execution)
        stage = (
            "CEX_NATIVE_PREBUY_RESEARCH"
            if execution.get("execution_verified") is True and score >= PREBUY_RESEARCH_SCORE
            else "CEX_NATIVE_ASSET_CLOSE_WATCH"
        )
        rows.append({
            **asset,
            "asset_identity_verified": True,
            "asset_identity_scope": "CURATED_NATIVE_ASSET_PLUS_CANONICAL_WRAPPER",
            "execution_identity_type": "CEX_SPOT_ORDERBOOK",
            "execution_identity_verified": execution.get("execution_verified") is True,
            "execution": execution,
            "symbol": symbol,
            "coingecko_id": cgid,
            "stage": stage,
            "score": score,
            "reasons": reasons,
            "cex_sensor": sensor,
            "cex_reference_price_usd": reference,
            "coherent_confirmations": _i(ident.get("current_coherent_confirmations") or ident.get("coherent_confirmations"), 0),
            "current_change_24h_pct": _f(ident.get("current_change_24h_max_pct") or ident.get("change_24h_max_pct")),
            "milestones": ident.get("milestones") or {},
            "buy_eligible": False,
            "actionable": False,
            "research_only": True,
            "telegram_delivery_enabled": False,
            "production_buy_blocker": "CEX_NATIVE_PREBUY_REQUIRES_FORWARD_VALIDATION_AND_DECISION_ENGINE_SUPPORT",
        })
    rows.sort(key=lambda x: (-_f(x.get("score")), _i((x.get("cex_sensor") or {}).get("current_rank"))))
    return {
        "version": 1,
        "generated_at": now(),
        "mode": "ASSET_IDENTITY_SEPARATE_FROM_EXECUTION_IDENTITY",
        "truth_contract": {
            "curated_native_asset_identity_can_enter_close_watch_without_dex_pair": True,
            "asset_identity_never_satisfies_buy_execution_identity": True,
            "cex_orderbook_can_verify_execution_research_only": True,
            "minimum_side_depth_2pct_usd": MIN_SIDE_DEPTH_USD,
            "maximum_spread_pct": MAX_SPREAD_PCT,
            "automatic_buy": False,
            "telegram_delivery_enabled": False,
            "final_buy_pipeline_unchanged": True,
        },
        "count": len(rows),
        "prebuy_research_count": sum(x.get("stage") == "CEX_NATIVE_PREBUY_RESEARCH" for x in rows),
        "close_watch_count": sum(x.get("stage") == "CEX_NATIVE_ASSET_CLOSE_WATCH" for x in rows),
        "candidates": rows,
    }


def main() -> int:
    doc = build(_load(HANDOFF, {}), _load(IDENTITY, {}), _load(REGISTRY, {}))
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "count": doc["count"],
        "prebuy_research_count": doc["prebuy_research_count"],
        "close_watch_count": doc["close_watch_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
