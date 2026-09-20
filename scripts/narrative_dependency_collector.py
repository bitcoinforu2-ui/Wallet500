from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/narrative-dependency-state.json"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def http_json(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "accept": "application/json",
            "user-agent": "Wallet500-NarrativeDependency/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def norm_chain(value):
    raw = str(value or "").strip().lower()
    return {"eth": "ethereum", "bnb": "bsc"}.get(raw, raw)


def norm_addr(chain, value):
    raw = str(value or "").strip()
    return raw.lower() if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"} else raw


def identity(t):
    chain = norm_chain(t.get("network") or t.get("chain"))
    contract = norm_addr(chain, t.get("contract") or t.get("token_address"))
    pair = norm_addr(chain, t.get("pair") or t.get("pair_address"))
    if not chain or not contract or not pair:
        return None
    return chain, contract, pair, f"{chain}:{contract}:{pair}"


def fnum(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def inum(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def pair_snapshot(pair):
    pc = pair.get("priceChange") or {}
    vol = pair.get("volume") or {}
    tx = pair.get("txns") or {}
    h1 = tx.get("h1") or {}
    return {
        "chain": str(pair.get("chainId") or "").lower(),
        "pair": pair.get("pairAddress") or "",
        "dex_id": pair.get("dexId") or "",
        "price": fnum(pair.get("priceUsd")),
        "liquidity": fnum((pair.get("liquidity") or {}).get("usd")),
        "change_m5": fnum(pc.get("m5")),
        "change_h1": fnum(pc.get("h1")),
        "change_h6": fnum(pc.get("h6")),
        "change_h24": fnum(pc.get("h24")),
        "volume_h1": fnum(vol.get("h1")),
        "volume_h6": fnum(vol.get("h6")),
        "volume_h24": fnum(vol.get("h24")),
        "buys_h1": inum(h1.get("buys")),
        "sells_h1": inum(h1.get("sells")),
        "url": pair.get("url") or "",
        "base": (pair.get("baseToken") or {}).get("address") or "",
        "quote": (pair.get("quoteToken") or {}).get("address") or "",
    }


def exact_pair_snapshot(t):
    i = identity(t)
    if not i:
        raise RuntimeError("TARGET_IDENTITY_MISSING")
    chain, contract, pair, _ = i
    url = f"https://api.dexscreener.com/latest/dex/pairs/{urllib.parse.quote(chain)}/{urllib.parse.quote(pair)}"
    data = http_json(url)
    rows = data.get("pairs") or ([data.get("pair")] if data.get("pair") else [])
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        snap = pair_snapshot(raw)
        base = norm_addr(chain, snap.get("base"))
        quote = norm_addr(chain, snap.get("quote"))
        if norm_addr(chain, snap.get("pair")) == pair and contract in {base, quote}:
            return snap
    raise RuntimeError("FOLLOWER_EXACT_PAIR_NOT_VERIFIED")


def best_dependency_pair(dep):
    chain = norm_chain(dep.get("network") or dep.get("chain"))
    contract = norm_addr(chain, dep.get("contract") or dep.get("token_address"))
    if not chain or not contract:
        raise RuntimeError("DEPENDENCY_IDENTITY_MISSING")
    url = f"https://api.dexscreener.com/latest/dex/tokens/{urllib.parse.quote(contract)}"
    data = http_json(url)
    candidates = []
    for raw in data.get("pairs") or []:
        if not isinstance(raw, dict) or str(raw.get("chainId") or "").lower() != chain:
            continue
        snap = pair_snapshot(raw)
        base = norm_addr(chain, snap.get("base"))
        quote = norm_addr(chain, snap.get("quote"))
        if contract not in {base, quote}:
            continue
        if snap["liquidity"] < fnum(dep.get("min_liquidity_usd"), 0):
            continue
        candidates.append(snap)
    if not candidates:
        raise RuntimeError("NO_VERIFIED_LIQUID_DEPENDENCY_PAIR")
    candidates.sort(key=lambda x: (x["liquidity"], x["volume_h24"]), reverse=True)
    return candidates[0]


def mk_event(t, family, kind, direction, strength, confidence, source, **extra):
    i = identity(t)
    if not i:
        raise RuntimeError("EVENT_TARGET_IDENTITY_MISSING")
    chain, contract, pair, key = i
    ts = now_iso()
    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")[:-1]
    event = {
        "symbol": str(t.get("symbol") or "").upper(),
        "network": chain,
        "contract": contract,
        "pair": pair,
        "identity_key": key,
        "family": family,
        "kind": kind,
        "direction": int(direction),
        "strength": round(max(0.0, min(100.0, fnum(strength))), 1),
        "confidence": round(max(0.0, min(100.0, fnum(confidence))), 1),
        "source": source,
        "event_time": ts,
        "observed_at": ts,
        "identity_verified": True,
        "identity_scope": "FOLLOWER_EXACT_PAIR_PLUS_VERIFIED_DEPENDENCY_CONTRACT",
        "narrative_dependency": True,
        "canonical_event_id": f"narrative:{key}:{kind}:{bucket}",
    }
    event.update(extra)
    return event


def evaluate_target(t, old_state):
    deps = [x for x in (t.get("narrative_dependencies") or []) if isinstance(x, dict)]
    if not deps:
        return [], None

    follower = exact_pair_snapshot(t)
    dep_rows = []
    errors = []
    for dep in deps:
        try:
            snap = best_dependency_pair(dep)
            h1_thr = fnum(dep.get("leader_h1_trigger_pct"), 5.0)
            h6_thr = fnum(dep.get("leader_h6_trigger_pct"), 12.0)
            negative_h1 = fnum(dep.get("leader_negative_h1_pct"), -6.0)
            positive = snap["change_h1"] >= h1_thr or snap["change_h6"] >= h6_thr
            negative = snap["change_h1"] <= negative_h1
            dep_rows.append({
                "symbol": str(dep.get("symbol") or "").upper(),
                "role": str(dep.get("role") or "RELATED"),
                "contract": dep.get("contract"),
                "positive": positive,
                "negative": negative,
                "threshold_h1": h1_thr,
                "threshold_h6": h6_thr,
                **snap,
            })
        except Exception as exc:
            errors.append({
                "symbol": str(dep.get("symbol") or "").upper(),
                "error": f"{type(exc).__name__}:{str(exc)[:120]}",
            })
        time.sleep(0.35)

    if not dep_rows:
        return [], {
            "observed_at": now_iso(),
            "follower": follower,
            "dependencies": [],
            "errors": errors,
        }

    positives = [x for x in dep_rows if x["positive"]]
    negatives = [x for x in dep_rows if x["negative"]]
    events = []

    if positives:
        strongest = max(positives, key=lambda x: max(x["change_h1"], x["change_h6"] / 2.0))
        leader_move = max(0.0, strongest["change_h1"], strongest["change_h6"] / 2.0)
        lag = leader_move - follower["change_h1"]
        follower_active = follower["volume_h1"] >= fnum(t.get("narrative_min_follower_volume_h1"), 5000)
        underextended = follower["change_h1"] <= fnum(t.get("narrative_follower_max_h1_pct_for_early"), 22.0)
        confidence = min(94.0, 68.0 + len(positives) * 8.0 + (6.0 if follower_active else 0.0))
        strength = min(100.0, 35.0 + leader_move * 2.2 + len(positives) * 8.0 + max(0.0, lag) * 0.8)
        events.append(mk_event(
            t,
            "attention_social",
            "narrative_leader_momentum",
            1,
            strength,
            confidence,
            "DexScreener verified narrative dependency graph",
            narrative_group=t.get("narrative_group"),
            positive_dependency_count=len(positives),
            dependency_count=len(dep_rows),
            leader_symbol=strongest["symbol"],
            leader_role=strongest["role"],
            leader_change_h1=round(strongest["change_h1"], 3),
            leader_change_h6=round(strongest["change_h6"], 3),
            leader_liquidity_usd=round(strongest["liquidity"], 2),
            follower_change_h1=round(follower["change_h1"], 3),
            follower_volume_h1=round(follower["volume_h1"], 2),
            relative_lag_pct=round(lag, 3),
            source_url=strongest.get("url") or "",
        ))
        if underextended and follower_active:
            events.append(mk_event(
                t,
                "attention_social",
                "narrative_rotation_early",
                1,
                min(100.0, strength + 8.0),
                min(96.0, confidence + 3.0),
                "Wallet500 narrative dependency graph",
                narrative_group=t.get("narrative_group"),
                positive_dependency_count=len(positives),
                leaders=[x["symbol"] for x in positives],
                follower_change_h1=round(follower["change_h1"], 3),
                follower_change_h6=round(follower["change_h6"], 3),
                follower_volume_h1=round(follower["volume_h1"], 2),
                follower_buys_h1=follower["buys_h1"],
                follower_sells_h1=follower["sells_h1"],
                relative_lag_pct=round(lag, 3),
            ))

    if len(negatives) >= max(1, len(dep_rows)) and not positives:
        worst = min(negatives, key=lambda x: x["change_h1"])
        events.append(mk_event(
            t,
            "attention_social",
            "narrative_dependency_breakdown",
            -1,
            min(100.0, 35.0 + abs(worst["change_h1"]) * 3.0),
            82,
            "DexScreener verified narrative dependency graph",
            narrative_group=t.get("narrative_group"),
            negative_dependencies=[x["symbol"] for x in negatives],
            leader_symbol=worst["symbol"],
            leader_change_h1=round(worst["change_h1"], 3),
            follower_change_h1=round(follower["change_h1"], 3),
            contradicts_bullish=True,
            source_url=worst.get("url") or "",
        ))

    snapshot = {
        "observed_at": now_iso(),
        "narrative_group": t.get("narrative_group"),
        "follower": follower,
        "dependencies": dep_rows,
        "errors": errors,
        "positive_dependencies": [x["symbol"] for x in positives],
        "negative_dependencies": [x["symbol"] for x in negatives],
        "event_kinds": [x["kind"] for x in events],
    }
    return events, snapshot


def merge_events(fresh):
    doc = load(EVENTS, {"version": 3, "events": []})
    ded = {}
    for e in [x for x in (doc.get("events") or []) if isinstance(x, dict)] + fresh:
        ded[(e.get("identity_key") or "", e.get("canonical_event_id") or "", e.get("kind") or "")] = e
    doc["version"] = max(3, int(doc.get("version") or 0))
    doc["generated_at"] = now_iso()
    doc["identity_mode"] = "EXACT_CHAIN_CONTRACT_PAIR"
    doc["events"] = list(ded.values())[-6000:]
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def main():
    cfg = load(CONFIG, {})
    state = load(STATE, {"version": 1, "tokens": {}})
    all_events = []
    reports = []
    for t in cfg.get("tokens") or []:
        if not isinstance(t, dict) or not t.get("narrative_dependencies"):
            continue
        i = identity(t)
        key = i[3] if i else str(t.get("symbol") or "UNKNOWN")
        try:
            events, snapshot = evaluate_target(t, (state.get("tokens") or {}).get(key) or {})
            all_events.extend(events)
            state.setdefault("tokens", {})[key] = snapshot or {"observed_at": now_iso()}
            reports.append({
                "symbol": str(t.get("symbol") or "").upper(),
                "identity_key": key,
                "events": [e["kind"] for e in events],
                "positive_dependencies": (snapshot or {}).get("positive_dependencies") or [],
                "negative_dependencies": (snapshot or {}).get("negative_dependencies") or [],
                "errors": (snapshot or {}).get("errors") or [],
            })
        except Exception as exc:
            reports.append({
                "symbol": str(t.get("symbol") or "").upper(),
                "identity_key": key,
                "events": [],
                "error": f"{type(exc).__name__}:{str(exc)[:180]}",
            })
    if all_events:
        merge_events(all_events)
    state["version"] = 1
    state["updated_at"] = now_iso()
    state["reports"] = reports
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    print("NARRATIVE_DEPENDENCY_INTELLIGENCE", json.dumps({"targets": len(reports), "events": len(all_events), "reports": reports}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
