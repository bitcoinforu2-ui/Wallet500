from __future__ import annotations

import json
import os
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
STATE = ROOT / "data/unified-watch-state.json"
CAND = ROOT / "data/alpha-caller-candidates.json"
INTEL = ROOT / "data/close-watch-intelligence.json"
INTEL_REPORT = ROOT / "data/unified-watch-intelligence-report.json"
EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def chain_name(value):
    raw = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(raw, raw)


def norm_addr(chain, value):
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def exact_identity_key(row):
    chain = chain_name(row.get("chain") or row.get("network"))
    token = norm_addr(chain, row.get("token_address") or row.get("contract") or row.get("mint"))
    pair = norm_addr(chain, row.get("pair_address") or row.get("pair"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def load_intelligence():
    try:
        doc = json.loads(INTEL.read_text()) if INTEL.exists() else {}
    except Exception:
        doc = {}
    rows = [x for x in (doc.get("tokens") or []) if isinstance(x, dict)]
    return {exact_identity_key(x): x for x in rows if exact_identity_key(x)}, doc


def http_json(url):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "Wallet500-UnifiedWatch/1.2"})
    return json.load(urllib.request.urlopen(req, timeout=20))


def token_id_matches(v, c):
    return norm_addr(chain_name(str(v or "").split("_")[0] if "_" in str(v or "") else ""), v) == c or str(v or "").lower().endswith("_" + str(c).lower())


def live_exact_pair(t, max_spread):
    n = str(t["network"]).strip().lower()
    canonical_chain = chain_name(n)
    pair = norm_addr(canonical_chain, t["pair"])
    ca = norm_addr(canonical_chain, t["contract"])
    gt = http_json(f"https://api.geckoterminal.com/api/v2/networks/{n}/pools/{t['pair']}")
    o = gt.get("data") or {}
    a = o.get("attributes") or {}
    r = o.get("relationships") or {}
    b = (((r.get("base_token") or {}).get("data") or {}).get("id") or "")
    q = (((r.get("quote_token") or {}).get("data") or {}).get("id") or "")
    b_addr = str(b).split("_")[-1]
    q_addr = str(q).split("_")[-1]
    if norm_addr(canonical_chain, b_addr) == ca:
        gp = float(a.get("base_token_price_usd") or 0)
    elif norm_addr(canonical_chain, q_addr) == ca:
        gp = float(a.get("quote_token_price_usd") or 0)
    else:
        raise RuntimeError("EXACT_PAIR_IDENTITY_MISMATCH_GT")
    if gp <= 0:
        raise RuntimeError("GT_PRICE_MISSING")
    vol = a.get("volume_usd") or {}
    tx = a.get("transactions") or {}
    h1 = tx.get("h1") or {}
    ch = a.get("price_change_percentage") or {}
    g = {
        "price": gp,
        "liquidity": float(a.get("reserve_in_usd") or 0),
        "volume_h1": float(vol.get("h1") or 0),
        "volume_h24": float(vol.get("h24") or 0),
        "buys_h1": int(h1.get("buys") or 0),
        "sells_h1": int(h1.get("sells") or 0),
        "change_h1": float(ch.get("h1") or 0),
        "change_h24": float(ch.get("h24") or 0),
    }
    if g["liquidity"] <= 0:
        raise RuntimeError("GT_LIQUIDITY_MISSING")
    dsnet = "ethereum" if n == "eth" else n
    ds = http_json(f"https://api.dexscreener.com/latest/dex/pairs/{dsnet}/{t['pair']}")
    p = next((x for x in (ds.get("pairs") or []) if chain_name(x.get("chainId")) == canonical_chain and norm_addr(canonical_chain, x.get("pairAddress")) == pair), None)
    if not p:
        raise RuntimeError("EXACT_PAIR_MISSING_DS")
    base = norm_addr(canonical_chain, (p.get("baseToken") or {}).get("address"))
    quote = norm_addr(canonical_chain, (p.get("quoteToken") or {}).get("address"))
    if ca not in {base, quote}:
        raise RuntimeError("DS_TOKEN_NOT_IN_EXACT_PAIR_FAIL_CLOSED")
    dp = float(p.get("priceUsd") or 0)
    if dp <= 0:
        raise RuntimeError("DS_PRICE_MISSING")
    med = statistics.median([gp, dp])
    spread = ((max(gp, dp) - min(gp, dp)) / med) * 100 if med else 999
    if spread > max_spread:
        raise RuntimeError(f"SOURCE_DATA_MISMATCH:{spread:.3f}%")
    return {**g, "price": med, "gt_price": gp, "ds_price": dp, "spread_pct": spread, "observed_at": now_iso()}


