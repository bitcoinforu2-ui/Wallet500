"""Wallet500 Global Listing Intelligence.

Unifies public pre-listing / launchpad discovery evidence into one forward-only
feed. A listing source is NEVER a production buy signal. Only candidates with a
usable on-chain contract are handed to Wallet500's existing deep-scan lane;
all normal liquidity, exact-pair, risk, holder/cluster and execution gates remain
mandatory.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("data")
RADAR = OUT / "global-listing-radar.json"
LEDGER = OUT / "global-listing-ledger.json"
WATCHLIST = OUT / "manual-watchlist.json"

UA = {"User-Agent": "Wallet500-GlobalListing/1.1", "Accept": "application/json,text/html,*/*"}
OFFICIAL_PAGES = [
    ("KRAKEN_LISTING_ROADMAP", "kraken", "https://www.kraken.com/listings"),
    ("COINBASE_LISTING_TRANSPARENCY", "coinbase", "https://www.coinbase.com/blog/increasing-transparency-for-new-asset-listings-on-coinbase"),
    ("BYBIT_NEW_LISTINGS", "bybit", "https://announcements.bybit.com/en/?category=new_crypto"),
    ("OKX_NEW_LISTINGS", "okx", "https://www.okx.com/help/section/announcements-new-listings"),
    ("KUCOIN_NEW_LISTINGS", "kucoin", "https://www.kucoin.com/announcement/new-listings"),
    ("BITGET_NEW_LISTINGS", "bitget", "https://www.bitget.com/support/sections/5955813039257"),
    ("GATE_NEW_LISTINGS", "gate", "https://www.gate.com/announcements/newlisted"),
    ("MEXC_NEW_LISTINGS", "mexc", "https://www.mexc.com/newlisting"),
]
MOONSHOT_BASE = "https://api.moonshot.cc"
MOONSHOT_VIEWS = ("new", "rising", "finalized")
EVM_CORE_CHAINS = ("ethereum", "bsc", "arbitrum", "base")
EVM_RE = re.compile(r"(?<![0-9A-Fa-f])0x[0-9A-Fa-f]{40}(?![0-9A-Fa-f])")
SOL_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
        ctype = (r.headers.get("content-type") or "").lower()
    if "json" in ctype or raw.lstrip().startswith(("{", "[")): return "json", json.loads(raw)
    return "html", raw


def _rows(payload):
    if isinstance(payload, list): return payload
    if isinstance(payload, dict):
        for k in ("data", "tokens", "pairs", "items", "list"):
            if isinstance(payload.get(k), list): return payload[k]
            if isinstance(payload.get(k), dict):
                nested = _rows(payload[k])
                if nested: return nested
    return []


def _identity(row: dict):
    for k in ("mint", "tokenAddress", "address", "baseTokenAddress", "contractAddress", "pairAddress", "id"):
        if row.get(k): return str(row[k])
    return None


def _infer_chain(token: str) -> str | None:
    if not token: return None
    if EVM_RE.fullmatch(token):
        # An EVM address alone cannot distinguish Ethereum/BSC/Arbitrum/Base.
        # The deep scan tests every supported EVM core chain and retains only a
        # chain with a valid exact market identity.
        return "evm_unknown"
    if SOL_RE.fullmatch(token): return "solana"
    return None


def _extract_addresses(text: str):
    seen, out = set(), []
    for token in EVM_RE.findall(text or ""):
        key = token.lower()
        if key not in seen: seen.add(key); out.append(token)
    lower = (text or "").lower()
    for m in SOL_RE.finditer(text or ""):
        a, b = max(0, m.start()-100), min(len(text), m.end()+100)
        if not any(w in lower[a:b] for w in ("mint", "contract", "token", "address")): continue
        token = m.group(0)
        if token not in seen: seen.add(token); out.append(token)
    return out[:250]


def _moonshot(ts: str):
    observations, health = [], []
    for view in MOONSHOT_VIEWS:
        url = f"{MOONSHOT_BASE}/tokens/v1/{view}"
        try:
            _, payload = _get(url); rows = _rows(payload)
            health.append({"source":"moonshot","surface":view,"ok":True,"rows":len(rows)})
            for row in rows:
                if not isinstance(row, dict): continue
                token = _identity(row)
                if not token: continue
                observations.append({"observed_at":ts,"source":"moonshot","surface":f"MOONSHOT_{view.upper()}","stage":view.upper(),"token":token,"chain":_infer_chain(token),"raw":row,"source_url":url})
        except Exception as e:
            health.append({"source":"moonshot","surface":view,"ok":False,"rows":0,"error":f"{type(e).__name__}: {e}"[:300]})
    return observations, health


def _official_pages(ts: str):
    observations, health = [], []
    for surface, exchange, url in OFFICIAL_PAGES:
        try:
            kind, payload = _get(url)
            text = json.dumps(payload, ensure_ascii=False) if kind == "json" else payload
            addresses = _extract_addresses(text)
            health.append({"source":exchange,"surface":surface,"ok":True,"addresses_found":len(addresses),"format":kind})
            for token in addresses:
                observations.append({"observed_at":ts,"source":exchange,"surface":surface,"stage":"PRE_LISTING_OR_NEW_LISTING_PUBLIC_SURFACE","token":token,"chain":_infer_chain(token),"source_url":url})
        except Exception as e:
            health.append({"source":exchange,"surface":surface,"ok":False,"addresses_found":0,"error":f"{type(e).__name__}: {e}"[:300]})
    return observations, health


def _key(obs: dict) -> str:
    return hashlib.sha256(f"{obs.get('source')}|{obs.get('surface')}|{obs.get('token')}".encode()).hexdigest()[:24]


def _deep_scan_rows(observations):
    rows, seen = [], set()
    for o in observations:
        token, chain = o.get("token") or "", o.get("chain")
        if not token or not chain: continue
        chains = EVM_CORE_CHAINS if chain == "evm_unknown" else (chain,)
        for c in chains:
            k = f"{c}:{token.lower() if c in EVM_CORE_CHAINS else token}"
            if k in seen: continue
            seen.add(k)
            rows.append({"chain":c,"token":token,"source":"GLOBAL_LISTING_INTELLIGENCE","listing_source":o.get("source"),"listing_surface":o.get("surface"),"listing_first_observed_at":o.get("observed_at"),"research_only_until_wallet500_gates_pass":True})
    return rows


def _merge_watchlist(auto_rows):
    current = _load(WATCHLIST, [])
    if not isinstance(current, list): current = []
    manual = [x for x in current if isinstance(x, dict) and x.get("source") != "GLOBAL_LISTING_INTELLIGENCE"]
    _write(WATCHLIST, manual + auto_rows[:500])
    return len(manual), min(len(auto_rows), 500)


def run():
    OUT.mkdir(parents=True, exist_ok=True); ts = _now()
    a, ah = _moonshot(ts); b, bh = _official_pages(ts); observations = a + b
    ledger = _load(LEDGER, {"version":1,"truth_label":"PUBLIC_LISTING_DISCOVERY_EVIDENCE_ONLY","records":{}})
    records = ledger.get("records") if isinstance(ledger.get("records"), dict) else {}; new_count = 0
    for o in observations:
        k = _key(o); rec = records.get(k)
        if rec is None: rec = {"first_seen_at":ts,"first_observation":o,"history":[]}; records[k] = rec; new_count += 1
        rec["last_seen_at"] = ts; rec["last_observation"] = o
        hist = rec.get("history") if isinstance(rec.get("history"), list) else []
        hist.append({"at":ts,"stage":o.get("stage"),"source":o.get("source"),"surface":o.get("surface")}); rec["history"] = hist[-200:]
    ledger.update({"version":1,"updated_at":ts,"truth_label":"PUBLIC_LISTING_DISCOVERY_EVIDENCE_ONLY","records":records,"policy":"Listing/roadmap/launchpad presence never bypasses Wallet500 production filters or constitutes a buy signal."})
    _write(LEDGER, ledger)
    deep_rows = _deep_scan_rows(observations); manual_count, auto_count = _merge_watchlist(deep_rows); health = ah + bh
    radar = {"version":1,"updated_at":ts,"mode":"GLOBAL_EXCHANGE_PRELISTING_DISCOVERY_FORWARD_ONLY","sources_requested":len(health),"sources_healthy":sum(1 for x in health if x.get("ok")),"observations":len(observations),"new_immutable_records":new_count,"deep_scan_candidates":auto_count,"manual_watchlist_preserved":manual_count,"source_health":health,"deep_scan_policy":["contract/mint identity required","symbol-only listing observations remain research only","EVM unknown-chain addresses are tested on Ethereum, BSC, Arbitrum and Base","existing Wallet500 liquidity >= $50K, exact-pair, survival, risk, holder/cluster and execution gates remain mandatory","no listing source may promote directly to Qualified/Live/Paper Truth"]}
    _write(RADAR, radar)
    print("GLOBAL LISTING INTELLIGENCE", json.dumps({k:radar[k] for k in ("sources_healthy","observations","new_immutable_records","deep_scan_candidates")}, separators=(",",":")))
    return radar


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
