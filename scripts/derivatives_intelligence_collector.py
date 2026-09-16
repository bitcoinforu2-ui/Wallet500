from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
REAL_ALERTS = ROOT / "data/real-alerts.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/derivatives-intelligence-state.json"

EVM_NETWORKS = {
    "ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "linea", "zksync", "mantle",
    "scroll", "blast",
}
NETWORK_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def network(value: object) -> str:
    raw = str(value or "").strip().lower()
    return NETWORK_ALIASES.get(raw, raw)


def addr(value: object, chain: str) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM_NETWORKS else raw


def identity_key(t: dict) -> str:
    chain = network(t.get("network") or t.get("chain"))
    contract = addr(t.get("contract") or t.get("token_address") or t.get("token") or t.get("mint"), chain)
    pair = addr(t.get("pair") or t.get("pair_address"), chain)
    return f"{chain}|{contract}|{pair}" if chain and contract and pair else ""


def get(url):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "Wallet500-Derivatives/2.0"})
    return json.load(urllib.request.urlopen(req, timeout=15))


def post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", "user-agent": "Wallet500-Derivatives/2.0"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=15))


def pct(a, b):
    return ((a / b) - 1) * 100 if b else None


def ev(t, kind, direction, strength, confidence, source, subject, **extra):
    chain = network(t["network"])
    contract = addr(t["contract"], chain)
    pair = addr(t["pair"], chain)
    production_independent = t.get("derivatives_identity_verified") is True
    payload = {
        "symbol": t["symbol"],
        "network": chain,
        "contract": contract,
        "pair": pair,
        "family": "derivatives",
        "kind": kind,
        "direction": direction,
        "strength": max(0, min(100, strength)),
        "confidence": max(0, min(100, confidence)),
        "source": source,
        "subject": subject,
        "canonical_event_id": f"{source}:{chain}:{contract}:{pair}:{kind}:{subject}",
        "event_time": now(),
        "observed_at": now(),
        "free_source": True,
        "exact_identity_bound": True,
        # Futures venues identify an asset by market symbol, not ERC20/SPL contract.
        # They may enrich the score, but cannot count as an independent production
        # family unless an explicit contract-to-derivative mapping was verified.
        "production_independent": production_independent,
        "identity_scope": "EXACT_CONTRACT_MAPPING" if production_independent else "DERIVATIVE_SYMBOL_ALIAS",
    }
    payload.update(extra)
    return payload


