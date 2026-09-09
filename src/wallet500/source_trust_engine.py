from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from urllib.parse import quote

from .waking_fallbacks import _get_json

DATA = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
STATE_PATH = DATA / "source-trust-state.json"
LATEST_PATH = DATA / "source-trust-latest.json"
HORIZONS = {"1h": 1.0, "6h": 6.0, "24h": 24.0, "7d": 168.0}
GRACE = {"1h": 2.0, "6h": 3.0, "24h": 8.0, "7d": 24.0}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _dt(v) -> datetime | None:
    try:
        raw = str(v or "").replace("Z", "+00:00")
        d = datetime.fromisoformat(raw)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _pct(entry: float | None, current: float | None) -> float | None:
    if not entry or current is None:
        return None
    return (current / entry - 1.0) * 100.0


def _clamp(v: float, lo=0.0, hi=100.0) -> float:
    return max(lo, min(hi, float(v)))


def _norm_source(v: object) -> str:
    s = str(v or "UNKNOWN").strip().lstrip("@").lower()
    aliases = {"cryptoyeezus": "CryptoYeezus", "cryptoyeezussss": "CryptoYeezus", "agentobsrh": "AgentOBSRH"}
    return aliases.get(s, str(v or "UNKNOWN").strip().lstrip("@"))


def _event_id(source: str, row: dict) -> str:
    return str(row.get("event_id") or row.get("post_id") or row.get("source_post_id") or row.get("url") or f"{source}:{row.get('published_at')}")


def _market(row: dict) -> dict:
    m = row.get("market_snapshot") or {}
    return m if isinstance(m, dict) else {}


def _identity_locked(row: dict) -> bool:
    m = _market(row)
    ev = str(m.get("identity_evidence") or "")
    return bool(row.get("pair_identity_locked") is True or m.get("pair_identity_locked") is True or ev.startswith("EXACT_"))


def _content_strength(row: dict) -> float:
    if row.get("intelligence_score") is not None:
        return _clamp(_f(row.get("intelligence_score"), 0))
    text = str(row.get("text") or "").lower()
    score = 10.0
    if any(x in text for x in ("buy", "bought", "entry", "bag", "ape", "position", "sell", "sold", "exit")):
        score += 35
    if any(x in text for x in ("because", "thesis", "reason", "conviction", "risk", "liquidity", "volume", "wallet", "flow")):
        score += 20
    if row.get("explicit_contract") or (_market(row).get("token_address")):
        score += 25
    if row.get("dex_links") or _market(row).get("pair_address"):
        score += 10
    return _clamp(score)


def _market_confirmation(row: dict) -> float:
    m = _market(row)
    liq = _f(m.get("liquidity_usd"), 0) or 0
    vol = _f(m.get("volume_h1_usd"), 0) or 0
    score = 25.0
    score += min(30.0, 30.0 * math.log10(max(liq, 1)) / math.log10(100000)) if liq > 0 else 0
    score += min(25.0, 25.0 * math.log10(max(vol, 1)) / math.log10(50000)) if vol > 0 else 0
    if _identity_locked(row):
        score += 20
    return _clamp(score)


def _token_key(row: dict) -> str | None:
    m = _market(row)
    addr = str(m.get("token_address") or row.get("explicit_contract") or "").strip().lower()
    if addr:
        return "ca:" + addr
    sym = str(row.get("symbol") or m.get("symbol") or "").strip().upper().lstrip("$")
    return "symbol:" + sym if sym else None


def _normalize_inputs() -> list[dict]:
    out: list[dict] = []
    agent = _load(DATA / "agentobs-intel-events.json", {})
    for row in (agent.get("events") or []) if isinstance(agent, dict) else []:
        if isinstance(row, dict):
            x = dict(row)
            x["source_name"] = _norm_source(row.get("source_account") or "AgentOBSRH")
            out.append(x)
    yeezus = _load(DATA / "cryptoyeezus-calls.json", {})
    for row in (yeezus.get("events") or []) if isinstance(yeezus, dict) else []:
        if isinstance(row, dict):
            x = dict(row)
            x["source_name"] = _norm_source(row.get("caller") or "CryptoYeezus")
            out.append(x)
    return out


def _independence_scores(rows: list[dict], window_minutes: int = 90) -> dict[str, float]:
    result: dict[str, float] = {}
    for i, row in enumerate(rows):
        source = row.get("source_name")
        key = _token_key(row)
        when = _dt(row.get("published_at"))
        eid = _event_id(str(source), row)
        if not key or not when:
            result[eid] = 100.0
            continue
        overlaps = 0
        for j, other in enumerate(rows):
            if i == j or other.get("source_name") == source or _token_key(other) != key:
                continue
            owhen = _dt(other.get("published_at"))
            if owhen and abs((when - owhen).total_seconds()) <= window_minutes * 60:
                overlaps += 1
        result[eid] = 100.0 if overlaps == 0 else max(55.0, 85.0 - 10.0 * (overlaps - 1))
    return result


