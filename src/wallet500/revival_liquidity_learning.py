from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from urllib.parse import quote
from urllib.request import Request, urlopen

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-liquidity-learning-state.json"
LATEST = DATA / "revival-liquidity-learning.json"
MODE = "RESEARCH_ONLY_REVIVAL_LIQUIDITY_LEARNING_V1"
NETWORK = "solana"
BATCH_SIZE = 30
OBSERVATIONS_PER_TOKEN = 10
CHECKPOINTS_MIN = (30, 60, 180, 360, 1440)
BASE58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def n(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def looks_like_solana_address(value: object) -> bool:
    s = str(value or "").strip()
    return 32 <= len(s) <= 44 and all(ch in BASE58 for ch in s)


def pct_change(current, previous) -> float | None:
    cur, prev = n(current), n(previous)
    if cur < 0 or prev <= 0:
        return None
    return ((cur / prev) - 1.0) * 100.0


def liquidity_market_cap_pct(liquidity_usd, market_cap_usd) -> float | None:
    liq, mcap = n(liquidity_usd), n(market_cap_usd)
    if liq < 0 or mcap <= 0:
        return None
    return (liq / mcap) * 100.0


def ratio_bucket(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value < 0.5:
        return "LT_0_5PCT"
    if value < 2:
        return "0_5_TO_2PCT"
    if value < 5:
        return "2_TO_5PCT"
    if value < 10:
        return "5_TO_10PCT"
    return "GE_10PCT"


def classify_signal(liq_change_pct: float | None, price_change_pct: float | None) -> str:
    """Research labels only. Raw values remain authoritative; labels never affect production."""
    if liq_change_pct is None or price_change_pct is None:
        return "BUILDING_BASELINE"
    if liq_change_pct >= 5 and price_change_pct >= 5:
        return "CO_MOVE_STRONG"
    if liq_change_pct >= 5 and -2 <= price_change_pct < 5:
        return "LIQ_LEADS"
    if price_change_pct >= 5 and liq_change_pct < 2:
        return "PRICE_LEADS"
    if liq_change_pct <= -5 and price_change_pct <= -3:
        return "CO_MOVE_DOWN"
    if liq_change_pct <= -5:
        return "LIQ_DRAIN"
    return "NEUTRAL"


def fetch_json(url: str, timeout: int = 20):
    req = Request(url, headers={"User-Agent": "Wallet500/1.0"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def load_revival() -> dict:
    payload = load_json(REVIVAL, {})
    if payload.get("mode") != "RESEARCH_ONLY_REVIVAL_SOLANA_500_V4":
        raise RuntimeError("REVIVAL_TRUTH_CONTRACT_UNAVAILABLE")
    if payload.get("network") != NETWORK:
        raise RuntimeError("REVIVAL_NETWORK_NOT_SOLANA")
    return payload


def eligible_rows(payload: dict) -> list[dict]:
    rows = []
    for x in payload.get("coins") or []:
        if x.get("network") != NETWORK:
            continue
        if x.get("solana_only_platform_verified") is not True:
            continue
        if x.get("stablecoin_excluded") is not True or x.get("pegged_derivative_excluded") is not True:
            continue
        if x.get("dex_link_type") != "DEXSCREENER_VERIFIED_PAIR":
            continue
        token = str(x.get("token_address") or "")
        pair = str(x.get("dex_pair_address") or "")
        if not looks_like_solana_address(token) or not looks_like_solana_address(pair):
            continue
        rows.append(x)
    return rows


def fetch_exact_pairs(rows: list[dict]) -> dict[str, dict]:
    requested = {str(x["dex_pair_address"]).lower(): x for x in rows}
    pair_ids = list(requested)
    out: dict[str, dict] = {}
    for start in range(0, len(pair_ids), BATCH_SIZE):
        chunk = pair_ids[start:start + BATCH_SIZE]
        url = "https://api.dexscreener.com/latest/dex/pairs/solana/" + ",".join(quote(x) for x in chunk)
        try:
            payload = fetch_json(url)
        except Exception:
            continue
        for pair in payload.get("pairs") or []:
            pair_address = str(pair.get("pairAddress") or "").lower()
            source = requested.get(pair_address)
            if not source:
                continue
            token = str(source.get("token_address") or "")
            base = str((pair.get("baseToken") or {}).get("address") or "")
            # DexScreener priceUsd/marketCap describe the base token. Never use them
            # for a quote-token match because that would silently attach another asset's price.
            if base != token:
                continue
            price = n(pair.get("priceUsd"))
            liq = n((pair.get("liquidity") or {}).get("usd"))
            mcap = n(pair.get("marketCap"))
            if price <= 0 or liq < 0 or mcap <= 0:
                continue
            out[token] = {
                "token_address": token,
                "symbol": source.get("symbol"),
                "name": source.get("name"),
                "pair_address": str(pair.get("pairAddress") or ""),
                "price_usd": price,
                "liquidity_usd": liq,
                "market_cap_usd": mcap,
                "pair_volume_24h_usd": n((pair.get("volume") or {}).get("h24")),
                "revival_score": n(source.get("revival_score_verified")),
                "watch_status": source.get("watch_status"),
            }
        if start + BATCH_SIZE < len(pair_ids):
            time.sleep(0.08)
    return out


def choose_baseline(history: list[dict], now: datetime) -> dict | None:
    candidates = []
    for obs in history:
        ts = parse_iso(obs.get("at"))
        if not ts:
            continue
        age_min = (now - ts).total_seconds() / 60.0
        if 25 <= age_min <= 45:
            candidates.append((abs(age_min - 30), obs))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def build_observation(row: dict, at: str) -> dict:
    ratio = liquidity_market_cap_pct(row.get("liquidity_usd"), row.get("market_cap_usd"))
    return {
        "at": at,
        "pair_address": row.get("pair_address"),
        "price_usd": row.get("price_usd"),
        "liquidity_usd": row.get("liquidity_usd"),
        "market_cap_usd": row.get("market_cap_usd"),
        "liq_mcap_pct": None if ratio is None else round(ratio, 6),
    }


def event_return(entry: float, current: float) -> float | None:
    if entry <= 0 or current <= 0:
        return None
    return ((current / entry) - 1.0) * 100.0


def update_events(events: list[dict], current_by_token: dict[str, dict], now: datetime, at: str) -> None:
    for event in events:
        if event.get("completed"):
            continue
        row = current_by_token.get(str(event.get("token_address") or ""))
        if not row or row.get("pair_address") != event.get("pair_address"):
            continue
        started = parse_iso(event.get("event_at"))
        if not started:
            continue
        age_min = (now - started).total_seconds() / 60.0
        price_ret = event_return(n(event.get("entry_price_usd")), n(row.get("price_usd")))
        liq_ret = event_return(n(event.get("entry_liquidity_usd")), n(row.get("liquidity_usd")))
        current_ratio = liquidity_market_cap_pct(row.get("liquidity_usd"), row.get("market_cap_usd"))
        ratio_ret = event_return(n(event.get("entry_liq_mcap_pct")), n(current_ratio)) if current_ratio is not None else None
        if price_ret is not None:
            event["max_price_return_pct"] = round(max(n(event.get("max_price_return_pct"), price_ret), price_ret), 4)
            event["min_price_return_pct"] = round(min(n(event.get("min_price_return_pct"), price_ret), price_ret), 4)
        outcomes = event.setdefault("outcomes", {})
        for mins in CHECKPOINTS_MIN:
            key = f"{mins}m"
            if age_min >= mins and key not in outcomes:
                outcomes[key] = {
                    "observed_at": at,
                    "price_return_pct": None if price_ret is None else round(price_ret, 4),
                    "liquidity_return_pct": None if liq_ret is None else round(liq_ret, 4),
                    "liq_mcap_ratio_return_pct": None if ratio_ret is None else round(ratio_ret, 4),
                    "price_usd": row.get("price_usd"),
                    "liquidity_usd": row.get("liquidity_usd"),
                    "market_cap_usd": row.get("market_cap_usd"),
                }
        if age_min >= 1440 and "1440m" in outcomes:
            event["completed"] = True
            event["completed_at"] = at
            event["hit_10pct"] = n(event.get("max_price_return_pct")) >= 10
            event["hit_25pct"] = n(event.get("max_price_return_pct")) >= 25
            event["hit_50pct"] = n(event.get("max_price_return_pct")) >= 50


def can_open_event(state: dict, token: str, signal: str, now: datetime) -> bool:
    if signal not in {"LIQ_LEADS", "CO_MOVE_STRONG"}:
        return False
    last_signal = (state.get("last_signal") or {}).get(token)
    if last_signal == signal:
        return False
    last_event_at = ((state.get("last_event_at") or {}).get(token) or {}).get(signal)
    last_dt = parse_iso(last_event_at)
    if last_dt and (now - last_dt).total_seconds() < 3600:
        return False
    return True


def summarize_events(events: list[dict]) -> dict:
    result = {}
    for signal in ("LIQ_LEADS", "CO_MOVE_STRONG"):
        subset = [e for e in events if e.get("signal") == signal]
        completed = [e for e in subset if e.get("completed")]
        gains = [n(e.get("max_price_return_pct")) for e in completed]
        result[signal] = {
            "events": len(subset),
            "completed_24h": len(completed),
            "hit_10pct": sum(1 for e in completed if e.get("hit_10pct")),
            "hit_25pct": sum(1 for e in completed if e.get("hit_25pct")),
            "hit_50pct": sum(1 for e in completed if e.get("hit_50pct")),
            "hit_10pct_rate": round(100 * sum(1 for e in completed if e.get("hit_10pct")) / len(completed), 2) if completed else None,
            "hit_25pct_rate": round(100 * sum(1 for e in completed if e.get("hit_25pct")) / len(completed), 2) if completed else None,
            "hit_50pct_rate": round(100 * sum(1 for e in completed if e.get("hit_50pct")) / len(completed), 2) if completed else None,
            "median_max_price_return_pct": round(median(gains), 4) if gains else None,
        }
    return result


def run() -> dict:
    revival = load_revival()
    rows = eligible_rows(revival)
    live = fetch_exact_pairs(rows)
    now = datetime.now(timezone.utc)
    at = now.isoformat()
    state = load_json(STATE, {
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "observations": {},
        "last_signal": {},
        "last_event_at": {},
        "events": [],
    })
    observations = state.setdefault("observations", {})
    last_signal = state.setdefault("last_signal", {})
    last_event_at = state.setdefault("last_event_at", {})
    events = state.setdefault("events", [])
    current_signals = []
    bucket_counts: dict[str, dict] = {}

    for token, row in live.items():
        history = observations.setdefault(token, [])
        baseline = choose_baseline(history, now)
        obs = build_observation(row, at)
        liq_change = pct_change(row.get("liquidity_usd"), baseline.get("liquidity_usd")) if baseline else None
        price_change = pct_change(row.get("price_usd"), baseline.get("price_usd")) if baseline else None
        mcap_change = pct_change(row.get("market_cap_usd"), baseline.get("market_cap_usd")) if baseline else None
        ratio_now = obs.get("liq_mcap_pct")
        ratio_change = pct_change(ratio_now, baseline.get("liq_mcap_pct")) if baseline and ratio_now is not None else None
        signal = classify_signal(liq_change, price_change)
        bucket = ratio_bucket(ratio_now)
        b = bucket_counts.setdefault(bucket, {"count": 0, "liq_leads": 0, "co_move_strong": 0, "waking_market": 0})
        b["count"] += 1
        if signal == "LIQ_LEADS": b["liq_leads"] += 1
        if signal == "CO_MOVE_STRONG": b["co_move_strong"] += 1
        if row.get("watch_status") == "WAKING_MARKET_ONLY": b["waking_market"] += 1

        current = {
            **row,
            "observed_at": at,
            "baseline_at": baseline.get("at") if baseline else None,
            "liq_mcap_pct": ratio_now,
            "liq_mcap_bucket": bucket,
            "liquidity_change_30m_pct": None if liq_change is None else round(liq_change, 4),
            "price_change_30m_pct": None if price_change is None else round(price_change, 4),
            "market_cap_change_30m_pct": None if mcap_change is None else round(mcap_change, 4),
            "liq_mcap_ratio_change_30m_pct": None if ratio_change is None else round(ratio_change, 4),
            "research_signal": signal,
        }
        current_signals.append(current)

        if can_open_event(state, token, signal, now):
            event_id = f"{token}:{int(now.timestamp())}:{signal}"
            events.append({
                "event_id": event_id,
                "token_address": token,
                "symbol": row.get("symbol"),
                "pair_address": row.get("pair_address"),
                "signal": signal,
                "event_at": at,
                "baseline_at": baseline.get("at") if baseline else None,
                "entry_price_usd": row.get("price_usd"),
                "entry_liquidity_usd": row.get("liquidity_usd"),
                "entry_market_cap_usd": row.get("market_cap_usd"),
                "entry_liq_mcap_pct": ratio_now,
                "entry_liq_mcap_bucket": bucket,
                "liquidity_change_30m_pct": current["liquidity_change_30m_pct"],
                "price_change_30m_pct": current["price_change_30m_pct"],
                "market_cap_change_30m_pct": current["market_cap_change_30m_pct"],
                "liq_mcap_ratio_change_30m_pct": current["liq_mcap_ratio_change_30m_pct"],
                "revival_score_at_event": row.get("revival_score"),
                "watch_status_at_event": row.get("watch_status"),
                "max_price_return_pct": 0.0,
                "min_price_return_pct": 0.0,
                "outcomes": {},
                "completed": False,
                "production_impact": "NONE",
            })
            last_event_at.setdefault(token, {})[signal] = at

        last_signal[token] = signal
        history.append(obs)
        observations[token] = history[-OBSERVATIONS_PER_TOKEN:]

    update_events(events, live, now, at)
    state["last_updated_at"] = at
    state["source_revival_generated_at"] = revival.get("generated_at")
    state["production_impact"] = "NONE"

    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    priority = {"LIQ_LEADS": 0, "CO_MOVE_STRONG": 1, "PRICE_LEADS": 2, "LIQ_DRAIN": 3, "CO_MOVE_DOWN": 4, "NEUTRAL": 5, "BUILDING_BASELINE": 6}
    current_signals.sort(key=lambda x: (priority.get(x.get("research_signal"), 99), -n(x.get("liquidity_change_30m_pct"))))
    payload = {
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": at,
        "source_revival_generated_at": revival.get("generated_at"),
        "source": "DEXSCREENER_EXACT_PAIR_BASE_TOKEN_MARKS+REVIVAL_VERIFIED_PAIR_IDENTITY",
        "production_impact": "NONE",
        "no_hindsight": True,
        "truth_contract": {
            "pair_identity": "EXACT_REVIVAL_VERIFIED_PAIR_ONLY",
            "price_market_cap_identity": "TOKEN_MUST_BE_DEX_PAIR_BASE_TOKEN",
            "market_cap": "DEXSCREENER_MARKET_CAP_ONLY_NO_FDV_SUBSTITUTION",
            "baseline": "NEAREST_OBSERVATION_TO_30_MINUTES_WITHIN_25_TO_45_MINUTES",
            "event_outcomes": [f"{m}m" for m in CHECKPOINTS_MIN],
            "promotion_rule": "NO_SCORE_OR_PRE_ALPHA_EFFECT_UNTIL_PROSPECTIVE_EVENT_SAMPLE_PROVES_VALUE",
        },
        "counts": {
            "revival_exact_pairs": len(rows),
            "usable_base_token_live_marks": len(live),
            "liq_leads_now": sum(1 for x in current_signals if x["research_signal"] == "LIQ_LEADS"),
            "co_move_strong_now": sum(1 for x in current_signals if x["research_signal"] == "CO_MOVE_STRONG"),
            "price_leads_now": sum(1 for x in current_signals if x["research_signal"] == "PRICE_LEADS"),
            "events_total": len(events),
            "events_completed_24h": sum(1 for e in events if e.get("completed")),
        },
        "ratio_buckets": bucket_counts,
        "learning_summary": summarize_events(events),
        "current_signals": current_signals,
        "recent_events": events[-200:],
    }
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({"mode": payload["mode"], **payload["counts"], "production_impact": payload["production_impact"]}))


if __name__ == "__main__":
    main()
