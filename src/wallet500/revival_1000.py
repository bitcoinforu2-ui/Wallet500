from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

DATA = Path("data")
LATEST = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-1000-state.json"
MODE = "RESEARCH_ONLY_REVIVAL_1000_V1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, headers: dict | None = None, timeout: int = 25):
    req = Request(url, headers={"User-Agent": "Wallet500/1.0", **(headers or {})})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_coingecko() -> list[dict]:
    key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    headers = {"x-cg-demo-api-key": key} if key else {}
    out = []
    for page in range(1, 5):
        url = (
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
            f"&order=market_cap_desc&per_page=250&page={page}&sparkline=false"
            "&price_change_percentage=7d,30d"
        )
        batch = fetch_json(url, headers=headers)
        if not isinstance(batch, list):
            raise RuntimeError("CoinGecko response is not a list")
        out.extend(batch)
        time.sleep(1.2)
    rows = []
    for x in out[:1000]:
        ath = x.get("ath")
        price = x.get("current_price")
        dd = None
        if ath and price is not None and float(ath) > 0:
            dd = (1.0 - float(price) / float(ath)) * 100.0
        rows.append({
            "source": "coingecko",
            "id": x.get("id"),
            "symbol": str(x.get("symbol") or "").upper(),
            "name": x.get("name"),
            "market_cap_rank": x.get("market_cap_rank"),
            "market_cap_usd": x.get("market_cap"),
            "price_usd": price,
            "volume_24h_usd": x.get("total_volume"),
            "ath_usd": ath,
            "ath_date": x.get("ath_date"),
            "drawdown_from_ath_pct": dd,
            "change_24h_pct": x.get("price_change_percentage_24h"),
            "change_7d_pct": x.get("price_change_percentage_7d_in_currency"),
            "change_30d_pct": x.get("price_change_percentage_30d_in_currency"),
        })
    return rows


def fetch_coinpaprika() -> list[dict]:
    raw = fetch_json("https://api.coinpaprika.com/v1/tickers?quotes=USD&limit=1000")
    rows = []
    for x in raw[:1000]:
        q = (x.get("quotes") or {}).get("USD") or {}
        ath = q.get("ath_price")
        price = q.get("price")
        dd = None
        pf = q.get("percent_from_price_ath")
        if pf is not None:
            dd = abs(float(pf)) if float(pf) <= 0 else 0.0
        elif ath and price is not None and float(ath) > 0:
            dd = (1.0 - float(price) / float(ath)) * 100.0
        rows.append({
            "source": "coinpaprika",
            "id": x.get("id"),
            "symbol": str(x.get("symbol") or "").upper(),
            "name": x.get("name"),
            "market_cap_rank": x.get("rank"),
            "market_cap_usd": q.get("market_cap"),
            "price_usd": price,
            "volume_24h_usd": q.get("volume_24h"),
            "ath_usd": ath,
            "ath_date": q.get("ath_date"),
            "drawdown_from_ath_pct": dd,
            "change_24h_pct": q.get("percent_change_24h"),
            "change_7d_pct": q.get("percent_change_7d"),
            "change_30d_pct": q.get("percent_change_30d"),
        })
    return rows


def n(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def score_market_signals(x: dict) -> tuple[float, list[str]]:
    """Market-only watch score. Holder/fundamental evidence is intentionally excluded until verified."""
    s = 0.0
    reasons = []
    dd = n(x.get("drawdown_from_ath_pct"), -1)
    if 70 <= dd <= 95:
        s += 35
        reasons.append("DEEP_DRAWDOWN_70_95")
        if 78 <= dd <= 92:
            s += 5
            reasons.append("DRAWDOWN_CORE_BAND")
    mcap = max(n(x.get("market_cap_usd")), 0)
    vol = max(n(x.get("volume_24h_usd")), 0)
    turnover = vol / mcap if mcap > 0 else 0
    if turnover >= 0.03:
        s += 8; reasons.append("TURNOVER_GE_3PCT")
    if turnover >= 0.10:
        s += 8; reasons.append("TURNOVER_GE_10PCT")
    if turnover >= 0.25:
        s += 7; reasons.append("TURNOVER_GE_25PCT")
    c7, c30, c24 = n(x.get("change_7d_pct")), n(x.get("change_30d_pct")), n(x.get("change_24h_pct"))
    if 0 < c7 <= 25:
        s += 8; reasons.append("EARLY_7D_AWAKENING")
    if 0 < c30 <= 40:
        s += 7; reasons.append("EARLY_30D_AWAKENING")
    if 0 < c24 <= 15:
        s += 7; reasons.append("EARLY_24H_MOMENTUM")
    if vol >= 1_000_000:
        s += 5; reasons.append("VOLUME_GE_1M")
    if c24 >= 50:
        s -= 15; reasons.append("CHASE_RISK_24H_GE_50")
    if c24 >= 100:
        s -= 15; reasons.append("LATE_PARABOLIC_24H_GE_100")
    return max(0.0, min(100.0, s)), reasons


def load_state() -> dict:
    if not STATE.exists():
        return {"version": 1, "first_t0": now_iso(), "coins": {}}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"version": 1, "first_t0": now_iso(), "coins": {}}


