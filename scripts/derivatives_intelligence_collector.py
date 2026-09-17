from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import resilient_http

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
DYNAMIC = ROOT / "data/unified-dynamic-candidates.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/derivatives-intelligence-state.json"
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
EVM = {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"}


def now():
    return datetime.now(timezone.utc).isoformat()


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
        ctype = str(t.get("candidate_type") or "CONFIGURED").upper()
        if ctype == "PUBLIC_ALPHA" and not (t.get("derivatives_intelligence") or t.get("derivatives_symbol")):
            continue
        if ctype == "CONFIGURED" and not t.get("derivatives_intelligence", False):
            continue
        seen.add(i[3])
        out.append(t)
    return out[:60]


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


def jget(url, cache_ttl=45):
    return resilient_http.request_json(
        url,
        timeout=15,
        attempts=5,
        cache_ttl=cache_ttl,
        user_agent="Wallet500-Derivatives/3.0",
    )


def gate_catalog():
    rows = jget("https://api.gateio.ws/api/v4/futures/usdt/contracts", 60)
    out = {}
    for d in rows if isinstance(rows, list) else []:
        name = str(d.get("name") or "").upper()
        if not name.endswith("_USDT"):
            continue
        sym = name[:-5]
        try:
            px = float(d.get("mark_price") or d.get("last_price") or 0)
            oi = float(d.get("open_interest") or 0)
            mult = float(d.get("quanto_multiplier") or 1)
            oi_usd = oi * px * mult
            funding = float(d.get("funding_rate") or 0) * 100
        except Exception:
            continue
        if px > 0 and oi_usd > 0:
            out[sym] = {"provider": "Gate Futures", "oi_usd": oi_usd, "mark_price": px, "funding_pct": funding}
    return out


def bybit_catalog():
    doc = jget("https://api.bybit.com/v5/market/tickers?category=linear", 60)
    if str(doc.get("retCode", "0")) not in {"0", "None"}:
        raise RuntimeError(f"BYBIT_RETCODE_{doc.get('retCode')}")
    out = {}
    for d in ((doc.get("result") or {}).get("list") or []):
        name = str(d.get("symbol") or "").upper()
        if not name.endswith("USDT"):
            continue
        sym = name[:-4]
        try:
            px = float(d.get("markPrice") or d.get("lastPrice") or 0)
            oi_usd = float(d.get("openInterestValue") or 0)
            funding = float(d.get("fundingRate") or 0) * 100
        except Exception:
            continue
        if px > 0 and oi_usd > 0:
            out[sym] = {"provider": "Bybit Perpetuals", "oi_usd": oi_usd, "mark_price": px, "funding_pct": funding}
    return out


def binance_catalog(configured_symbols):
    marks = jget("https://fapi.binance.com/fapi/v1/premiumIndex", 60)
    marks = marks if isinstance(marks, list) else [marks]
    mark_map = {str(x.get("symbol") or "").upper(): x for x in marks if isinstance(x, dict)}
    out = {}
    for sym in configured_symbols:
        pair = sym.upper() + "USDT"
        m = mark_map.get(pair)
        if not m:
            continue
        try:
            oi = jget("https://fapi.binance.com/fapi/v1/openInterest?" + urllib.parse.urlencode({"symbol": pair}), 20)
            px = float(m.get("markPrice") or 0)
            units = float(oi.get("openInterest") or 0)
            funding = float(m.get("lastFundingRate") or 0) * 100
        except Exception:
            continue
        if px > 0 and units > 0:
            out[sym] = {"provider": "Binance Futures", "oi_usd": units * px, "mark_price": px, "funding_pct": funding}
    return out


def provider_catalogs(rows):
    catalogs, health = {}, {}
    providers = (("Gate Futures", gate_catalog), ("Bybit Perpetuals", bybit_catalog))
    for name, fn in providers:
        try:
            catalogs[name] = fn()
            health[name] = {"status": "OK", "symbols": len(catalogs[name])}
        except Exception as e:
            catalogs[name] = {}
            health[name] = {"status": "ERROR", "error": f"{type(e).__name__}:{str(e)[:120]}"}
    configured_symbols = {
        str(t.get("derivatives_symbol") or t.get("symbol") or "").upper()
        for t in rows
        if str(t.get("candidate_type") or "CONFIGURED").upper() == "CONFIGURED"
    }
    try:
        catalogs["Binance Futures"] = binance_catalog(configured_symbols)
        health["Binance Futures"] = {"status": "OK", "symbols": len(catalogs["Binance Futures"])}
    except Exception as e:
        catalogs["Binance Futures"] = {}
        health["Binance Futures"] = {"status": "ERROR", "error": f"{type(e).__name__}:{str(e)[:120]}"}
    return catalogs, health


def pick_snapshot(t, catalogs):
    sym = str(t.get("derivatives_symbol") or t.get("symbol") or "").upper()
    ctype = str(t.get("candidate_type") or "CONFIGURED").upper()
    if not sym:
        return None
    # Gate-discovered identities are contract-linked to the Gate spot symbol, so
    # only Gate futures may be attached automatically. This prevents ticker collisions.
    if ctype == "GATE_SPOT_DISCOVERY":
        snap = (catalogs.get("Gate Futures") or {}).get(sym)
        return dict(snap, derivative_symbol=sym) if snap else None
    for provider in ("Bybit Perpetuals", "Gate Futures", "Binance Futures"):
        snap = (catalogs.get(provider) or {}).get(sym)
        if snap:
            return dict(snap, derivative_symbol=sym)
    return None


def main():
    doc = load(EVENTS, {"version": 3, "events": []})
    state = load(STATE, {"version": 3, "tokens": {}})
    state["version"] = 3
    old_tokens = state.setdefault("tokens", {})
    out = []
    rows = targets()
    catalogs, provider_health = provider_catalogs(rows)
    provider_ok = {k: 0 for k in catalogs}
    unavailable = 0
    not_listed = 0

    for t in rows:
        sym = str(t.get("symbol") or "").upper()
        i = ident(t)
        if not sym or not i:
            continue
        prev = old_tokens.get(i[3]) or {}
        snap = pick_snapshot(t, catalogs)
        if not snap:
            not_listed += 1
            old_tokens.setdefault(i[3], {"symbol": sym, "identity_key": i[3]})["last_derivatives_status"] = {
                "status": "NOT_LISTED_ON_IDENTITY_SAFE_PROVIDER",
                "observed_at": now(),
            }
            continue

        provider_ok[snap["provider"]] = provider_ok.get(snap["provider"], 0) + 1
        old = float(prev.get("oi_usd") or 0)
        same_provider = prev.get("provider") == snap.get("provider")
        d = pct(snap["oi_usd"], old) if same_provider else None
        if d is not None and abs(d) >= 5:
            out.append(ev(
                t,
                "open_interest_change",
                1 if d > 0 else -1,
                min(100, abs(d) * 3),
                86,
                snap["provider"],
                f"OI {d:+.2f}% vs prior same-provider snapshot",
                oi_usd=snap["oi_usd"],
                delta_pct=round(d, 3),
                funding_pct=snap.get("funding_pct"),
                derivative_symbol=snap.get("derivative_symbol"),
            ))
        funding = float(snap.get("funding_pct") or 0)
        if abs(funding) >= 0.05:
            out.append(ev(
                t,
                "funding_extreme",
                -1,
                min(100, abs(funding) * 1000),
                82,
                snap["provider"],
                f"funding {funding:+.4f}%",
                funding_pct=funding,
                contradicts_bullish=funding > 0,
                derivative_symbol=snap.get("derivative_symbol"),
            ))
        old_tokens[i[3]] = {**snap, "symbol": sym, "identity_key": i[3], "observed_at": now()}

    if all(v.get("status") != "OK" for v in provider_health.values()):
        unavailable = len(rows)

    merged = [e for e in (doc.get("events") or []) if isinstance(e, dict)] + [e for e in out if e]
    ded = {}
    for e in merged:
        ded[(e.get("identity_key") or "", e.get("canonical_event_id"), e.get("kind"))] = e
    doc = {"version": 3, "generated_at": now(), "events": list(ded.values())[-5000:]}
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    state["updated_at"] = now()
    state["provider_success"] = provider_ok
    state["provider_health"] = provider_health
    state["unavailable_targets"] = unavailable
    state["not_listed_targets"] = not_listed
    state["target_count"] = len(rows)
    state["http_resilience"] = resilient_http.metrics()
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "new_events": len([x for x in out if x]),
        "targets": len(rows),
        "provider_success": provider_ok,
        "provider_health": provider_health,
        "not_listed": not_listed,
        "unavailable": unavailable,
        "http": resilient_http.metrics(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