def _pair_snapshot(call: dict) -> dict | None:
    pair = str(call.get("pair_address") or "").strip()
    chain = str(call.get("chain") or "").strip()
    if not pair or not chain:
        return None
    try:
        payload = _get_json(f"https://api.dexscreener.com/latest/dex/pairs/{quote(chain)}/{quote(pair)}")
        pairs = payload.get("pairs") or []
        if not pairs:
            return None
        p = pairs[0]
        if str(p.get("pairAddress") or "").lower() != pair.lower():
            return None
        return {
            "price_usd": _f(p.get("priceUsd")),
            "liquidity_usd": _f((p.get("liquidity") or {}).get("usd")),
            "observed_at": _iso(_now()),
        }
    except Exception:
        return None


def _initial_call(row: dict, independence: float) -> dict | None:
    m = _market(row)
    price = _f(m.get("price_usd"))
    pair = str(m.get("pair_address") or "").strip()
    chain = str(m.get("chain") or "").strip()
    published = row.get("published_at")
    if row.get("baseline_only") is True or not published or not price or not pair or not chain or not _identity_locked(row):
        return None
    source = str(row.get("source_name"))
    return {
        "id": _event_id(source, row),
        "source": source,
        "published_at": published,
        "token_key": _token_key(row),
        "symbol": row.get("symbol") or m.get("symbol"),
        "token_address": m.get("token_address") or row.get("explicit_contract"),
        "chain": chain,
        "pair_address": pair,
        "entry_price_usd": price,
        "entry_liquidity_usd": _f(m.get("liquidity_usd")),
        "content_strength": _content_strength(row),
        "market_confirmation": _market_confirmation(row),
        "independence": independence,
        "identity_locked": True,
        "horizons": {},
        "observations": [],
        "rug_flag": False,
        "max_gain_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "earlyness_hours_to_20pct": None,
    }


def _update_call(call: dict, now: datetime) -> None:
    snap = _pair_snapshot(call)
    if not snap or snap.get("price_usd") is None:
        return
    published = _dt(call.get("published_at"))
    if not published:
        return
    age_h = (now - published).total_seconds() / 3600.0
    ret = _pct(_f(call.get("entry_price_usd")), _f(snap.get("price_usd")))
    obs = {**snap, "age_hours": round(age_h, 3), "return_pct": ret}
    call.setdefault("observations", []).append(obs)
    call["observations"] = call["observations"][-200:]
    if ret is not None:
        call["max_gain_pct"] = max(_f(call.get("max_gain_pct"), ret), ret)
        call["max_drawdown_pct"] = min(_f(call.get("max_drawdown_pct"), ret), ret)
        if ret >= 20 and call.get("earlyness_hours_to_20pct") is None:
            call["earlyness_hours_to_20pct"] = round(age_h, 3)
    entry_liq = _f(call.get("entry_liquidity_usd"))
    cur_liq = _f(snap.get("liquidity_usd"))
    if entry_liq and cur_liq is not None and ret is not None and cur_liq <= entry_liq * 0.2 and ret <= -80:
        call["rug_flag"] = True
    horizons = call.setdefault("horizons", {})
    for name, target in HORIZONS.items():
        if name in horizons or age_h < target:
            continue
        if age_h <= target + GRACE[name]:
            horizons[name] = {"return_pct": ret, "price_usd": snap.get("price_usd"), "captured_at": snap.get("observed_at"), "age_hours": round(age_h, 3), "capture_mode": "FIRST_OBSERVED_IN_WINDOW"}
        else:
            horizons[name] = {"status": "MISSED_CAPTURE_WINDOW", "age_hours": round(age_h, 3)}


def _valid_returns(calls: list[dict], horizon: str) -> list[float]:
    vals = []
    for c in calls:
        h = (c.get("horizons") or {}).get(horizon) or {}
        v = _f(h.get("return_pct"))
        if v is not None:
            vals.append(v)
    return vals