def build(rows: list[dict], source: str, failures: list[dict]) -> dict:
    ts = now_iso()
    state = load_state()
    coins_state = state.setdefault("coins", {})
    normalized = []
    for i, x in enumerate(rows[:1000], 1):
        x["universe_rank"] = i
        x["market_cap_rank"] = x.get("market_cap_rank") or i
        x["dex_link"] = "https://dexscreener.com/search?q=" + quote(str(x.get("symbol") or x.get("id") or ""))
        x["dex_link_type"] = "SEARCH_ONLY_NOT_EXACT_PAIR"
        x["coingecko_link"] = "https://www.coingecko.com/en/coins/" + str(x.get("id") or "") if source == "coingecko" else None
        score, reasons = score_market_signals(x)
        x["watch_score_market_only"] = round(score, 2)
        x["watch_reasons"] = reasons
        dd = n(x.get("drawdown_from_ath_pct"), -1)
        core = 70 <= dd <= 95
        if core and score >= 65:
            status = "WAKING_MARKET_ONLY"
        elif core:
            status = "DEEP_WATCH"
        else:
            status = "OUTSIDE_CORE_DRAWDOWN_BAND"
        x["watch_status"] = status
        x["holder_growth_verified"] = None
        x["concentration_change_verified"] = None
        x["fundamental_evidence_verified"] = None
        x["pre_alpha_eligible"] = False
        x["pre_alpha_blocker"] = "HOLDER_AND_FUNDAMENTAL_EVIDENCE_NOT_YET_VERIFIED"
        key = str(x.get("id") or x.get("symbol") or i)
        st = coins_state.setdefault(key, {"first_seen_at": ts, "t0_price_usd": x.get("price_usd"), "t0_rank": i})
        x["t0"] = st
        normalized.append(x)
    state["last_updated_at"] = ts
    state["coins"] = coins_state
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    core_count = sum(1 for x in normalized if x["watch_status"] != "OUTSIDE_CORE_DRAWDOWN_BAND")
    waking = sum(1 for x in normalized if x["watch_status"] == "WAKING_MARKET_ONLY")
    return {
        "version": 1,
        "mode": MODE,
        "generated_at": ts,
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "universe_definition": "TOP_1000_BY_MARKET_CAP_MONITORED; CORE_RESEARCH_BAND_70_TO_95_PCT_BELOW_ATH",
        "source": source,
        "counts": {"universe": len(normalized), "core_drawdown_watch": core_count, "waking_market_only": waking, "pre_alpha": 0},
        "scoring_contract": {
            "market_score_max": 100,
            "holder_growth": "PENDING_VERIFIED_SOURCE",
            "concentration_decline": "PENDING_VERIFIED_SOURCE",
            "fundamentals_product_community": "PENDING_VERIFIED_SOURCE",
            "rule": "MISSING_EVIDENCE_NEVER_IMPUTED_AS_TRUE"
        },
        "failures": failures,
        "coins": normalized,
    }


def main() -> None:
    failures = []
    rows = []
    source = "NONE"
    for name, fn in (("coingecko", fetch_coingecko), ("coinpaprika", fetch_coinpaprika)):
        try:
            rows = fn()
            if len(rows) >= 100:
                source = name
                break
            raise RuntimeError(f"insufficient rows: {len(rows)}")
        except Exception as e:
            failures.append({"failure_code": "REVIVAL_UNIVERSE_SOURCE_FAILED", "source": name, "severity": "DEGRADED", "blocks_production": False, "actual": f"{type(e).__name__}: {e}", "diagnosed_at": now_iso()})
    if not rows:
        raise SystemExit("REVIVAL_1000_NO_MARKET_SOURCE")
    payload = build(rows, source, failures)
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"mode": MODE, "source": source, **payload["counts"], "failures": len(failures)}))


if __name__ == "__main__":
    main()
