from __future__ import annotations

import json
import os
import urllib.error
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
        if ctype == "BUY_ZONE" and not t.get("derivatives_symbol"):
            continue
        # Gate spot candidates are identity-safe on Gate because their symbol was
        # resolved from that exchange into this exact chain+contract+pair.
        # BUY_ZONE derivatives are allowed only with an explicit derivatives_symbol.
        if ctype in {"GATE_SPOT_DISCOVERY", "CONFIGURED", "BUY_ZONE"}:
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
        "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR_WITH_DECLARED_DERIVATIVE_SYMBOL_MAPPING",
    }
    x.update(extra)
    return x


def jget(url, cache_ttl=45, attempts=4):
    return resilient_http.request_json(
        url,
        timeout=15,
        attempts=attempts,
        cache_ttl=cache_ttl,
        user_agent="Wallet500-Derivatives/4.0",
    )


def jpost(url, payload, cache_ttl=45, attempts=4):
    return resilient_http.request_json(
        url,
        method="POST",
        payload=payload,
        timeout=15,
        attempts=attempts,
        cache_ttl=cache_ttl,
        user_agent="Wallet500-Derivatives/4.0",
    )


def gate_contract_catalog():
    # Contract metadata does NOT contain the OI field we need. It is used only
    # for existence/mark/funding; OI comes from /contract_stats below.
    rows = jget("https://api.gateio.ws/api/v4/futures/usdt/contracts?limit=1000&offset=0", 60)
    if not isinstance(rows, list):
        raise RuntimeError("GATE_CONTRACT_LIST_NOT_ARRAY")
    out = {}
    for d in rows:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name") or "").upper()
        if not name.endswith("_USDT") or d.get("in_delisting") is True:
            continue
        sym = name[:-5]
        try:
            px = float(d.get("mark_price") or d.get("last_price") or 0)
            funding = float(d.get("funding_rate") or 0) * 100
        except Exception:
            continue
        if px > 0:
            out[sym] = {
                "contract": name,
                "mark_price": px,
                "funding_pct": funding,
            }
    return out


def gate_snapshot(sym, meta):
    if not meta:
        return None
    contract = meta["contract"]
    q = urllib.parse.urlencode({"contract": contract, "limit": 1})
    stats = jget(f"https://api.gateio.ws/api/v4/futures/usdt/contract_stats?{q}", 25)
    if not isinstance(stats, list) or not stats:
        return None
    s = stats[-1] if isinstance(stats[-1], dict) else {}
    try:
        oi_usd = float(s.get("open_interest_usd") or 0)
        mark = float(s.get("mark_price") or meta.get("mark_price") or 0)
    except Exception:
        return None
    if oi_usd <= 0 or mark <= 0:
        return None
    return {
        "provider": "Gate Futures",
        "oi_usd": oi_usd,
        "mark_price": mark,
        "funding_pct": float(meta.get("funding_pct") or 0),
        "derivative_symbol": sym,
        "derivative_contract": contract,
        "mapping": "GATE_SPOT_SYMBOL_TO_GATE_FUTURES" if sym else "GATE_FUTURES",
    }


def hyperliquid_catalog():
    doc = jpost("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"}, 45)
    if not isinstance(doc, list) or len(doc) < 2:
        raise RuntimeError("HYPERLIQUID_META_CONTEXT_SCHEMA")
    meta, contexts = doc[0], doc[1]
    universe = (meta or {}).get("universe") or []
    if not isinstance(universe, list) or not isinstance(contexts, list):
        raise RuntimeError("HYPERLIQUID_UNIVERSE_SCHEMA")
    out = {}
    for asset, ctx in zip(universe, contexts):
        if not isinstance(asset, dict) or not isinstance(ctx, dict):
            continue
        sym = str(asset.get("name") or "").upper()
        try:
            mark = float(ctx.get("markPx") or ctx.get("midPx") or 0)
            oi_units = float(ctx.get("openInterest") or 0)
            funding = float(ctx.get("funding") or 0) * 100
        except Exception:
            continue
        oi_usd = oi_units * mark
        if sym and mark > 0 and oi_usd > 0:
            out[sym] = {
                "provider": "Hyperliquid",
                "oi_usd": oi_usd,
                "mark_price": mark,
                "funding_pct": funding,
                "derivative_symbol": sym,
                "mapping": "CONFIGURED_SYMBOL_TO_HYPERLIQUID_PERP",
            }
    return out


def restricted_provider_health():
    # Hosted GitHub egress produced deterministic Binance 451 and Bybit 403.
    # Do not burn requests every 15 minutes. They can be opt-in re-probed.
    enabled = os.getenv("WALLET500_REPROBE_GEO_RESTRICTED_DERIVATIVES", "0") == "1"
    status = "REPROBE_ENABLED_NOT_IMPLEMENTED" if enabled else "DISABLED_AFTER_RUNTIME_GEO_RESTRICTION"
    return {
        "Binance Futures": {"status": status, "last_observed_http": 451},
        "Bybit Perpetuals": {"status": status, "last_observed_http": 403},
    }


