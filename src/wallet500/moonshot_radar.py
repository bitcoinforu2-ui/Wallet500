"""Wallet500 Moonshot launchpad radar.

Research/discovery feed only. Never promotes a token to production by itself.
Uses Moonshot's public Data API and preserves first-seen state immutably.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("data/moonshot-radar.json")
LEDGER = Path("data/moonshot-discovery-ledger.json")
BASE = os.getenv("MOONSHOT_DATA_API", "https://api.moonshot.cc")
VIEWS = ("new", "rising", "finalized")


def now():
    return datetime.now(timezone.utc).isoformat()


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def rows(payload):
    if isinstance(payload, list): return payload
    if isinstance(payload, dict):
        for k in ("data", "tokens", "pairs", "items"):
            if isinstance(payload.get(k), list): return payload[k]
    return []


def identity(x):
    for k in ("mint", "tokenAddress", "address", "baseTokenAddress", "pairAddress", "id"):
        if x.get(k): return str(x[k])
    return None


def load_ledger():
    if not LEDGER.exists(): return {"truth_label":"MOONSHOT_DISCOVERY_RESEARCH_ONLY","records":{}}
    try: return json.loads(LEDGER.read_text())
    except Exception: return {"truth_label":"MOONSHOT_DISCOVERY_RESEARCH_ONLY","records":{}}


def main():
    ts = now(); ledger = load_ledger(); records = ledger.setdefault("records", {})
    snapshot = {"updated_at":ts,"mode":"RESEARCH_DISCOVERY_ONLY_NOT_BUY_SIGNAL","source":"Moonshot Data API","views":{},"errors":[]}
    for view in VIEWS:
        try:
            # Endpoint is configurable so API path changes fail visibly rather than fabricate data.
            payload = get_json(f"{BASE.rstrip('/')}/tokens/v1/{view}")
            found = rows(payload); snapshot["views"][view] = found
            for x in found:
                if not isinstance(x, dict): continue
                key = identity(x)
                if not key: continue
                rec = records.get(key)
                if rec is None:
                    rec = {"first_seen_at":ts,"first_seen_view":view,"identity":key,"first_snapshot":x,"history":[]}
                    records[key] = rec
                rec.setdefault("history", []).append({"at":ts,"view":view,"snapshot":x})
                rec["history"] = rec["history"][-200:]
                rec["last_seen_at"] = ts; rec["last_seen_view"] = view; rec["last_snapshot"] = x
        except Exception as e:
            snapshot["views"][view] = []
            snapshot["errors"].append({"view":view,"error":type(e).__name__+": "+str(e)[:300]})
    ledger["updated_at"] = ts
    ledger["truth_label"] = "MOONSHOT_DISCOVERY_RESEARCH_ONLY"
    ledger["important_limit"] = "Moonshot presence is discovery evidence only; Wallet500 production gates remain mandatory."
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False))
    print("MOONSHOT RADAR", {k:len(v) for k,v in snapshot["views"].items()}, "errors", len(snapshot["errors"]))

if __name__ == "__main__": main()
