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
REAL_ALERTS = ROOT / "data/real-alerts.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/free-intelligence-collector-state.json"
UA = "Wallet500-FreeIntel/2.0"

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


def get_json(url: str, headers=None, timeout: int = 12):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    try:
        with urlopen(Request(url, headers=h), timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def event(t, family, kind, direction, strength, confidence, source, subject="", url="", cid="", extra=None):
    chain = network(t["network"])
    contract = addr(t["contract"], chain)
    pair = addr(t["pair"], chain)
    payload = {
        "symbol": t["symbol"],
        "network": chain,
        "contract": contract,
        "pair": pair,
        "family": family,
        "kind": kind,
        "direction": direction,
        "strength": round(max(0, min(100, strength)), 1),
        "confidence": round(max(0, min(100, confidence)), 1),
        "source": source,
        "source_url": url,
        "subject": subject,
        "canonical_event_id": cid or f"{source}:{chain}:{contract}:{pair}:{kind}",
        "event_time": now(),
        "observed_at": now(),
        "free_source": True,
        "exact_identity_bound": True,
        "production_independent": True,
    }
    if extra:
        payload.update(extra)
    return payload


def _canonical_targets() -> list[dict]:
    if not REAL_ALERTS.exists():
        return []
    try:
        payload = json.loads(REAL_ALERTS.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = []
    for name in ("alerts", "pre_wave_alerts"):
        rows.extend(row for row in (payload.get(name) or []) if isinstance(row, dict))
    out = []
    for row in rows:
        if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
            continue
        chain = network(row.get("chain") or row.get("network"))
        contract = addr(row.get("token_address") or row.get("token") or row.get("mint"), chain)
        pair = addr(row.get("pair_address"), chain)
        symbol = str(row.get("symbol") or row.get("name") or "").strip().upper()
        if not chain or not contract or not pair or not symbol:
            continue
        out.append(
            {
                "symbol": symbol,
                "network": chain,
                "contract": contract,
                "pair": pair,
                "dex_url": row.get("dex_url") or row.get("url"),
                "production_dynamic_target": True,
                "derivatives_intelligence": True,
            }
        )
    return out


def targets(cfg: dict) -> list[dict]:
    # Static close-watch targets remain, but every canonical exact-pair REAL/PRE-WAVE
    # row is automatically pulled into the collectors. This closes the gap where
    # LSK/other production alerts were never present in unified-watch-config.json.
    merged: dict[str, dict] = {}
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
        # Prefer static configuration metadata (GitHub repo, DefiLlama slug, wallet
        # mappings) while still allowing a dynamic production target to be added.
        if key in merged:
            existing = merged[key]
            dynamic = existing.get("production_dynamic_target") is True
            if dynamic and t.get("production_dynamic_target") is not True:
                merged[key] = {**existing, **t}
            else:
                merged[key] = {**t, **existing}
        else:
            merged[key] = t
    return list(merged.values())


def ds_collect(t: dict, prev: dict):
    data = get_json("https://api.dexscreener.com/latest/dex/tokens/" + t["contract"])
    out = []
    if not data:
        return out, {}
    target_chain = network(t["network"])
    target_pair = addr(t["pair"], target_chain)
    exact = None
    for row in data.get("pairs") or []:
        candidate_chain = network(row.get("chainId"))
        candidate_pair = addr(row.get("pairAddress"), candidate_chain)
        if candidate_chain == target_chain and candidate_pair == target_pair:
            exact = row
            break
    if exact is None:
        return [event(t, "market_microstructure", "identity_mismatch", -1, 100, 95, "DexScreener", extra={"hard_risk": True})], {}

    token_addresses = {
        addr((exact.get("baseToken") or {}).get("address"), target_chain),
        addr((exact.get("quoteToken") or {}).get("address"), target_chain),
    }
    if addr(t["contract"], target_chain) not in token_addresses:
        return [event(t, "market_microstructure", "identity_mismatch", -1, 100, 99, "DexScreener", extra={"hard_risk": True, "reason": "PAIR_DOES_NOT_CONTAIN_TARGET_CONTRACT"})], {}

    liquidity = num((exact.get("liquidity") or {}).get("usd"))
    volume = num((exact.get("volume") or {}).get("h1"))
    tx = (exact.get("txns") or {}).get("h1") or {}
    buys = num(tx.get("buys"))
    sells = num(tx.get("sells"))
    price = num(exact.get("priceUsd"))
    snap = {"price": price, "liquidity": liquidity, "volume_h1": volume, "buys_h1": buys, "sells_h1": sells}

    if buys is not None and sells is not None and buys + sells >= 20:
        ratio = (buys + 1) / (sells + 1)
        strength = min(100, abs(ratio - 1) * 90)
        if ratio >= 1.25:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", 1, strength, 82, "DexScreener", extra={"value": ratio}))
        elif ratio <= 0.8:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", -1, strength, 82, "DexScreener", extra={"value": ratio, "contradicts_bullish": True}))

    previous_volume = num(prev.get("volume_h1"))
    previous_liquidity = num(prev.get("liquidity"))
    if volume is not None and previous_volume and previous_volume > 0:
        multiple = volume / previous_volume
        if multiple >= 1.5:
            out.append(event(t, "market_microstructure", "volume_acceleration", 1, min(100, (multiple - 1) * 55), 78, "DexScreener", extra={"multiple": round(multiple, 3)}))
    if liquidity is not None and previous_liquidity and previous_liquidity > 0:
        change = (liquidity - previous_liquidity) / previous_liquidity * 100
        if change <= -20:
            out.append(event(t, "market_microstructure", "liquidity_change", -1, min(100, abs(change) * 2), 88, "DexScreener", extra={"change_pct": round(change, 2), "contradicts_bullish": True, "hard_risk": change <= -45}))
        elif change >= 15:
            out.append(event(t, "market_microstructure", "liquidity_change", 1, min(100, change * 1.5), 80, "DexScreener", extra={"change_pct": round(change, 2)}))
    return out, snap


def trending(all_targets: list[dict]):
    data = get_json("https://api.coingecko.com/api/v3/search/trending") or {}
    coins = data.get("coins") or []
    out = []
    for rank, row in enumerate(coins, 1):
        item = row.get("item") or {}
        symbol = str(item.get("symbol") or "").upper()
        for t in all_targets:
            if symbol != t["symbol"].upper():
                continue
            out.append(
                event(
                    t,
                    "search_discovery",
                    "coingecko_trending_rank",
                    1,
                    max(35, 100 - rank * 7),
                    60,
                    "CoinGecko Trending",
                    url="https://www.coingecko.com/",
                    cid=f"coingecko-trending:{t['symbol']}:{datetime.now(timezone.utc).date()}",
                    extra={
                        "rank": rank,
                        "identity_scope": "SYMBOL_ONLY_ATTENTION_SIGNAL",
                        "production_independent": False,
                    },
                )
            )
    return out


def honeypot(t: dict):
    if network(t["network"]) not in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon"}:
        return []
    data = get_json("https://api.honeypot.is/v2/IsHoneypot?address=" + t["contract"])
    if not data:
        return []
    out = []
    is_honeypot = (data.get("honeypotResult") or {}).get("isHoneypot")
    simulation = data.get("simulationResult") or {}
    buy_tax = num(simulation.get("buyTax"))
    sell_tax = num(simulation.get("sellTax"))
    if is_honeypot is True:
        out.append(event(t, "supply_tokenomics", "honeypot_or_transfer_block", -1, 100, 95, "Honeypot.is", extra={"hard_risk": True}))
    tax = max([x for x in (buy_tax, sell_tax) if x is not None], default=None)
    if tax is not None and tax >= 15:
        out.append(event(t, "supply_tokenomics", "extreme_tax", -1, min(100, tax * 3), 90, "Honeypot.is", extra={"buy_tax": buy_tax, "sell_tax": sell_tax, "hard_risk": tax >= 30}))
    return out


def github_collect(t: dict, prev: dict):
    repo = (t.get("free_intel") or {}).get("github_repo")
    if not repo:
        return [], {}
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Authorization": "Bearer " + token} if token else {}
    data = get_json("https://api.github.com/repos/" + repo, headers=headers)
    release = get_json("https://api.github.com/repos/" + repo + "/releases/latest", headers=headers)
    if not data:
        return [], {}
    snap = {"pushed_at": data.get("pushed_at"), "updated_at": data.get("updated_at"), "release": (release or {}).get("tag_name")}
    out = []
    if snap["pushed_at"] and snap["pushed_at"] != prev.get("pushed_at"):
        out.append(event(t, "developer_project", "repo_activity", 1, 45, 65, "GitHub", subject=repo, url="https://github.com/" + repo, cid=f"github-push:{repo}:{snap['pushed_at']}"))
    if snap["release"] and snap["release"] != prev.get("release"):
        out.append(event(t, "developer_project", "github_release", 1, 65, 80, "GitHub", subject=snap["release"], url="https://github.com/" + repo + "/releases", cid=f"github-release:{repo}:{snap['release']}"))
    return out, snap


def defillama(t: dict, prev: dict):
    slug = (t.get("free_intel") or {}).get("defillama_slug")
    if not slug:
        return [], {}
    data = get_json("https://api.llama.fi/protocol/" + slug)
    if not data:
        return [], {}
    tvl = num(data.get("tvl"))
    snap = {"tvl": tvl}
    out = []
    old = num(prev.get("tvl"))
    if tvl is not None and old and old > 0:
        change = (tvl - old) / old * 100
        if abs(change) >= 5:
            out.append(event(t, "fundamental_usage", "tvl_change", 1 if change > 0 else -1, min(100, abs(change) * 5), 80, "DefiLlama", url="https://defillama.com/protocol/" + slug, extra={"change_pct": round(change, 2), "contradicts_bullish": change < 0}))
    return out, snap


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    all_targets = targets(cfg)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"tokens": {}}
    old_events = (json.loads(EVENTS.read_text(encoding="utf-8")).get("events") or []) if EVENTS.exists() else []
    fresh = []
    newstate = dict(state) if isinstance(state, dict) else {"tokens": {}}
    newstate["version"] = 2
    newstate["updated_at"] = now()
    newstate.setdefault("tokens", {})

    fresh += trending(all_targets)
    for t in all_targets:
        key = identity_key(t)
        previous = newstate["tokens"].get(key, {}) if key else {}
        dex_events, dex_snapshot = ds_collect(t, previous.get("dexscreener", {}))
        fresh += dex_events
        fresh += honeypot(t)
        github_events, github_snapshot = github_collect(t, previous.get("github", {}))
        fresh += github_events
        llama_events, llama_snapshot = defillama(t, previous.get("defillama", {}))
        fresh += llama_events
        if key:
            newstate["tokens"][key] = {
                "symbol": t["symbol"],
                "network": t["network"],
                "contract": t["contract"],
                "pair": t["pair"],
                "dexscreener": dex_snapshot,
                "github": github_snapshot,
                "defillama": llama_snapshot,
                "observed_at": now(),
            }
        time.sleep(0.15)

    cutoff = time.time() - 24 * 3600

    def recent(row):
        try:
            return datetime.fromisoformat(str(row.get("event_time")).replace("Z", "+00:00")).timestamp() >= cutoff
        except Exception:
            return False

    merged = [row for row in old_events if isinstance(row, dict) and recent(row)] + fresh
    deduped = {}
    for row in merged:
        chain = network(row.get("network") or row.get("chain"))
        contract = addr(row.get("contract") or row.get("token_address"), chain)
        pair = addr(row.get("pair") or row.get("pair_address"), chain)
        dedupe_key = (chain, contract, pair, row.get("canonical_event_id"), row.get("kind"))
        deduped[dedupe_key] = row

    EVENTS.write_text(json.dumps({"version": 3, "generated_at": now(), "events": list(deduped.values())}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    STATE.write_text(json.dumps(newstate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "tokens": len(all_targets), "dynamic_production_targets": sum(1 for t in all_targets if t.get("production_dynamic_target")), "new_events": len(fresh), "retained_events": len(deduped), "free_only": True, "exact_identity_bound": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
