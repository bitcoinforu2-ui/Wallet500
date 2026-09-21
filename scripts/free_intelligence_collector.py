from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import resilient_http
except ImportError:  # package import in pytest / module mode
    from scripts import resilient_http

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data/unified-watch-config.json"
DYNAMIC = ROOT / "data/unified-dynamic-candidates.json"
SPOT = ROOT / "data/spot-market-discovery.json"
BOOTSTRAP = ROOT / "data/new-chain-bootstrap-radar.json"
BUY_REGISTRY = ROOT / "data/buy-zone-close-watch-registry.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/free-intelligence-collector-state.json"
UA = "Wallet500-FreeIntel/2.1"
EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}
HONEYPOT_CHAIN_IDS = {
    "ethereum": 1,
    "bsc": 56,
    "base": 8453,
    "arbitrum": 42161,
    "optimism": 10,
    "polygon": 137,
}


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
    try:
        return resilient_http.request_json(
            url,
            headers=headers or {},
            timeout=timeout,
            attempts=4,
            cache_ttl=45,
            user_agent=UA,
        )
    except Exception:
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
    chain, contract, pair, identity_key = identity(t)
    data = get_json("https://api.dexscreener.com/latest/dex/tokens/" + contract)
    out = []
    if not data:
        return out, {}
    pairs = data.get("pairs") or []
    exact = next((p for p in pairs if chain_name(p.get("chainId")) == chain and same_addr(chain, p.get("pairAddress"), pair)), None)
    if not exact:
        return [event(t, "market_microstructure", "identity_mismatch", -1, 100, 95, "DexScreener", extra={"hard_risk": True, "identity_verified": False})], {}

    base = (exact.get("baseToken") or {}).get("address")
    if not same_addr(chain, base, contract):
        return [event(t, "market_microstructure", "price_source_mismatch", -1, 100, 98, "DexScreener", extra={"hard_risk": True, "identity_verified": False, "reason": "TRACKED_TOKEN_NOT_DEXSCREENER_BASE_TOKEN"})], {}

    liq = num((exact.get("liquidity") or {}).get("usd"))
    vol = num((exact.get("volume") or {}).get("h1"))
    tx = (exact.get("txns") or {}).get("h1") or {}
    buys = num(tx.get("buys"))
    sells = num(tx.get("sells"))
    price = num(exact.get("priceUsd"))
    snap = {"price": price, "liquidity": liq, "volume_h1": vol, "buys_h1": buys, "sells_h1": sells}

    out.append(event(t, "market_microstructure", "verified_market_snapshot", 0, 0, 100, "DexScreener", url=str(exact.get("url") or ""), cid=f"dexsnapshot:{identity_key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "price_usd": price, "liquidity_usd": liq, "volume_h1_usd": vol, "buys_h1": buys, "sells_h1": sells}))

    if buys is not None and sells is not None and buys + sells >= 20:
        ratio = (buys + 1) / (sells + 1)
        strength = min(100, abs(ratio - 1) * 90)
        if ratio >= 1.25:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", 1, strength, 82, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "value": ratio}))
        elif ratio <= 0.8:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", -1, strength, 82, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "value": ratio, "contradicts_bullish": True}))

    pv = num(prev.get("volume_h1"))
    pl = num(prev.get("liquidity"))
    if vol is not None and pv and pv > 0:
        multiple = vol / pv
        if multiple >= 1.5:
            out.append(event(t, "market_microstructure", "volume_acceleration", 1, min(100, (multiple - 1) * 55), 78, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "multiple": round(multiple, 3)}))
    if liq is not None and pl and pl > 0:
        change = (liq - pl) / pl * 100
        if change <= -20:
            out.append(event(t, "market_microstructure", "liquidity_change", -1, min(100, abs(change) * 2), 88, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "change_pct": round(change, 2), "contradicts_bullish": True, "hard_risk": change <= -45}))
        elif change >= 15:
            out.append(event(t, "market_microstructure", "liquidity_change", 1, min(100, change * 1.5), 80, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "change_pct": round(change, 2)}))
    return out, snap