def _canonical_targets() -> list[dict]:
    if not REAL_ALERTS.exists():
        return []
    try:
        payload = json.loads(REAL_ALERTS.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for name in ("alerts", "pre_wave_alerts"):
        for row in payload.get(name) or []:
            if not isinstance(row, dict):
                continue
            if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
                continue
            chain = network(row.get("chain") or row.get("network"))
            contract = addr(row.get("token_address") or row.get("token") or row.get("mint"), chain)
            pair = addr(row.get("pair_address"), chain)
            symbol = str(row.get("symbol") or row.get("name") or "").strip().upper()
            if chain and contract and pair and symbol:
                out.append({"symbol": symbol, "network": chain, "contract": contract, "pair": pair, "production_dynamic_target": True, "derivatives_intelligence": True})
    return out


def targets(cfg: dict) -> list[dict]:
    merged = {}
    for raw in list(cfg.get("tokens") or []) + _canonical_targets():
        if not isinstance(raw, dict):
            continue
        t = dict(raw)
        t["network"] = network(t.get("network") or t.get("chain"))
        t["contract"] = addr(t.get("contract") or t.get("token_address") or t.get("token") or t.get("mint"), t["network"])
        t["pair"] = addr(t.get("pair") or t.get("pair_address"), t["network"])
        t["symbol"] = str(t.get("symbol") or t.get("name") or "").strip().upper()
        key = identity_key(t)
        if not key or not t["symbol"]:
            continue
        if key in merged:
            existing = merged[key]
            if existing.get("production_dynamic_target") is True and t.get("production_dynamic_target") is not True:
                merged[key] = {**existing, **t}
            else:
                merged[key] = {**t, **existing}
        else:
            merged[key] = t
    return list(merged.values())


def binance_snapshot(symbol):
    market = symbol.upper() + "USDT"
    base = "https://fapi.binance.com"
    oi = float(get(base + "/fapi/v1/openInterest?" + urllib.parse.urlencode({"symbol": market}))["openInterest"])
    mark = get(base + "/fapi/v1/premiumIndex?" + urllib.parse.urlencode({"symbol": market}))
    price = float(mark["markPrice"])
    funding = float(mark.get("lastFundingRate") or 0) * 100
    return {"oi_units": oi, "oi_usd": oi * price, "mark_price": price, "funding_pct": funding}


def hyper_user(address):
    perp = post("https://api.hyperliquid.xyz/info", {"type": "clearinghouseState", "user": address})
    spot = post("https://api.hyperliquid.xyz/info", {"type": "spotClearinghouseState", "user": address})
    positions = []
    for row in perp.get("assetPositions") or []:
        position = row.get("position") or {}
        size = float(position.get("szi") or 0)
        if size:
            positions.append({"coin": position.get("coin"), "signed_size": size, "side": "LONG" if size > 0 else "SHORT", "entry_px": position.get("entryPx"), "position_value": position.get("positionValue"), "liquidation_px": position.get("liquidationPx"), "unrealized_pnl": position.get("unrealizedPnl")})
    balances = {str(row.get("coin")): float(row.get("total") or 0) for row in (spot.get("balances") or [])}
    return {"positions": positions, "spot_balances": balances}


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    all_targets = targets(cfg)
    doc = json.loads(EVENTS.read_text(encoding="utf-8")) if EVENTS.exists() else {"version": 3, "events": []}
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"version": 2, "tokens": {}}
    state.setdefault("tokens", {})
    out = []

    for t in all_targets:
        if t.get("derivatives_intelligence") is False:
            continue
        key = identity_key(t)
        symbol = t["symbol"]
        previous = state["tokens"].get(key) or {}
        try:
            snap = binance_snapshot(symbol)
        except Exception as exc:
            snap = {"status": "UNAVAILABLE", "reason": type(exc).__name__}

        if snap.get("oi_usd"):
            old = float(previous.get("oi_usd") or 0)
            change = pct(snap["oi_usd"], old)
            if change is not None and abs(change) >= 5:
                out.append(ev(t, "open_interest_change", 1 if change > 0 else -1, min(100, abs(change) * 3), 85, "Binance Futures", f"OI {change:+.2f}% vs prior verified snapshot", oi_usd=snap["oi_usd"], delta_pct=round(change, 3), funding_pct=snap["funding_pct"]))
            if abs(snap["funding_pct"]) >= 0.05:
                out.append(ev(t, "funding_extreme", -1, min(100, abs(snap["funding_pct"]) * 1000), 80, "Binance Futures", f"funding {snap['funding_pct']:+.4f}%", contradicts_bullish=snap["funding_pct"] > 0))
            state["tokens"][key] = {**snap, "symbol": symbol, "network": t["network"], "contract": t["contract"], "pair": t["pair"], "observed_at": now()}

        for wallet in t.get("tracked_perp_wallets") or []:
            address = str(wallet.get("address") if isinstance(wallet, dict) else wallet)
            provider = str(wallet.get("provider", "hyperliquid") if isinstance(wallet, dict) else "hyperliquid").lower()
            if provider != "hyperliquid" or not address:
                continue
            try:
                user = hyper_user(address)
            except Exception:
                continue
            position = next((p for p in user["positions"] if str(p.get("coin", "")).upper() == symbol), None)
            spot_units = float(user["spot_balances"].get(symbol, 0))
            if not position:
                continue
            position_value = abs(float(position.get("position_value") or 0))
            side = position["side"]
            mark_price = float(snap.get("mark_price") or 0) if isinstance(snap, dict) else 0
            spot_usd = spot_units * mark_price if mark_price else None
            hedge_ratio = (position_value / spot_usd) if spot_usd and spot_usd > 0 and side == "SHORT" else None
            direction = 1 if side == "LONG" else -1
            strength = min(100, 35 + (min(2.0, hedge_ratio or 0) * 25))
            out.append(ev(t, "verified_same_wallet_perp_exposure", direction, strength, 92, "Hyperliquid public account state", address, wallet_address=address, side=side, perp_notional_usd=position_value, spot_units=spot_units, spot_usd=spot_usd, hedge_ratio=hedge_ratio, entry_px=position.get("entry_px"), liquidation_px=position.get("liquidation_px")))
            if side == "SHORT" and spot_units > 0:
                out.append(ev(t, "spot_holder_short_hedge", -1, min(100, 45 + (min(2.0, hedge_ratio or 0) * 20)), 90, "Hyperliquid public account state", address, contradicts_bullish=True, wallet_address=address, hedge_ratio=hedge_ratio, interpretation="HEDGE_OR_DISTRIBUTION_RISK_NOT_MANIPULATION_PROOF"))

    merged = [row for row in (doc.get("events") or []) if isinstance(row, dict)] + out
    doc = {"version": 3, "generated_at": now(), "events": merged[-5000:]}
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state["version"] = 2
    state["updated_at"] = now()
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "new_events": len(out), "tokens": len(all_targets), "dynamic_production_targets": sum(1 for t in all_targets if t.get("production_dynamic_target")), "exact_identity_bound": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
