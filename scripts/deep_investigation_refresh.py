from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cross_domain_intelligence_collector as cross
import free_intelligence_collector as free
import intelligence_fusion

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "data/close-watch-events.json"
CROSS_STATE = ROOT / "data/cross-domain-intelligence-state.json"
FREE_STATE = ROOT / "data/free-intelligence-collector-state.json"

_ATTENTION_CACHE = None
_ATTENTION_CACHE_AT = 0.0


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def positive_investigation_reasons(live, triggers, material_reasons, policy):
    reasons = []
    if any(
        x in {"PRICE_PLUS_VOLUME_ACCELERATION", "ALPHA_CALL_PLUS_BUY_IMBALANCE"}
        or str(x).startswith("BREAK_ABOVE_")
        for x in triggers
    ):
        reasons.append("POSITIVE_MARKET_TRIGGER")

    buys = int(live.get("buys_h1") or 0)
    sells = int(live.get("sells_h1") or 0)
    ratio = (buys + 1.0) / (sells + 1.0)
    min_buys = int(policy.get("deep_investigation_min_buys_h1", 15))
    min_ratio = float(policy.get("deep_investigation_min_buy_sell_ratio", 2.0))
    if buys >= min_buys and ratio >= min_ratio:
        reasons.append(f"BUY_FLOW_IMBALANCE_{ratio:.1f}X")

    for reason in material_reasons or []:
        r = str(reason)
        if r.startswith("VOLUME_EXPANSION_"):
            reasons.append(r)
        elif r.startswith("BUY_PRESSURE_SHIFT_"):
            reasons.append(r)
        elif r.startswith("PRICE_CHANGE_+"):
            reasons.append(r)
        elif r.startswith("NEW_TRIGGER:") and not any(
            bad in r for bad in ("LOSS_", "LIQUIDITY_DROP")
        ):
            reasons.append(r)

    return list(dict.fromkeys(reasons))


def _event(t, engine, family, kind, direction, strength, confidence, source, **extra):
    chain = engine.chain_name(t.get("network") or t.get("chain"))
    contract = engine.norm_addr(chain, t.get("contract") or t.get("token_address"))
    pair = engine.norm_addr(chain, t.get("pair") or t.get("pair_address"))
    ts = now_iso()
    identity_key = f"{chain}:{contract}:{pair}"
    e = {
        "symbol": str(t.get("symbol") or "").upper(),
        "network": chain,
        "contract": contract,
        "pair": pair,
        "identity_key": identity_key,
        "family": family,
        "kind": kind,
        "direction": int(direction),
        "strength": round(max(0.0, min(100.0, float(strength))), 1),
        "confidence": round(max(0.0, min(100.0, float(confidence))), 1),
        "source": source,
        "event_time": ts,
        "observed_at": ts,
        "identity_verified": True,
        "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR_DEEP_INVESTIGATION",
        "deep_investigation": True,
    }
    e.update(extra)
    e.setdefault(
        "canonical_event_id",
        f"deep:{identity_key}:{kind}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
    )
    return e


def _market_events(t, engine, live, previous_scan):
    out = [
        _event(
            t,
            engine,
            "market_microstructure",
            "verified_market_snapshot",
            0,
            0,
            100,
            "GeckoTerminal+DexScreener exact-pair consensus",
            price_usd=live.get("price"),
            liquidity_usd=live.get("liquidity"),
            volume_h1_usd=live.get("volume_h1"),
            buys_h1=live.get("buys_h1"),
            sells_h1=live.get("sells_h1"),
            spread_pct=live.get("spread_pct"),
        )
    ]
    pp = float(previous_scan.get("price") or 0)
    pv = float(previous_scan.get("volume_h1") or 0)
    pl = float(previous_scan.get("liquidity") or 0)
    price = float(live.get("price") or 0)
    vol = float(live.get("volume_h1") or 0)
    liq = float(live.get("liquidity") or 0)
    buys = int(live.get("buys_h1") or 0)
    sells = int(live.get("sells_h1") or 0)
    ratio = (buys + 1.0) / (sells + 1.0)

    if pp > 0:
        pd = (price / pp - 1) * 100
        if abs(pd) >= 5:
            out.append(_event(t, engine, "market_microstructure", "price_structure", 1 if pd > 0 else -1, min(100, abs(pd) * 3), 92, "Exact-pair scan delta", change_pct=round(pd, 2), contradicts_bullish=pd < 0))
    if pv > 0:
        vm = vol / pv
        if vm >= 1.5:
            out.append(_event(t, engine, "market_microstructure", "volume_acceleration", 1, min(100, (vm - 1) * 55), 90, "Exact-pair scan delta", multiple=round(vm, 3)))
    if buys + sells >= 20:
        if ratio >= 1.25:
            out.append(_event(t, engine, "market_microstructure", "buy_sell_imbalance", 1, min(100, (ratio - 1) * 70), 90, "Exact-pair transaction flow", value=round(ratio, 3)))
        elif ratio <= 0.8:
            out.append(_event(t, engine, "market_microstructure", "buy_sell_imbalance", -1, min(100, (1 / max(ratio, 0.01) - 1) * 55), 90, "Exact-pair transaction flow", value=round(ratio, 3), contradicts_bullish=True))
    if pl > 0:
        ld = (liq / pl - 1) * 100
        if abs(ld) >= 10:
            out.append(_event(t, engine, "market_microstructure", "liquidity_change", 1 if ld > 0 else -1, min(100, abs(ld) * 2), 90, "Exact-pair scan delta", change_pct=round(ld, 2), contradicts_bullish=ld < 0, hard_risk=ld <= -45))
    return out