def trending(tokens):
    eligible = []
    for t in tokens:
        cg_id = str(t.get("coingecko_id") or (t.get("free_intel") or {}).get("coingecko_id") or "").strip().lower()
        if cg_id:
            eligible.append((t, cg_id))
    if not eligible:
        return []
    data = get_json("https://api.coingecko.com/api/v3/search/trending") or {}
    coins = data.get("coins") or []
    out = []
    for rank, row in enumerate(coins, 1):
        item = row.get("item") or {}
        item_id = str(item.get("id") or "").strip().lower()
        for t, cg_id in eligible:
            if item_id == cg_id:
                out.append(event(t, "search_discovery", "coingecko_trending_rank", 1, max(35, 100 - rank * 7), 82, "CoinGecko Trending", url="https://www.coingecko.com/", cid=f"coingecko-trending:{identity(t)[3]}:{cg_id}:{datetime.now(timezone.utc).date()}", extra={"identity_verified": True, "identity_scope": "EXPLICIT_COINGECKO_ID_TO_CONFIGURED_EXACT_PAIR", "coingecko_id": cg_id, "rank": rank}))
    return out


def honeypot(t, prev=None, with_snapshot=False):
    """Require chain-specific, consecutive confirmation before a provider result becomes HARD_RISK."""
    chain, contract, _, _ = identity(t)
    chain_id = HONEYPOT_CHAIN_IDS.get(chain)
    empty = {"is_honeypot": None, "buy_tax": None, "sell_tax": None, "confirmed_hard_risk": False}
    if not chain_id or not contract:
        return ([], empty) if with_snapshot else []

    d = get_json(
        "https://api.honeypot.is/v2/IsHoneypot?address="
        + contract
        + "&chainID="
        + str(chain_id)
    )
    if not d:
        return ([], empty) if with_snapshot else []

    out = []
    hp = (d.get("honeypotResult") or {}).get("isHoneypot")
    sim = d.get("simulationResult") or {}
    bt = num(sim.get("buyTax"))
    st = num(sim.get("sellTax"))
    previous = prev if isinstance(prev, dict) else {}
    consecutive_honeypot = bool(hp is True and previous.get("is_honeypot") is True)

    if hp is True:
        kind = "honeypot_or_transfer_block" if consecutive_honeypot else "honeypot_or_transfer_block_unconfirmed"
        out.append(event(
            t,
            "supply_tokenomics",
            kind,
            -1,
            100 if consecutive_honeypot else 55,
            95 if consecutive_honeypot else 70,
            "Honeypot.is",
            extra={
                "identity_verified": True,
                "identity_scope": "EXACT_CONTRACT_CONFIGURED_PAIR_CONTEXT",
                "hard_risk": consecutive_honeypot,
                "security_confirmation": "CONSECUTIVE_PROVIDER_CONFIRMATION" if consecutive_honeypot else "FIRST_OBSERVATION_REQUIRES_RECHECK",
                "chain_id": chain_id,
            },
        ))

    tax = max([x for x in (bt, st) if x is not None], default=None)
    consecutive_extreme_tax = bool(
        tax is not None
        and tax >= 30
        and previous.get("extreme_tax") is True
    )
    if tax is not None and tax >= 15:
        out.append(event(
            t,
            "supply_tokenomics",
            "extreme_tax",
            -1,
            min(100, tax * 3),
            90,
            "Honeypot.is",
            extra={
                "identity_verified": True,
                "identity_scope": "EXACT_CONTRACT_CONFIGURED_PAIR_CONTEXT",
                "buy_tax": bt,
                "sell_tax": st,
                "hard_risk": consecutive_extreme_tax,
                "security_confirmation": "CONSECUTIVE_PROVIDER_CONFIRMATION" if consecutive_extreme_tax else "FIRST_OBSERVATION_REQUIRES_RECHECK",
                "chain_id": chain_id,
            },
        ))

    snap = {
        "observed_at": now(),
        "chain_id": chain_id,
        "is_honeypot": hp is True,
        "buy_tax": bt,
        "sell_tax": st,
        "extreme_tax": bool(tax is not None and tax >= 30),
        "confirmed_hard_risk": bool(consecutive_honeypot or consecutive_extreme_tax),
    }
    return (out, snap) if with_snapshot else out


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
        out.append(event(t, "developer_project", "repo_activity", 1, 45, 65, "GitHub", subject=repo, url="https://github.com/" + repo, cid=f"github-push:{identity(t)[3]}:{repo}:{snap['pushed_at']}", extra={"identity_verified": True, "identity_scope": "EXPLICIT_CONFIG_PROJECT_MAPPING"}))
    if snap["release"] and snap["release"] != prev.get("release"):
        out.append(event(t, "developer_project", "github_release", 1, 65, 80, "GitHub", subject=snap["release"], url="https://github.com/" + repo + "/releases", cid=f"github-release:{identity(t)[3]}:{repo}:{snap['release']}", extra={"identity_verified": True, "identity_scope": "EXPLICIT_CONFIG_PROJECT_MAPPING"}))
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
            out.append(event(t, "fundamental_usage", "tvl_change", 1 if change > 0 else -1, min(100, abs(change) * 5), 80, "DefiLlama", url="https://defillama.com/protocol/" + slug, extra={"identity_verified": True, "identity_scope": "EXPLICIT_CONFIG_PROTOCOL_MAPPING", "change_pct": round(change, 2), "contradicts_bullish": change < 0}))
    return out, snap