def money(v):
    v = float(v)
    if abs(v) >= 1e6:
        return f"${v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.2f}"


def send(msg):
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        raise RuntimeError("TELEGRAM_SECRETS_NOT_CONFIGURED")
    data = urllib.parse.urlencode({"chat_id": chat, "text": msg[:4000], "disable_web_page_preview": "true"}).encode()
    body = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{bot}/sendMessage", data=data, method="POST"), timeout=20))
    if not body.get("ok"):
        raise RuntimeError("TELEGRAM_SEND_FAILED")


def dynamic_candidates():
    if not CAND.exists():
        return []
    d = json.loads(CAND.read_text())
    out = []
    seen = set()
    for c in d.get("candidates") or []:
        if c.get("status") != "GATED_RESEARCH_CANDIDATE":
            continue
        ca = str(c.get("contract") or "")
        pair = str(c.get("pair") or "")
        network = str(c.get("network") or "")
        if not ca or not pair or not network:
            continue
        key = exact_identity_key({"network": network, "contract": ca, "pair": pair})
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"symbol": str(c.get("symbol") or "ALPHA").upper(), "network": network, "contract": ca, "pair": pair, "dex_url": c.get("dex_url") or "", "up_levels": [], "down_levels": [], "liquidity_drop_pct": 25, "volume_acceleration_multiple": 2.0, "min_volume_h1_for_momentum": 0, "dynamic_alpha_candidate": True})
    return out[:100]


def fusion_summary(row):
    if not row:
        return {"status": "NOT_AVAILABLE", "score": None, "label": "NOT_AVAILABLE", "families": 0, "hard_risks": [], "updated_at": None, "evidence_age_minutes": None}
    return {
        "status": row.get("status") or "UNKNOWN",
        "score": row.get("score"),
        "label": row.get("label") or "WATCH",
        "families": int(row.get("independent_positive_families") or 0),
        "hard_risks": list(row.get("hard_risks") or []),
        "updated_at": row.get("updated_at"),
        "freshest_event_at": row.get("freshest_event_at"),
        "evidence_age_minutes": row.get("evidence_age_minutes"),
        "current_evidence_count": int(row.get("current_evidence_count") or 0),
    }


