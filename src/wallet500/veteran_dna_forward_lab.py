from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .revival_1000 import is_pegged_or_derivative_like, is_stable_like
from .revival_absorption_signal import exact_pair_for_coin, fetch_json

DATA = Path("data")
SOURCE = DATA / "revival-1000-latest.json"
LEDGER = DATA / "veteran-dna-forward-ledger.json"
SUMMARY = DATA / "veteran-dna-forward-summary.json"
MODE = "VETERAN_DNA_FORWARD_NO_HINDSIGHT_V1"
NETWORK = "solana"
MIN_AGE_DAYS = 180
LIQ_FLOOR = 50_000.0
WINNER_RETURN_24H = 25.0
CONTROL_RETURN_24H = 5.0
MAX_NEW_PER_RUN = 60
CHECKPOINTS = (("1h", 1.0), ("3h", 3.0), ("6h", 6.0), ("24h", 24.0))


def n(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def now_utc():
    return datetime.now(timezone.utc)


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def key(token, pair):
    return f"{NETWORK}:{str(token or '')}:{str(pair or '').lower()}"


def stable_order(k: str):
    return hashlib.sha256(k.encode()).hexdigest()


def eligible_coin(coin: dict) -> bool:
    if not isinstance(coin, dict):
        return False
    if coin.get("market_age_verified") is not True:
        return False
    if n(coin.get("market_age_min_days"), 0) < MIN_AGE_DAYS:
        return False
    if coin.get("dex_link_type") != "DEXSCREENER_VERIFIED_PAIR":
        return False
    if not str(coin.get("token_address") or "").strip() or not str(coin.get("dex_pair_address") or "").strip():
        return False
    if is_stable_like(coin) or is_pegged_or_derivative_like(coin):
        return False
    return True


def fetch_pair_map(coins: list[dict]):
    if not coins:
        return {}, []
    pair_map = {}
    failures = []
    for start in range(0, len(coins), 30):
        batch = coins[start:start + 30]
        addresses = [str(c.get("token_address")) for c in batch]
        try:
            rows = fetch_json("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(addresses), timeout=20)
            if not isinstance(rows, list):
                raise RuntimeError("DEX_BATCH_NOT_LIST")
        except Exception as e:
            failures.append({"start": start, "size": len(batch), "error": f"{type(e).__name__}: {e}"})
            continue
        for coin in batch:
            p = exact_pair_for_coin(coin, rows)
            if p:
                pair_map[str(coin.get("dex_pair_address") or "").lower()] = p
    return pair_map, failures


def pair_features(pair: dict):
    tx = pair.get("txns") or {}
    h1_tx = tx.get("h1") or {}
    vol = pair.get("volume") or {}
    changes = pair.get("priceChange") or {}
    liq = n((pair.get("liquidity") or {}).get("usd"), 0.0) or 0.0
    vol_h1 = n(vol.get("h1"), 0.0) or 0.0
    buys = int(n(h1_tx.get("buys"), 0) or 0)
    sells = int(n(h1_tx.get("sells"), 0) or 0)
    return {
        "price_usd": n(pair.get("priceUsd")),
        "liquidity_usd": round(liq, 2),
        "volume_h1_usd": round(vol_h1, 2),
        "volume_h24_usd": n(vol.get("h24")),
        "turnover_h1": round(vol_h1 / liq, 6) if liq > 0 else None,
        "buys_h1": buys,
        "sells_h1": sells,
        "buy_sell_ratio_h1": round(buys / max(1, sells), 6),
        "price_change_h1_pct": n(changes.get("h1")),
        "price_change_h6_pct": n(changes.get("h6")),
        "price_change_h24_pct": n(changes.get("h24")),
    }


def label_24h(ret):
    if ret is None:
        return None
    if ret >= WINNER_RETURN_24H:
        return "WINNER"
    if ret <= CONTROL_RETURN_24H:
        return "CONTROL"
    return "AMBIGUOUS"


def med(records, field):
    vals = [n((r.get("t0_features") or {}).get(field)) for r in records]
    vals = [x for x in vals if x is not None]
    return round(statistics.median(vals), 6) if vals else None


def summarize(records: dict):
    rows = list(records.values())
    winners = [r for r in rows if r.get("label_24h") == "WINNER"]
    controls = [r for r in rows if r.get("label_24h") == "CONTROL"]
    ambiguous = [r for r in rows if r.get("label_24h") == "AMBIGUOUS"]
    open_rows = [r for r in rows if r.get("label_24h") is None]
    fields = ("liquidity_usd", "volume_h1_usd", "turnover_h1", "buy_sell_ratio_h1", "buys_h1", "sells_h1")
    wm = {f: med(winners, f) for f in fields}
    cm = {f: med(controls, f) for f in fields}
    lifts = {
        f: round(wm[f] / cm[f], 6) if wm.get(f) is not None and cm.get(f) not in (None, 0) else None
        for f in fields
    }
    ready = len(winners) >= 20 and len(controls) >= 20
    return {
        "mode": MODE,
        "generated_at": now_utc().isoformat(),
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {
            "scope": "VETERAN_COINS_ONLY",
            "minimum_market_age_days": MIN_AGE_DAYS,
            "stable_wrapped_pegged_excluded": True,
            "exact_pair_required": True,
            "liquidity_floor_usd": LIQ_FLOOR,
            "immutable_t0": True,
            "no_hindsight": True,
            "winner_rule": f"exact-pair 24h return >= {WINNER_RETURN_24H}%",
            "control_rule": f"exact-pair 24h return <= {CONTROL_RETURN_24H}%",
            "production_threshold_promotion_requires": "AT_LEAST_20_WINNERS_AND_20_CONTROLS_PLUS_SEPARATE_PROSPECTIVE_VALIDATION",
        },
        "counts": {
            "records": len(rows),
            "open": len(open_rows),
            "winners": len(winners),
            "controls": len(controls),
            "ambiguous": len(ambiguous),
            "research_ready": ready,
        },
        "winner_t0_medians": wm,
        "control_t0_medians": cm,
        "winner_to_control_median_ratio": lifts,
        "status": "RESEARCH_READY_FOR_SEPARATION_ANALYSIS" if ready else "COLLECTING_VETERAN_FORWARD_SAMPLE",
    }


def main():
    src = load(SOURCE, {})
    if src.get("network") != NETWORK:
        raise SystemExit("VETERAN_DNA_FORWARD_WRONG_NETWORK")
    if src.get("production_portfolio_impact") != "NONE":
        raise SystemExit("VETERAN_DNA_FORWARD_UNSAFE_SOURCE")
    age_gate = src.get("age_gate") or {}
    if age_gate.get("status") != "ENFORCED_FAIL_CLOSED" or n(age_gate.get("minimum_market_age_days"), 0) < MIN_AGE_DAYS:
        raise SystemExit("VETERAN_DNA_FORWARD_AGE_GATE_NOT_ENFORCED")

    ledger = load(LEDGER, {"version": 1, "mode": MODE, "network": NETWORK, "records": {}})
    if ledger.get("mode") != MODE or ledger.get("network") != NETWORK:
        raise SystemExit("VETERAN_DNA_FORWARD_LEDGER_CONTRACT_INVALID")
    records = ledger.setdefault("records", {})
    now = now_utc()

    universe = [c for c in (src.get("coins") or []) if eligible_coin(c)]
    universe_by_key = {key(c.get("token_address"), c.get("dex_pair_address")): c for c in universe}

    due_keys = []
    for k, rec in records.items():
        t0 = parse_ts(rec.get("t0_at"))
        if not t0 or rec.get("label_24h") is not None:
            continue
        age_h = (now - t0).total_seconds() / 3600.0
        if any(age_h >= h and name not in (rec.get("checkpoints") or {}) for name, h in CHECKPOINTS):
            due_keys.append(k)

    unseen = [k for k in universe_by_key if k not in records]
    unseen.sort(key=stable_order)
    new_keys = unseen[:MAX_NEW_PER_RUN]

    fetch_coins = []
    for k in due_keys:
        rec = records[k]
        fetch_coins.append({
            "token_address": rec.get("token_address"),
            "dex_pair_address": rec.get("pair_address"),
            "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        })
    fetch_coins.extend(universe_by_key[k] for k in new_keys)

    dedup = {}
    for c in fetch_coins:
        dedup[key(c.get("token_address"), c.get("dex_pair_address"))] = c
    pair_map, failures = fetch_pair_map(list(dedup.values()))

    created = 0
    for k in new_keys:
        coin = universe_by_key[k]
        pair = pair_map.get(str(coin.get("dex_pair_address") or "").lower())
        if not pair:
            continue
        feat = pair_features(pair)
        if not feat.get("price_usd") or feat.get("liquidity_usd", 0) < LIQ_FLOOR:
            continue
        records[k] = {
            "network": NETWORK,
            "token_address": coin.get("token_address"),
            "pair_address": coin.get("dex_pair_address"),
            "symbol_at_t0": coin.get("symbol"),
            "t0_at": now.isoformat(),
            "t0_features": feat,
            "market_age_verified": True,
            "market_age_min_days_at_t0": coin.get("market_age_min_days"),
            "market_age_evidence_source": coin.get("market_age_evidence_source"),
            "checkpoints": {},
            "label_24h": None,
            "immutable_t0": True,
            "no_hindsight": True,
        }
        created += 1

    checkpoint_updates = 0
    for k in due_keys:
        rec = records.get(k)
        if not rec:
            continue
        pair = pair_map.get(str(rec.get("pair_address") or "").lower())
        if not pair:
            continue
        current = pair_features(pair)
        current_price = n(current.get("price_usd"))
        t0_price = n((rec.get("t0_features") or {}).get("price_usd"))
        t0 = parse_ts(rec.get("t0_at"))
        if not current_price or not t0_price or not t0:
            continue
        age_h = (now - t0).total_seconds() / 3600.0
        ret = ((current_price / t0_price) - 1.0) * 100.0
        cps = rec.setdefault("checkpoints", {})
        for name, h in CHECKPOINTS:
            if name in cps or age_h < h:
                continue
            cps[name] = {
                "observed_at": now.isoformat(),
                "observed_age_hours": round(age_h, 4),
                "price_usd": current_price,
                "return_pct": round(ret, 6),
                "liquidity_usd": current.get("liquidity_usd"),
                "turnover_h1": current.get("turnover_h1"),
                "buy_sell_ratio_h1": current.get("buy_sell_ratio_h1"),
            }
            checkpoint_updates += 1
        if "24h" in cps and rec.get("label_24h") is None:
            rec["label_24h"] = label_24h(n(cps["24h"].get("return_pct")))

    ledger.update({
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "updated_at": now.isoformat(),
        "records": records,
        "truth_contract": {
            "veteran_only": True,
            "minimum_market_age_days": MIN_AGE_DAYS,
            "stable_wrapped_pegged_excluded": True,
            "exact_pair_only": True,
            "immutable_t0": True,
            "no_hindsight": True,
            "production_change": False,
        },
        "last_run": {
            "eligible_universe": len(universe),
            "new_locked": created,
            "checkpoint_updates": checkpoint_updates,
            "pair_refresh_failures": failures,
        },
    })
    summary = summarize(records)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"new_locked": created, "checkpoint_updates": checkpoint_updates, **summary["counts"], "status": summary["status"]}, indent=2))


if __name__ == "__main__":
    main()