def _source_card(source: str, calls: list[dict]) -> dict:
    r1, r6, r24, r7 = (_valid_returns(calls, h) for h in ("1h", "6h", "24h", "7d"))
    evaluable = len(r24)
    hit = (100.0 * sum(1 for x in r24 if x > 0) / evaluable) if evaluable else None
    rug_rate = 100.0 * sum(1 for c in calls if c.get("rug_flag")) / len(calls) if calls else 0.0
    identity_rate = 100.0 * sum(1 for c in calls if c.get("identity_locked")) / len(calls) if calls else 0.0
    early = [float(c["earlyness_hours_to_20pct"]) for c in calls if c.get("earlyness_hours_to_20pct") is not None]
    early_score = 50.0 if not early else _clamp(100 - median(early) * 5)
    perf = 50.0 if hit is None else _clamp(0.65 * hit + 0.35 * _clamp(50 + (median(r24) if r24 else 0) * 2))
    risk = _clamp(100 - rug_rate * 2 - max(0.0, -min((_f(c.get("max_drawdown_pct"), 0) for c in calls), default=0.0)) * 0.35)
    consistency = 50.0 if len(r24) < 2 else _clamp(100 - (max(r24) - min(r24)) * 0.4)
    raw = 0.40 * perf + 0.20 * risk + 0.15 * early_score + 0.15 * identity_rate + 0.10 * consistency
    confidence = min(1.0, evaluable / 30.0)
    trust = 50.0 * (1 - confidence) + raw * confidence
    return {
        "source": source,
        "calls": len(calls),
        "evaluable_24h_calls": evaluable,
        "sample_confidence": round(confidence, 4),
        "trust_score": round(trust, 2),
        "raw_model_score": round(raw, 2),
        "hit_rate_24h_pct": None if hit is None else round(hit, 2),
        "median_return_1h_pct": None if not r1 else round(median(r1), 2),
        "median_return_6h_pct": None if not r6 else round(median(r6), 2),
        "median_return_24h_pct": None if not r24 else round(median(r24), 2),
        "median_return_7d_pct": None if not r7 else round(median(r7), 2),
        "worst_observed_drawdown_pct": round(min((_f(c.get("max_drawdown_pct"), 0) for c in calls), default=0.0), 2),
        "rug_rate_pct": round(rug_rate, 2),
        "identity_lock_rate_pct": round(identity_rate, 2),
        "earlyness_score": round(early_score, 2),
        "model_components": {"performance": round(perf, 2), "risk": round(risk, 2), "earlyness": round(early_score, 2), "identity": round(identity_rate, 2), "consistency": round(consistency, 2)},
        "status": "LEARNING" if evaluable < 30 else "CALIBRATED",
    }


def run() -> dict:
    now = _now()
    rows = _normalize_inputs()
    indep = _independence_scores(rows)
    state = _load(STATE_PATH, {"version": 1, "calls": {}})
    calls = state.get("calls") if isinstance(state, dict) and isinstance(state.get("calls"), dict) else {}
    for row in rows:
        source = str(row.get("source_name"))
        eid = _event_id(source, row)
        if eid not in calls:
            call = _initial_call(row, indep.get(eid, 100.0))
            if call:
                calls[eid] = call
    for call in calls.values():
        _update_call(call, now)
    grouped: dict[str, list[dict]] = {}
    for call in calls.values():
        grouped.setdefault(str(call.get("source") or "UNKNOWN"), []).append(call)
    cards = {source: _source_card(source, group) for source, group in grouped.items()}
    impacts = []
    for call in calls.values():
        card = cards.get(str(call.get("source"))) or {"trust_score": 50.0}
        impact = (_f(call.get("content_strength"), 0) * _f(card.get("trust_score"), 50) * _f(call.get("market_confirmation"), 0) * _f(call.get("independence"), 100)) / 1_000_000.0
        impacts.append({"id": call.get("id"), "source": call.get("source"), "token_key": call.get("token_key"), "content_strength": call.get("content_strength"), "source_trust": card.get("trust_score"), "market_confirmation": call.get("market_confirmation"), "independence": call.get("independence"), "effective_social_impact": round(_clamp(impact), 2)})
    latest = {
        "version": 1,
        "mode": "WALLET500_SOURCE_TRUST_V1",
        "observed_at": _iso(now),
        "formula": "ContentStrength x SourceTrust x MarketConfirmation x Independence",
        "trust_model": {"performance": 0.40, "risk": 0.20, "earlyness": 0.15, "identity": 0.15, "consistency": 0.10, "prior": 50, "full_confidence_calls": 30},
        "horizon_capture_policy": "FIRST_OBSERVED_IN_WINDOW_ONLY; missed windows are never backfilled",
        "sources": cards,
        "recent_impacts": impacts[-100:],
        "production_trade_impact": "RESEARCH_WEIGHT_ONLY",
    }
    _write(STATE_PATH, {"version": 1, "updated_at": _iso(now), "calls": calls})
    _write(LATEST_PATH, latest)
    print(json.dumps(latest, ensure_ascii=False, indent=2))
    return latest


if __name__ == "__main__":
    run()
