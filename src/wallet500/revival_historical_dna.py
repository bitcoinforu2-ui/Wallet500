from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

DATA = Path("data")
SOURCE = DATA / "outcome-tracker.json"
OUT = DATA / "revival-historical-dna.json"
MODE = "RESEARCH_ONLY_REVIVAL_HISTORICAL_DNA_V1"
NETWORK = "solana"
MIN_LIQUIDITY_USD = 50_000.0
HORIZONS_MIN = (60, 180, 360, 1440)
EVENT_COOLDOWN_MIN = 180
MIN_SAMPLE_N = 25
MIN_UNIQUE_TOKENS = 10


def _load(path: Path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _f(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _dt(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _same(a, b) -> bool:
    return bool(a) and bool(b) and str(a).lower() == str(b).lower()


def _pct(cur, prev):
    c, p = _f(cur), _f(prev)
    if c is None or p is None or p <= 0:
        return None
    return ((c / p) - 1.0) * 100.0


def _ratio(cur, prev):
    c, p = _f(cur), _f(prev)
    if c is None or p is None or p <= 0:
        return None
    return c / p


def _quantile(values: list[float], q: float):
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def _point(raw: dict):
    at = _dt(raw.get("observed_at") or raw.get("at") or raw.get("timestamp"))
    price = _f(raw.get("price_usd"))
    liq = _f(raw.get("liquidity_usd"))
    if at is None or price is None or price <= 0 or liq is None or liq < 0:
        return None
    buys = _f(raw.get("buys_h1"), 0.0) or 0.0
    sells = _f(raw.get("sells_h1"), 0.0) or 0.0
    return {
        "at": at,
        "at_iso": at.isoformat(),
        "price": price,
        "liquidity": liq,
        "volume_h1": max(0.0, _f(raw.get("volume_h1"), 0.0) or 0.0),
        "buys_h1": max(0.0, buys),
        "sells_h1": max(0.0, sells),
        "txns_h1": max(0.0, buys + sells),
    }


def _history(token: dict) -> list[dict]:
    pair = token.get("entry_pair_address")
    discovered = _dt(token.get("first_seen") or token.get("tracking_started_at"))
    rows = []
    for raw in token.get("history") or []:
        if not isinstance(raw, dict) or not _same(raw.get("pair_address"), pair):
            continue
        p = _point(raw)
        if p is None or (discovered and p["at"] < discovered):
            continue
        rows.append(p)
    rows.sort(key=lambda x: x["at"])
    dedup = []
    seen = set()
    for p in rows:
        if p["at_iso"] in seen:
            continue
        seen.add(p["at_iso"])
        dedup.append(p)
    return dedup


def _archetypes(history: list[dict], i: int) -> tuple[list[str], dict]:
    if i < 1:
        return [], {}
    cur, prev = history[i], history[i - 1]
    liq_change = _pct(cur["liquidity"], prev["liquidity"])
    price_change = _pct(cur["price"], prev["price"])
    vol_ratio = _ratio(cur["volume_h1"], prev["volume_h1"])
    tx_ratio = _ratio(cur["txns_h1"], prev["txns_h1"])
    buy_sell = cur["buys_h1"] / max(1.0, cur["sells_h1"])
    persistent = False
    if i >= 2:
        p2 = history[i - 2]
        net = _pct(cur["liquidity"], p2["liquidity"])
        persistent = bool(
            net is not None
            and net >= 3
            and cur["liquidity"] >= prev["liquidity"] * 0.99
            and prev["liquidity"] >= p2["liquidity"] * 0.99
        )

    names: list[str] = []
    if liq_change is not None and price_change is not None:
        if liq_change >= 3 and -2 <= price_change < 3:
            names.append("LIQ_LEADS")
        if liq_change >= 3 and price_change >= 3:
            names.append("CO_MOVE_UP")
    if liq_change is not None and liq_change >= 2 and vol_ratio is not None and vol_ratio >= 1.5:
        names.append("LIQ_PLUS_VOLUME")
        if tx_ratio is not None and tx_ratio >= 1.3:
            names.append("LIQ_VOLUME_TX_STACK")
    if vol_ratio is not None and vol_ratio >= 2 and tx_ratio is not None and tx_ratio >= 1.5:
        names.append("VOLUME_TX_ACCEL")
    if vol_ratio is not None and vol_ratio >= 1.5 and buy_sell >= 1.25:
        names.append("BUY_PRESSURE_WITH_VOLUME")
    if persistent:
        names.append("PERSISTENT_LIQ_BUILD")
        if vol_ratio is not None and vol_ratio >= 1.5:
            names.append("PERSISTENT_LIQ_PLUS_VOLUME")

    features = {
        "liquidity_change_pct": None if liq_change is None else round(liq_change, 4),
        "price_change_pct": None if price_change is None else round(price_change, 4),
        "volume_h1_ratio": None if vol_ratio is None else round(vol_ratio, 4),
        "txns_h1_ratio": None if tx_ratio is None else round(tx_ratio, 4),
        "buy_sell_ratio": round(buy_sell, 4),
        "persistent_liquidity_build": persistent,
    }
    return names, features


def _forward(history: list[dict], i: int, horizon_min: int):
    start = history[i]
    target = start["at"] + timedelta(minutes=horizon_min)
    max_lag = timedelta(minutes=max(30, int(horizon_min * 0.35)))
    for p in history[i + 1 :]:
        if p["at"] < target:
            continue
        if p["at"] > target + max_lag:
            return None
        ret = _pct(p["price"], start["price"])
        if ret is None:
            return None
        return {
            "observed_at": p["at_iso"],
            "return_pct": ret,
            "liquidity_return_pct": _pct(p["liquidity"], start["liquidity"]),
        }
    return None


def _summary(returns: list[float], tokens: set[str]):
    n = len(returns)
    unique = len(tokens)
    status = "RESEARCH_READY" if n >= MIN_SAMPLE_N and unique >= MIN_UNIQUE_TOKENS else "INSUFFICIENT_SAMPLE"
    if not returns:
        return {
            "status": status,
            "sample_n": 0,
            "unique_tokens": unique,
            "median_return_pct": None,
            "p25_return_pct": None,
            "p75_return_pct": None,
            "hit_10pct_rate": None,
            "hit_25pct_rate": None,
            "hit_50pct_rate": None,
        }
    return {
        "status": status,
        "sample_n": n,
        "unique_tokens": unique,
        "median_return_pct": round(median(returns), 4),
        "p25_return_pct": round(_quantile(returns, 0.25), 4),
        "p75_return_pct": round(_quantile(returns, 0.75), 4),
        "hit_10pct_rate": round(100 * sum(r >= 10 for r in returns) / n, 2),
        "hit_25pct_rate": round(100 * sum(r >= 25 for r in returns) / n, 2),
        "hit_50pct_rate": round(100 * sum(r >= 50 for r in returns) / n, 2),
    }


def build(source: dict) -> dict:
    buckets: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    token_sets: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    event_counts = defaultdict(int)
    examples = []
    eligible_tokens = 0
    eligible_points = 0

    for token in (source.get("tokens") or {}).values():
        if not isinstance(token, dict) or str(token.get("chain") or "").lower() != NETWORK:
            continue
        pair = token.get("entry_pair_address")
        if not pair:
            continue
        hist = _history(token)
        if len(hist) < 3:
            continue
        token_id = str(token.get("token") or "")
        if not token_id:
            continue
        eligible_tokens += 1
        last_open: dict[str, datetime] = {}
        for i in range(1, len(hist)):
            cur = hist[i]
            if cur["liquidity"] < MIN_LIQUIDITY_USD:
                continue
            names, features = _archetypes(hist, i)
            if not names:
                continue
            eligible_points += 1
            for name in names:
                prev_open = last_open.get(name)
                if prev_open and (cur["at"] - prev_open).total_seconds() < EVENT_COOLDOWN_MIN * 60:
                    continue
                last_open[name] = cur["at"]
                event_counts[name] += 1
                outcomes = {}
                for horizon in HORIZONS_MIN:
                    out = _forward(hist, i, horizon)
                    if out is None:
                        continue
                    ret = out["return_pct"]
                    buckets[name][horizon].append(ret)
                    token_sets[name][horizon].add(token_id)
                    outcomes[f"{horizon}m"] = {
                        "return_pct": round(ret, 4),
                        "observed_at": out["observed_at"],
                    }
                if outcomes and len(examples) < 300:
                    examples.append(
                        {
                            "token": token_id,
                            "pair_address": pair,
                            "event_at": cur["at_iso"],
                            "archetype": name,
                            "features": features,
                            "outcomes": outcomes,
                        }
                    )

    archetypes = {}
    for name in sorted(event_counts):
        horizon_stats = {}
        for horizon in HORIZONS_MIN:
            horizon_stats[f"{horizon}m"] = _summary(buckets[name][horizon], token_sets[name][horizon])
        ready = [v for v in horizon_stats.values() if v.get("status") == "RESEARCH_READY"]
        archetypes[name] = {
            "events_detected": event_counts[name],
            "status": "RESEARCH_READY" if ready else "INSUFFICIENT_SAMPLE",
            "horizons": horizon_stats,
        }

    generated = datetime.now(timezone.utc).isoformat()
    return {
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": generated,
        "production_impact": "NONE",
        "no_hindsight": True,
        "source": "OUTCOME_TRACKER_EXACT_ENTRY_PAIR_HISTORY",
        "truth_contract": {
            "identity": "SOLANA_TOKEN_PLUS_LOCKED_ENTRY_PAIR_ONLY",
            "minimum_liquidity_usd_at_event": MIN_LIQUIDITY_USD,
            "feature_rule": "FEATURES_USE_ONLY CURRENT_AND_PREVIOUS OBSERVATIONS; FUTURE OBSERVATIONS ARE LABELS ONLY",
            "event_cooldown_minutes_per_token_archetype": EVENT_COOLDOWN_MIN,
            "research_ready_min_sample_n": MIN_SAMPLE_N,
            "research_ready_min_unique_tokens": MIN_UNIQUE_TOKENS,
            "promotion_rule": "NO_HYBRID_SCORE_EFFECT_WITHOUT_PROSPECTIVE_VALIDATION",
        },
        "counts": {
            "eligible_solana_tokens": eligible_tokens,
            "eligible_feature_points": eligible_points,
            "archetypes": len(archetypes),
            "research_ready_archetypes": sum(x.get("status") == "RESEARCH_READY" for x in archetypes.values()),
        },
        "archetypes": archetypes,
        "sample_events": examples,
    }


def run() -> dict:
    source = _load(SOURCE, {})
    if not isinstance(source, dict) or not isinstance(source.get("tokens"), dict):
        raise RuntimeError("REVIVAL_HISTORICAL_DNA_SOURCE_UNAVAILABLE")
    payload = build(source)
    DATA.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({"mode": payload["mode"], **payload["counts"], "production_impact": payload["production_impact"]}))


if __name__ == "__main__":
    main()