def _holder_events(t, engine, hs, previous_holder):
    if not hs:
        return []
    out = [
        _event(
            t,
            engine,
            "holder_network",
            "holder_structure_snapshot",
            0,
            0,
            90,
            hs.get("provider") or "native chain holder provider",
            holders_count=hs.get("holders_count"),
            top10_pct=hs.get("top10_pct"),
            top20_pct=hs.get("top20_pct"),
        )
    ]
    hc = hs.get("holders_count")
    phc = (previous_holder or {}).get("holders_count")
    if hc is not None and phc not in (None, 0):
        delta = (float(hc) - float(phc)) / abs(float(phc)) * 100
        if abs(delta) >= 2:
            out.append(_event(t, engine, "holder_network", "holder_growth", 1 if delta > 0 else -1, min(100, abs(delta) * 8), 88, hs.get("provider") or "holder provider", holder_count=hc, change_pct=round(delta, 3), contradicts_bullish=delta < 0))
    top10 = hs.get("top10_pct")
    ptop10 = (previous_holder or {}).get("top10_pct")
    if top10 is not None and float(top10) >= 70:
        out.append(_event(t, engine, "holder_network", "holder_concentration", -1, min(100, 35 + (float(top10) - 70) * 2), 82, hs.get("provider") or "holder provider", top10_pct=round(float(top10), 2), contradicts_bullish=True))
    if top10 is not None and ptop10 is not None and abs(float(top10) - float(ptop10)) >= 1.5:
        dpp = float(top10) - float(ptop10)
        out.append(_event(t, engine, "wallet_flow", "top_holder_balance_change", -1 if dpp > 0 else 1, min(100, abs(dpp) * 12), 82, hs.get("provider") or "holder provider", top10_pct=round(float(top10), 2), change_pp=round(dpp, 2), contradicts_bullish=dpp > 0))
    exu = hs.get("exchange_top_units")
    pexu = (previous_holder or {}).get("exchange_top_units")
    if exu is not None and pexu not in (None, 0):
        d = (float(exu) - float(pexu)) / abs(float(pexu)) * 100
        if abs(d) >= 10:
            out.append(_event(t, engine, "wallet_flow", "exchange_netflow", -1 if d > 0 else 1, min(100, abs(d) * 2), 78, hs.get("provider") or "holder provider", exchange_top_units=exu, change_pct=round(d, 2), contradicts_bullish=d > 0))
    return out


def _news_events(t, engine, ns):
    if ns is None:
        return []
    out = [
        _event(
            t,
            engine,
            "catalyst_news",
            "news_scan_snapshot",
            0,
            0,
            70,
            "Google News RSS",
            article_count_24h=int(ns.get("count") or 0),
            subject=" | ".join(x.get("title", "") for x in (ns.get("titles") or [])[:2]),
        )
    ]
    if int(ns.get("count") or 0) >= 2 and int(ns.get("direction") or 0):
        direction = int(ns.get("direction") or 0)
        out.append(_event(t, engine, "catalyst_news", "news_velocity", direction, min(80, 30 + int(ns.get("count") or 0) * 8), 62, "Google News RSS", article_count_24h=int(ns.get("count") or 0), positive_hits=int(ns.get("positive") or 0), negative_hits=int(ns.get("negative") or 0), subject=" | ".join(x.get("title", "") for x in (ns.get("titles") or [])[:2]), contradicts_bullish=direction < 0))
    return out


def _attention_maps():
    global _ATTENTION_CACHE, _ATTENTION_CACHE_AT
    if _ATTENTION_CACHE is not None and time.time() - _ATTENTION_CACHE_AT < 300:
        return _ATTENTION_CACHE
    try:
        _ATTENTION_CACHE = cross.global_attention_maps()
    except Exception:
        _ATTENTION_CACHE = ({}, {})
    _ATTENTION_CACHE_AT = time.time()
    return _ATTENTION_CACHE


def _attention_events(t, engine):
    i = cross.ident(t)
    if not i:
        return []
    trending, boosts = _attention_maps()
    out = []
    rank = trending.get((cross.GT_NET.get(i[0], i[0]), i[2].lower()))
    if rank:
        out.append(_event(t, engine, "search_discovery", "geckoterminal_trending_pool", 1, max(35, 100 - rank * 5), 84, "GeckoTerminal Trending", rank=rank, canonical_event_id=f"deep-gt:{i[3]}:{rank}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"))
    boost = boosts.get((i[0], i[1]))
    if boost and boost > 0:
        out.append(_event(t, engine, "attention_social", "paid_attention_boost", 1, min(60, 20 + boost ** 0.5), 58, "DexScreener Boosts", boost_amount=boost, paid_attention=True, canonical_event_id=f"deep-boost:{i[3]}:{int(boost)}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"))
    return out