def targets():
    cfg = json.loads(CFG.read_text())
    try:
        dyn = json.loads(DYNAMIC.read_text()) if DYNAMIC.exists() else {"candidates": []}
    except Exception:
        dyn = {"candidates": []}
    try:
        spot = json.loads(SPOT.read_text()) if SPOT.exists() else {"candidates": []}
    except Exception:
        spot = {"candidates": []}
    try:
        registry = json.loads(BUY_REGISTRY.read_text()) if BUY_REGISTRY.exists() else {"entries": {}}
    except Exception:
        registry = {"entries": {}}
    try:
        bootstrap = json.loads(BOOTSTRAP.read_text()) if BOOTSTRAP.exists() else {"candidates": []}
    except Exception:
        bootstrap = {"candidates": []}

    # Read the durable BUY registry directly so a newly persisted BUY gets full
    # intelligence in this same workflow even before the dynamic bridge refresh.
    registry_entries = registry.get("entries") if isinstance(registry, dict) and isinstance(registry.get("entries"), dict) else {}
    registry_buy_targets = [
        t for t in registry_entries.values()
        if isinstance(t, dict) and t.get("active") is True
    ]
    dynamic_buy_targets = [
        t for t in (dyn.get("candidates") or [])
        if isinstance(t, dict) and str(t.get("candidate_type") or "").upper() == "BUY_ZONE"
    ]
    bootstrap_targets = [
        t for t in (bootstrap.get("candidates") or [])
        if isinstance(t, dict) and t.get("bootstrap_actionable_watch") is True
    ]
    # Same-run CEX movers must receive fresh microstructure/security intelligence.
    # Reading Spot Discovery directly avoids the one-workflow lag caused by the
    # dynamic bridge running later in the pipeline.
    spot_hot_targets = []
    for t in (spot.get("resolved_candidates") or []):
        if not isinstance(t, dict):
            continue
        momentum = num(t.get("discovery_momentum_change_pct") or t.get("change_24h_pct")) or 0.0
        gain = num(t.get("gain_from_first_seen_pct")) or 0.0
        rank = int(num(t.get("positive_gainer_rank")) or 999999)
        turnover = num(t.get("quote_volume_24h_usd")) or 0.0
        if momentum >= 25.0 or gain >= 25.0 or (rank <= 15 and turnover >= 20000.0):
            spot_hot_targets.append(t)

    raw_targets = (
        registry_buy_targets
        + dynamic_buy_targets
        + spot_hot_targets
        + bootstrap_targets
        + [t for t in (cfg.get("tokens") or []) if isinstance(t, dict)]
    )
    tokens = []
    seen = set()
    for t in raw_targets:
        if not isinstance(t, dict) or not all(identity(t)[:3]):
            continue
        key = identity(t)[3]
        if key in seen:
            continue
        seen.add(key)
        tokens.append(t)
    return tokens


def main():
    tokens = targets()
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
        he, hs = honeypot(t, p.get("honeypot", {}), with_snapshot=True)
        fresh += he
        ge, gs = github_collect(t, p.get("github", {}))
        fresh += ge
        le, ls = defillama(t, p.get("defillama", {}))
        fresh += le
        newstate["tokens"][key] = {"dexscreener": ds, "honeypot": hs, "github": gs, "defillama": ls, "observed_at": now()}
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