def main():
    doc = load(EVENTS, {"version": 3, "events": []})
    state = load(STATE, {"version": 4, "tokens": {}})
    state["version"] = 4
    old_tokens = state.setdefault("tokens", {})
    rows = targets()
    out = []

    provider_health = restricted_provider_health()
    provider_success = {"Gate Futures": 0, "Hyperliquid": 0, "Binance Futures": 0, "Bybit Perpetuals": 0}

    try:
        gate_meta = gate_contract_catalog()
        provider_health["Gate Futures"] = {"status": "OK", "contracts": len(gate_meta)}
    except Exception as e:
        gate_meta = {}
        provider_health["Gate Futures"] = {"status": "ERROR", "error": f"{type(e).__name__}:{str(e)[:160]}"}

    try:
        hyper = hyperliquid_catalog()
        provider_health["Hyperliquid"] = {"status": "OK", "contracts": len(hyper)}
    except Exception as e:
        hyper = {}
        provider_health["Hyperliquid"] = {"status": "ERROR", "error": f"{type(e).__name__}:{str(e)[:160]}"}

    not_listed = 0
    provider_errors = 0
    mapping_rejected = 0

    for t in rows:
        i = ident(t)
        sym = str(t.get("derivatives_symbol") or t.get("symbol") or "").upper()
        ctype = str(t.get("candidate_type") or "CONFIGURED").upper()
        if not i or not sym:
            continue
        prev = old_tokens.get(i[3]) or {}
        snap = None
        errors = []

        # Gate discovery has a strong exchange-local mapping: Gate supplied the
        # spot symbol AND the chain contract that became this exact identity.
        # Configured targets have deliberate operator mapping and may fail over
        # to Hyperliquid if Gate has no perp.
        if sym in gate_meta:
            try:
                snap = gate_snapshot(sym, gate_meta[sym])
                if snap:
                    snap["mapping"] = (
                        "GATE_SPOT_CONTRACT_RESOLUTION_TO_SAME_GATE_SYMBOL_PERP"
                        if ctype == "GATE_SPOT_DISCOVERY"
                        else "EXPLICIT_BUY_ZONE_DERIVATIVES_SYMBOL_TO_GATE_PERP"
                        if ctype == "BUY_ZONE"
                        else "CONFIGURED_SYMBOL_TO_GATE_PERP"
                    )
            except urllib.error.HTTPError as e:
                errors.append(f"GateHTTP{e.code}")
            except Exception as e:
                errors.append(f"Gate:{type(e).__name__}")

        if snap is None and ctype in {"CONFIGURED", "BUY_ZONE"}:
            h = hyper.get(sym)
            if h:
                snap = dict(h)

        # Never attach cross-exchange ticker-only data to an arbitrary dynamic
        # token. For non-Gate dynamic alpha this collector is intentionally off.
        if snap is None:
            not_listed += 1
            if errors:
                provider_errors += 1
            old_tokens.setdefault(i[3], {"symbol": sym, "identity_key": i[3]})["last_derivatives_status"] = {
                "status": "NOT_LISTED_ON_IDENTITY_SAFE_PROVIDER" if not errors else "PROVIDER_LOOKUP_FAILED",
                "errors": errors,
                "observed_at": now(),
            }
            continue

        provider_success[snap["provider"]] = provider_success.get(snap["provider"], 0) + 1
        old_oi = float(prev.get("oi_usd") or 0)
        same_provider = prev.get("provider") == snap.get("provider")
        d = pct(snap["oi_usd"], old_oi) if same_provider else None

        if d is not None and abs(d) >= 5:
            out.append(ev(
                t,
                "open_interest_change",
                1 if d > 0 else -1,
                min(100, abs(d) * 3),
                88,
                snap["provider"],
                f"OI {d:+.2f}% vs prior same-provider snapshot",
                oi_usd=snap["oi_usd"],
                delta_pct=round(d, 3),
                funding_pct=snap.get("funding_pct"),
                derivative_symbol=snap.get("derivative_symbol"),
                derivative_identity_mapping=snap.get("mapping"),
            ))

        funding = float(snap.get("funding_pct") or 0)
        if abs(funding) >= 0.05:
            out.append(ev(
                t,
                "funding_extreme",
                -1,
                min(100, abs(funding) * 1000),
                84,
                snap["provider"],
                f"funding {funding:+.4f}%",
                funding_pct=funding,
                contradicts_bullish=funding > 0,
                derivative_symbol=snap.get("derivative_symbol"),
                derivative_identity_mapping=snap.get("mapping"),
            ))

        old_tokens[i[3]] = {
            **snap,
            "symbol": str(t.get("symbol") or sym).upper(),
            "identity_key": i[3],
            "observed_at": now(),
            "last_derivatives_status": {"status": "OK", "observed_at": now()},
        }

    merged = [e for e in (doc.get("events") or []) if isinstance(e, dict)] + [e for e in out if e]
    ded = {}
    for e in merged:
        ded[(e.get("identity_key") or "", e.get("canonical_event_id"), e.get("kind"))] = e
    doc = {"version": 3, "generated_at": now(), "events": list(ded.values())[-5000:]}
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    healthy_providers = [k for k, v in provider_health.items() if v.get("status") == "OK"]
    state["updated_at"] = now()
    state["provider_success"] = provider_success
    state["provider_health"] = provider_health
    state["healthy_providers"] = healthy_providers
    state["unavailable_targets"] = len(rows) if not healthy_providers else 0
    state["not_listed_targets"] = not_listed
    state["provider_lookup_errors"] = provider_errors
    state["mapping_rejected"] = mapping_rejected
    state["target_count"] = len(rows)
    state["http_resilience"] = resilient_http.metrics()
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({
        "status": "OK",
        "new_events": len([x for x in out if x]),
        "targets": len(rows),
        "provider_success": provider_success,
        "provider_health": provider_health,
        "healthy_providers": healthy_providers,
        "not_listed": not_listed,
        "provider_lookup_errors": provider_errors,
        "unavailable": state["unavailable_targets"],
        "http": resilient_http.metrics(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