def _merge_events(fresh):
    doc = _load(EVENTS, {"version": 3, "events": []})
    ded = {}
    for e in [x for x in (doc.get("events") or []) if isinstance(x, dict)] + fresh:
        ded[(e.get("identity_key") or "", e.get("canonical_event_id"), e.get("kind"))] = e
    doc["version"] = max(3, int(doc.get("version") or 0))
    doc["generated_at"] = now_iso()
    doc["identity_mode"] = "EXACT_CHAIN_CONTRACT_PAIR"
    doc["events"] = list(ded.values())[-5000:]
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def run_one(engine, policy, t, live, previous_scan, triggers, material_reasons):
    qualification = positive_investigation_reasons(live, triggers, material_reasons, policy)
    if not qualification:
        return None

    identity_key = engine.exact_identity_key(t)
    if not identity_key:
        return None

    cross_state = _load(CROSS_STATE, {"version": 1, "tokens": {}})
    free_state = _load(FREE_STATE, {"version": 2, "tokens": {}})
    fresh = _market_events(t, engine, live, previous_scan)
    providers = {"market": "OK_EXACT_PAIR_CONSENSUS"}

    try:
        hs = cross.holder_snapshot(t)
        providers["holder_wallet"] = "OK" if hs else "NO_DATA"
    except Exception as exc:
        hs = None
        providers["holder_wallet"] = f"ERROR:{type(exc).__name__}"
    previous_holder = ((cross_state.get("tokens") or {}).get(identity_key) or {}).get("holder") or {}
    fresh += _holder_events(t, engine, hs, previous_holder)

    try:
        ns = cross.news_snapshot(t)
        providers["news"] = "OK" if ns is not None else "NO_DATA"
    except Exception as exc:
        ns = None
        providers["news"] = f"ERROR:{type(exc).__name__}"
    fresh += _news_events(t, engine, ns)

    before_attention = len(fresh)
    fresh += _attention_events(t, engine)
    providers["search_social_attention"] = "MATCH" if len(fresh) > before_attention else "NO_MATCH"

    free_prev = (free_state.get("tokens") or {}).get(identity_key) or {}
    hsnap = free_prev.get("honeypot") or {}
    try:
        hp, hsnap = free.honeypot(t, hsnap, with_snapshot=True)
        fresh += hp
        providers["security_tokenomics"] = "CHECKED_WITH_CONSECUTIVE_CONFIRMATION" if engine.chain_name(t.get("network")) in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon"} else "NOT_APPLICABLE"
    except Exception as exc:
        providers["security_tokenomics"] = f"ERROR:{type(exc).__name__}"
    try:
        ge, gs = free.github_collect(t, free_prev.get("github") or {})
        fresh += ge
        providers["developer"] = "CHECKED" if (t.get("free_intel") or {}).get("github_repo") else "NOT_MAPPED"
    except Exception as exc:
        gs = free_prev.get("github") or {}
        providers["developer"] = f"ERROR:{type(exc).__name__}"
    try:
        fe, fs = free.defillama(t, free_prev.get("defillama") or {})
        fresh += fe
        providers["fundamental"] = "CHECKED" if (t.get("free_intel") or {}).get("defillama_slug") else "NOT_MAPPED"
    except Exception as exc:
        fs = free_prev.get("defillama") or {}
        providers["fundamental"] = f"ERROR:{type(exc).__name__}"
    providers["derivatives"] = "PRECOLLECTED_THIS_WORKFLOW_WHEN_IDENTITY_SAFE"

    _merge_events(fresh)

    cross_tokens = cross_state.setdefault("tokens", {})
    cross_tokens[identity_key] = {"observed_at": now_iso(), "holder": hs, "news": ns, "deep_investigation": True}
    cross_state["updated_at"] = now_iso()
    CROSS_STATE.write_text(json.dumps(cross_state, indent=2, ensure_ascii=False) + "\n")

    free_tokens = free_state.setdefault("tokens", {})
    free_tokens[identity_key] = {"honeypot": hsnap, "github": gs, "defillama": fs, "observed_at": now_iso(), "deep_investigation": True}
    free_state["updated_at"] = now_iso()
    FREE_STATE.write_text(json.dumps(free_state, indent=2, ensure_ascii=False) + "\n")

    intelligence_fusion.main()
    intel_doc = _load(engine.INTEL, {"tokens": []})
    row = next((x for x in (intel_doc.get("tokens") or []) if engine.exact_identity_key(x) == identity_key), None)

    report = {
        "symbol": str(t.get("symbol") or "").upper(),
        "identity_key": identity_key,
        "candidate_type": t.get("candidate_type") or "CONFIGURED",
        "qualification": qualification,
        "market_triggers": list(triggers),
        "new_evidence": len(fresh),
        "providers": providers,
        "fusion_refreshed": row is not None,
        "generated_at": now_iso(),
    }
    print("DEEP_INVESTIGATION_REFRESH", json.dumps(report, ensure_ascii=False))
    return report, row
