from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
DYNAMIC = ROOT / "data/unified-dynamic-candidates.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/derivatives-intelligence-state.json"
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
EVM = {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"}


def now():
    return datetime.now(timezone.utc).isoformat()


def get(url, timeout=9):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "Wallet500-Derivatives/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post(url, payload, timeout=9):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", "user-agent": "Wallet500-Derivatives/2.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def chain_name(v):
    raw = str(v or "").strip().lower()
    return ALIASES.get(raw, raw)


def norm(chain, v):
    raw = str(v or "").strip()
    return raw.lower() if chain in EVM else raw


def ident(t):
    c = chain_name(t.get("network") or t.get("chain"))
    a = norm(c, t.get("contract") or t.get("token_address"))
    p = norm(c, t.get("pair") or t.get("pair_address"))
    return (c, a, p, f"{c}:{a}:{p}") if c and a and p else None


def load(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def targets():
    cfg = load(CONFIG, {"tokens": []})
    dyn = load(DYNAMIC, {"candidates": []})
    out, seen = [], set()
    for t in list(cfg.get("tokens") or []) + list(dyn.get("candidates") or []):
        if not isinstance(t, dict):
            continue
        i = ident(t)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        out.append(t)
    return out[:50]


def pct(a, b):
    return ((a / b) - 1) * 100 if b else None


def ev(t, kind, direction, strength, confidence, source, subject, **extra):
    i = ident(t)
    if not i:
        return None
    x = {
        "symbol": str(t.get("symbol") or "").upper(),
        "network": i[0],
        "contract": i[1],
        "pair": i[2],
        "identity_key": i[3],
        "family": "derivatives",
        "kind": kind,
        "direction": direction,
        "strength": max(0, min(100, strength)),
        "confidence": max(0, min(100, confidence)),
        "source": source,
        "subject": subject,
        "canonical_event_id": f"{source}:{i[3]}:{kind}:{subject}",
        "event_time": now(),
        "observed_at": now(),
        "free_source": True,
        "identity_verified": True,
        "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR",
    }
    x.update(extra)
    return x


def binance_snapshot(symbol):
    s = symbol.upper() + "USDT"
    base = "https://fapi.binance.com"
    oi = float(get(base + "/fapi/v1/openInterest?" + urllib.parse.urlencode({"symbol": s}))["openInterest"])
    mark = get(base + "/fapi/v1/premiumIndex?" + urllib.parse.urlencode({"symbol": s}))
    px = float(mark["markPrice"])
    funding = float(mark.get("lastFundingRate") or 0) * 100
    return {"provider": "Binance Futures", "oi_units": oi, "oi_usd": oi * px, "mark_price": px, "funding_pct": funding}


def gate_snapshot(symbol):
    name = symbol.upper() + "_USDT"
    d = get("https://api.gateio.ws/api/v4/futures/usdt/contracts/" + urllib.parse.quote(name, safe=""))
    px = float(d.get("mark_price") or d.get("last_price") or 0)
    oi = float(d.get("open_interest") or 0)
    mult = float(d.get("quanto_multiplier") or 1)
    funding = float(d.get("funding_rate") or 0) * 100
    if px <= 0 or oi <= 0:
        raise RuntimeError("GATE_FUTURES_SNAPSHOT_MISSING")
    return {"provider": "Gate Futures", "oi_units": oi, "oi_usd": oi * px * mult, "mark_price": px, "funding_pct": funding, "quanto_multiplier": mult}


def derivative_snapshot(symbol):
    errors = []
    for fn in (binance_snapshot, gate_snapshot):
        try:
            return fn(symbol)
        except Exception as e:
            errors.append(type(e).__name__)
    return {"status": "UNAVAILABLE", "reason": "+".join(errors[-2:]) or "NO_PROVIDER"}


def hyper_user(address):
    perp = post("https://api.hyperliquid.xyz/info", {"type": "clearinghouseState", "user": address})
    spot = post("https://api.hyperliquid.xyz/info", {"type": "spotClearinghouseState", "user": address})
    positions = []
    for row in perp.get("assetPositions") or []:
        p = row.get("position") or {}
        sz = float(p.get("szi") or 0)
        if sz:
            positions.append({
                "coin": p.get("coin"),
                "signed_size": sz,
                "side": "LONG" if sz > 0 else "SHORT",
                "entry_px": p.get("entryPx"),
                "position_value": p.get("positionValue"),
                "liquidation_px": p.get("liquidationPx"),
                "unrealized_pnl": p.get("unrealizedPnl"),
            })
    balances = {str(x.get("coin")): float(x.get("total") or 0) for x in (spot.get("balances") or [])}
    return {"positions": positions, "spot_balances": balances}


def main():
    doc = load(EVENTS, {"version": 3, "events": []})
    state = load(STATE, {"version": 2, "tokens": {}})
    state["version"] = 2
    old_tokens = state.setdefault("tokens", {})
    out = []
    provider_ok = {"Binance Futures": 0, "Gate Futures": 0}
    unavailable = 0
    rows = targets()

    for t in rows:
        sym = str(t.get("symbol") or "").upper()
        i = ident(t)
        if not sym or not i:
            continue
        prev = old_tokens.get(i[3]) or {}
        snap = derivative_snapshot(sym)
        if snap.get("oi_usd"):
            provider_ok[snap["provider"]] = provider_ok.get(snap["provider"], 0) + 1
            old = float(prev.get("oi_usd") or 0)
            d = pct(snap["oi_usd"], old)
            if d is not None and abs(d) >= 5:
                out.append(ev(
                    t,
                    "open_interest_change",
                    1 if d > 0 else -1,
                    min(100, abs(d) * 3),
                    85,
                    snap["provider"],
                    f"OI {d:+.2f}% vs prior verified snapshot",
                    oi_usd=snap["oi_usd"],
                    delta_pct=round(d, 3),
                    funding_pct=snap["funding_pct"],
                ))
            if abs(snap["funding_pct"]) >= 0.05:
                out.append(ev(
                    t,
                    "funding_extreme",
                    -1,
                    min(100, abs(snap["funding_pct"]) * 1000),
                    80,
                    snap["provider"],
                    f"funding {snap['funding_pct']:+.4f}%",
                    funding_pct=snap["funding_pct"],
                    contradicts_bullish=snap["funding_pct"] > 0,
                ))
            old_tokens[i[3]] = {**snap, "symbol": sym, "identity_key": i[3], "observed_at": now()}
        else:
            unavailable += 1
            old_tokens.setdefault(i[3], {"symbol": sym, "identity_key": i[3]})["last_unavailable"] = {**snap, "observed_at": now()}

        for w in t.get("tracked_perp_wallets") or []:
            address = str(w.get("address") if isinstance(w, dict) else w)
            provider = str(w.get("provider", "hyperliquid") if isinstance(w, dict) else "hyperliquid").lower()
            if provider != "hyperliquid" or not address:
                continue
            try:
                u = hyper_user(address)
            except Exception:
                continue
            pos = next((p for p in u["positions"] if str(p.get("coin", "")).upper() == sym), None)
            spot = float(u["spot_balances"].get(sym, 0))
            if not pos:
                continue
            pv = abs(float(pos.get("position_value") or 0))
            side = pos["side"]
            spx = float(snap.get("mark_price") or 0)
            spot_usd = spot * spx if spx else None
            hedge_ratio = (pv / spot_usd) if spot_usd and spot_usd > 0 and side == "SHORT" else None
            direction = 1 if side == "LONG" else -1
            strength = min(100, 35 + (min(2.0, hedge_ratio or 0) * 25))
            out.append(ev(
                t,
                "verified_same_wallet_perp_exposure",
                direction,
                strength,
                92,
                "Hyperliquid public account state",
                address,
                wallet_address=address,
                side=side,
                perp_notional_usd=pv,
                spot_units=spot,
                spot_usd=spot_usd,
                hedge_ratio=hedge_ratio,
                entry_px=pos.get("entry_px"),
                liquidation_px=pos.get("liquidation_px"),
            ))
            if side == "SHORT" and spot > 0:
                out.append(ev(
                    t,
                    "spot_holder_short_hedge",
                    -1,
                    min(100, 45 + (min(2.0, hedge_ratio or 0) * 20)),
                    90,
                    "Hyperliquid public account state",
                    address,
                    contradicts_bullish=True,
                    wallet_address=address,
                    hedge_ratio=hedge_ratio,
                    interpretation="HEDGE_OR_DISTRIBUTION_RISK_NOT_MANIPULATION_PROOF",
                ))

    merged = [e for e in (doc.get("events") or []) if isinstance(e, dict)] + [e for e in out if e]
    ded = {}
    for e in merged:
        ded[(e.get("identity_key") or "", e.get("canonical_event_id"), e.get("kind"))] = e
    doc = {"version": 3, "generated_at": now(), "events": list(ded.values())[-5000:]}
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    state["updated_at"] = now()
    state["provider_success"] = provider_ok
    state["unavailable_targets"] = unavailable
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "OK", "new_events": len([x for x in out if x]), "targets": len(rows), "provider_success": provider_ok, "unavailable": unavailable}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