def main():
    cfg = json.loads(CONFIG.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {"version": 1, "tokens": {}}
    st = state.setdefault("tokens", {})
    spread = float((cfg.get("data_integrity") or {}).get("max_price_source_spread_pct", 2))
    tokens = list(cfg.get("tokens") or [])
    known = {exact_identity_key(x) for x in tokens}
    tokens += [x for x in dynamic_candidates() if exact_identity_key(x) not in known]
    intel_index, intel_doc = load_intelligence()
    intel_rows = []

    for t in tokens:
        sym = t["symbol"].upper()
        identity_key = exact_identity_key(t)
        key = sym if not t.get("dynamic_alpha_candidate") else f"ALPHA:{identity_key}"
        prev = st.get(key) or {}
        fusion = fusion_summary(intel_index.get(identity_key))
        try:
            live = live_exact_pair(t, spread)
        except Exception as e:
            print(key, "UNVERIFIED", str(e), "INTELLIGENCE", fusion)
            intel_rows.append({"symbol": sym, "identity_key": identity_key, "market_verified": False, "intelligence": fusion, "error": str(e)[:240]})
            continue

        pp = float(prev.get("price") or 0)
        pl = float(prev.get("liquidity") or 0)
        pv = float(prev.get("volume_h1") or 0)
        tr = []
        if pp > 0:
            for lv in t.get("up_levels") or []:
                if pp < float(lv) <= live["price"]:
                    tr.append(f"BREAK_ABOVE_{float(lv):g}")
            for lv in t.get("down_levels") or []:
                if pp >= float(lv) > live["price"]:
                    tr.append(f"LOSS_BELOW_{float(lv):g}")
            drop = float(t.get("liquidity_drop_pct") or 25)
            if pl > 0 and live["liquidity"] < pl * (1 - drop / 100):
                tr.append(f"LIQUIDITY_DROP_GT_{drop:g}PCT")
            mult = float(t.get("volume_acceleration_multiple") or 2)
            minv = float(t.get("min_volume_h1_for_momentum") or 0)
            if pv > 0 and live["volume_h1"] >= max(minv, pv * mult) and live["price"] > pp:
                tr.append("PRICE_PLUS_VOLUME_ACCELERATION")
            if t.get("dynamic_alpha_candidate") and live["buys_h1"] >= 10 and live["buys_h1"] >= max(2 * live["sells_h1"], 10):
                tr.append("ALPHA_CALL_PLUS_BUY_IMBALANCE")

        st[key] = {
            "symbol": sym,
            "network": t["network"],
            "contract": t["contract"],
            "pair": t["pair"],
            "identity_key": identity_key,
            "price": live["price"],
            "liquidity": live["liquidity"],
            "volume_h1": live["volume_h1"],
            "volume_h24": live["volume_h24"],
            "buys_h1": live["buys_h1"],
            "sells_h1": live["sells_h1"],
            "spread_pct": live["spread_pct"],
            "observed_at": live["observed_at"],
            "dynamic_alpha_candidate": bool(t.get("dynamic_alpha_candidate")),
            "intelligence_fusion": fusion,
        }
        intel_rows.append({"symbol": sym, "identity_key": identity_key, "market_verified": True, "intelligence": fusion})
        print(key, "VERIFIED", st[key], "TRIGGERS", tr)

        if tr:
            hard_risk = bool(fusion.get("hard_risks"))
            risk = hard_risk or any(x.startswith("LOSS_") or "LIQUIDITY_DROP" in x for x in tr)
            label = "RISK" if risk else ("ALPHA_CLOSE_WATCH" if t.get("dynamic_alpha_candidate") else "REVIVAL_BUILDING")
            icon = "⚠️" if risk else "🔥"
            score_text = "n/a" if fusion.get("score") is None else f"{float(fusion['score']):.1f}/100"
            intel_line = f"Intelligence Fusion: {score_text} · {fusion.get('label')} · {fusion.get('families')} independent positive families · {fusion.get('status')}"
            if fusion.get("hard_risks"):
                intel_line += " · HARD RISK: " + ", ".join(map(str, fusion["hard_risks"]))
            msg = "\n".join([
                f"{icon} {sym} | WALLET500 UNIFIED WATCH | {label}",
                f"CURRENT VERIFIED PRICE: ${live['price']:.8f}",
                f"SOURCE: GeckoTerminal exact pair + DexScreener exact pair | spread {live['spread_pct']:.2f}%",
                f"OBSERVED: {live['observed_at']}",
                f"Previous verified: ${pp:.8f}",
                f"1H {live['change_h1']:+.2f}% | 24H {live['change_h24']:+.2f}%",
                f"Liquidity {money(live['liquidity'])} | Vol 1H {money(live['volume_h1'])}",
                f"Buys/Sells 1H: {live['buys_h1']}/{live['sells_h1']}",
                intel_line,
                "Fusion mode: SHADOW EVIDENCE — does not promote a production REAL ALERT yet.",
                "TRIGGERS: " + ", ".join(tr),
                "Research/close watch only — never auto-trade.",
                f"CA: {t['contract']}",
                f"Pair: {t['pair']}",
                str(t.get("dex_url") or ""),
            ])
            send(msg)

    state["updated_at"] = now_iso()
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    report = {
        "version": 1,
        "updated_at": now_iso(),
        "mode": "EXACT_PAIR_INTELLIGENCE_SHADOW",
        "fusion_snapshot_generated_at": intel_doc.get("generated_at") if isinstance(intel_doc, dict) else None,
        "targets": intel_rows,
    }
    INTEL_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "OK", "configured": len(cfg.get("tokens") or []), "dynamic_alpha": len(tokens) - len(cfg.get("tokens") or []), "intelligence_targets": len(intel_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
