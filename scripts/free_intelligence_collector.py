from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data/unified-watch-config.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/free-intelligence-collector-state.json"
UA = "Wallet500-FreeIntel/2.0"
EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def chain_name(value: object) -> str:
    raw = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(raw, raw)


def norm_addr(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def identity(t: dict) -> tuple[str, str, str, str]:
    chain = chain_name(t.get("network") or t.get("chain"))
    contract = norm_addr(chain, t.get("contract") or t.get("token_address"))
    pair = norm_addr(chain, t.get("pair") or t.get("pair_address"))
    return chain, contract, pair, f"{chain}:{contract}:{pair}"


def same_addr(chain: str, left: object, right: object) -> bool:
    return norm_addr(chain, left) == norm_addr(chain, right)


def get_json(url: str, headers=None, timeout: int = 12):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    try:
        with urlopen(Request(url, headers=h), timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def event(t, fam, kind, direction, strength, confidence, source, subject="", url="", cid="", extra=None):
    chain, contract, pair, identity_key = identity(t)
    ts = now()
    e = {
        "symbol": str(t.get("symbol") or "").upper(),
        "network": chain,
        "contract": contract,
        "pair": pair,
        "identity_key": identity_key,
        "family": fam,
        "kind": kind,
        "direction": direction,
        "strength": round(max(0, min(100, float(strength))), 1),
        "confidence": round(max(0, min(100, float(confidence))), 1),
        "source": source,
        "source_url": url,
        "subject": subject,
        "canonical_event_id": cid or f"{source}:{identity_key}:{kind}",
        "event_time": ts,
        "observed_at": ts,
        "free_source": True,
    }
    if extra:
        e.update(extra)
    return e


def ds_collect(t, prev):
    chain, contract, pair, _ = identity(t)
    data = get_json("https://api.dexscreener.com/latest/dex/tokens/" + contract)
    out = []
    if not data:
        return out, {}
    pairs = data.get("pairs") or []
    exact = next(
        (
            p
            for p in pairs
            if chain_name(p.get("chainId")) == chain and same_addr(chain, p.get("pairAddress"), pair)
        ),
        None,
    )
    if not exact:
        return [event(t, "market_microstructure", "identity_mismatch", -1, 100, 95, "DexScreener", extra={"hard_risk": True})], {}

    base = (exact.get("baseToken") or {}).get("address")
    quote = (exact.get("quoteToken") or {}).get("address")
    if not (same_addr(chain, base, contract) or same_addr(chain, quote, contract)):
        return [event(t, "market_microstructure", "identity_mismatch", -1, 100, 98, "DexScreener", extra={"hard_risk": True})], {}

    liq = num((exact.get("liquidity") or {}).get("usd"))
    vol = num((exact.get("volume") or {}).get("h1"))
    tx = (exact.get("txns") or {}).get("h1") or {}
    buys = num(tx.get("buys"))
    sells = num(tx.get("sells"))
    price = num(exact.get("priceUsd"))
    snap = {"price": price, "liquidity": liq, "volume_h1": vol, "buys_h1": buys, "sells_h1": sells}

    out.append(
        event(
            t,
            "market_microstructure",
            "verified_market_snapshot",
            0,
            0,
            100,
            "DexScreener",
            url=str(exact.get("url") or ""),
            cid=f"dexsnapshot:{identity(t)[3]}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
            extra={"price_usd": price, "liquidity_usd": liq, "volume_h1_usd": vol, "buys_h1": buys, "sells_h1": sells},
        )
    )

    if buys is not None and sells is not None and buys + sells >= 20:
        ratio = (buys + 1) / (sells + 1)
        strength = min(100, abs(ratio - 1) * 90)
        if ratio >= 1.25:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", 1, strength, 82, "DexScreener", extra={"value": ratio}))
        elif ratio <= 0.8:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", -1, strength, 82, "DexScreener", extra={"value": ratio, "contradicts_bullish": True}))

    pv = num(prev.get("volume_h1"))
    pl = num(prev.get("liquidity"))
    if vol is not None and pv and pv > 0:
        multiple = vol / pv
        if multiple >= 1.5:
            out.append(event(t, "market_microstructure", "volume_acceleration", 1, min(100, (multiple - 1) * 55), 78, "DexScreener", extra={"multiple": round(multiple, 3)}))
    if liq is not None and pl and pl > 0:
        change = (liq - pl) / pl * 100
        if change <= -20:
            out.append(event(t, "market_microstructure", "liquidity_change", -1, min(100, abs(change) * 2), 88, "DexScreener", extra={"change_pct": round(change, 2), "contradicts_bullish": True, "hard_risk": change <= -45}))
        elif change >= 15:
            out.append(event(t, "market_microstructure", "liquidity_change", 1, min(100, change * 1.5), 80, "DexScreener", extra={"change_pct": round(change, 2)}))
    return out, snap


def trending(tokens):
    data = get_json("https://api.coingecko.com/api/v3/search/trending") or {}
    coins = data.get("coins") or []
    out = []
    for rank, row in enumerate(coins, 1):
        item = row.get("item") or {}
        sym = str(item.get("symbol") or "").upper()
        for t in tokens:
            if sym == str(t.get("symbol") or "").upper():
                out.append(event(t, "search_discovery", "coingecko_trending_rank", 1, max(35, 100 - rank * 7), 72, "CoinGecko Trending", url="https://www.coingecko.com/", cid=f"coingecko-trending:{identity(t)[3]}:{datetime.now(timezone.utc).date()}", extra={"rank": rank}))
    return out


def honeypot(t):
    chain, contract, _, _ = identity(t)
    if chain not in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon"}:
        return []
    d = get_json("https://api.honeypot.is/v2/IsHoneypot?address=" + contract)
    if not d:
        return []
    out = []
    hp = (d.get("honeypotResult") or {}).get("isHoneypot")
    sim = d.get("simulationResult") or {}
    bt = num(sim.get("buyTax"))
    st = num(sim.get("sellTax"))
    if hp is True:
        out.append(event(t, "supply_tokenomics", "honeypot_or_transfer_block", -1, 100, 95, "Honeypot.is", extra={"hard_risk": True}))
    tax = max([x for x in (bt, st) if x is not None], default=None)
    if tax is not None and tax >= 15:
        out.append(event(t, "supply_tokenomics", "extreme_tax", -1, min(100, tax * 3), 90, "Honeypot.is", extra={"buy_tax": bt, "sell_tax": st, "hard_risk": tax >= 30}))
    return out


def github_collect(t, prev):
    repo = (t.get("free_intel") or {}).get("github_repo")
    if not repo:
        return [], {}
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Authorization": "Bearer " + token} if token else {}
    d = get_json("https://api.github.com/repos/" + repo, headers=headers)
    rel = get_json("https://api.github.com/repos/" + repo + "/releases/latest", headers=headers)
    if not d:
        return [], {}
    snap = {"pushed_at": d.get("pushed_at"), "updated_at": d.get("updated_at"), "release": (rel or {}).get("tag_name")}
    out = []
    if snap["pushed_at"] and snap["pushed_at"] != prev.get("pushed_at"):
        out.append(event(t, "developer_project", "repo_activity", 1, 45, 65, "GitHub", subject=repo, url="https://github.com/" + repo, cid=f"github-push:{identity(t)[3]}:{repo}:{snap['pushed_at']}"))
    if snap["release"] and snap["release"] != prev.get("release"):
        out.append(event(t, "developer_project", "github_release", 1, 65, 80, "GitHub", subject=snap["release"], url="https://github.com/" + repo + "/releases", cid=f"github-release:{identity(t)[3]}:{repo}:{snap['release']}"))
    return out, snap


def defillama(t, prev):
    slug = (t.get("free_intel") or {}).get("defillama_slug")
    if not slug:
        return [], {}
    d = get_json("https://api.llama.fi/protocol/" + slug)
    if not d:
        return [], {}
    tvl = num(d.get("tvl"))
    snap = {"tvl": tvl}
    out = []
    old = num(prev.get("tvl"))
    if tvl is not None and old and old > 0:
        change = (tvl - old) / old * 100
        if abs(change) >= 5:
            out.append(event(t, "fundamental_usage", "tvl_change", 1 if change > 0 else -1, min(100, abs(change) * 5), 80, "DefiLlama", url="https://defillama.com/protocol/" + slug, extra={"change_pct": round(change, 2), "contradicts_bullish": change < 0}))
    return out, snap


def main():
    cfg = json.loads(CFG.read_text())
    tokens = [t for t in (cfg.get("tokens") or []) if isinstance(t, dict) and all(identity(t)[:3])]
    state = json.loads(STATE.read_text()) if STATE.exists() else {"tokens": {}}
    old_events = (json.loads(EVENTS.read_text()).get("events") or []) if EVENTS.exists() else []
    fresh = []
    newstate = {"version": 2, "updated_at": now(), "tokens": {}}
    fresh += trending(tokens)

    for t in tokens:
        _, _, _, key = identity(t)
        p = state.get("tokens", {}).get(key, {})
        de, ds = ds_collect(t, p.get("dexscreener", {}))
        fresh += de
        fresh += honeypot(t)
        ge, gs = github_collect(t, p.get("github", {}))
        fresh += ge
        le, ls = defillama(t, p.get("defillama", {}))
        fresh += le
        newstate["tokens"][key] = {"dexscreener": ds, "github": gs, "defillama": ls, "observed_at": now()}
        time.sleep(0.15)

    cutoff = time.time() - 24 * 3600

    def recent(e):
        try:
            return datetime.fromisoformat(str(e.get("event_time")).replace("Z", "+00:00")).timestamp() >= cutoff
        except Exception:
            return False

    merged = [e for e in old_events if isinstance(e, dict) and recent(e)] + fresh
    ded = {}
    for e in merged:
        chain = chain_name(e.get("network") or e.get("chain"))
        contract = norm_addr(chain, e.get("contract") or e.get("token_address"))
        pair = norm_addr(chain, e.get("pair") or e.get("pair_address"))
        key = f"{chain}:{contract}:{pair}"
        ded[(key, e.get("canonical_event_id"), e.get("kind"))] = e

    EVENTS.write_text(json.dumps({"version": 3, "generated_at": now(), "identity_mode": "EXACT_CHAIN_CONTRACT_PAIR", "events": list(ded.values())}, indent=2, ensure_ascii=False) + "\n")
    STATE.write_text(json.dumps(newstate, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "OK", "tokens": len(tokens), "new_events": len(fresh), "retained_events": len(ded), "neutral_verified_snapshots": sum(1 for e in fresh if e.get("kind") == "verified_market_snapshot"), "free_only": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
