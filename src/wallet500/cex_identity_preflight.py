from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DATA = Path("data")
MIN_MARKET_AGE_DAYS = 180
UA = {"User-Agent": "Wallet500/1.7", "Accept": "application/json"}

EXCHANGE_ALIASES = {
    "gate": {"gate.io", "gate"},
    "mexc": {"mexc"},
    "kucoin": {"kucoin"},
    "bitget": {"bitget"},
    "bingx": {"bingx"},
    "okx": {"okx"},
    "bybit": {"bybit"},
    "binance": {"binance"},
    "htx": {"htx", "huobi"},
    "coinex": {"coinex"},
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _headers() -> dict[str, str]:
    h = dict(UA)
    key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def _get_json(url: str, timeout: int = 25):
    req = Request(url, headers=_headers())
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cg_markets(params: dict) -> list[dict]:
    data = _get_json("https://api.coingecko.com/api/v3/coins/markets?" + urlencode(params, doseq=True))
    if not isinstance(data, list):
        raise RuntimeError("CoinGecko markets response is not a list")
    return data


def _fetch_by_symbols(symbols: list[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    clean = list(dict.fromkeys(str(x).strip().lower() for x in symbols if str(x).strip()))
    for start in range(0, len(clean), 45):
        batch = clean[start:start + 45]
        rows = _cg_markets({
            "vs_currency": "usd",
            "symbols": ",".join(batch),
            "include_tokens": "all",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false",
        })
        for row in rows:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym:
                grouped[sym].append(row)
    return grouped


def _base_symbol(symbol: object) -> str:
    s = str(symbol or "").strip().upper().replace("-", "").replace("_", "")
    if s.endswith("USDTM"):
        return s[:-5]
    if s.endswith("USDT"):
        return s[:-4]
    return s


def _parse_dt(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def _age_meta(row: dict, source: str) -> dict | None:
    now = now_utc()
    dates = [_parse_dt(row.get("ath_date")), _parse_dt(row.get("atl_date"))]
    dates = [x for x in dates if x is not None and x <= now]
    if not dates:
        return None
    evidence = min(dates)
    days = int((now - evidence).total_seconds() // 86400)
    if days < MIN_MARKET_AGE_DAYS:
        return None
    return {
        "market_age_verified": True,
        "market_age_min_days": days,
        "market_age_evidence_at": evidence.isoformat(),
        "market_age_evidence_source": source,
        "coingecko_id": row.get("id"),
    }


def _cex_reference_price(alert: dict) -> float | None:
    prices = []
    for row in alert.get("markets") or []:
        try:
            p = float(row.get("price") or 0)
        except (TypeError, ValueError):
            p = 0
        if p > 0:
            prices.append(p)
    if prices:
        return float(median(prices))
    for milestone in ("first_alert", "first_anomaly", "first_seen"):
        try:
            p = float(((alert.get("milestones") or {}).get(milestone) or {}).get("reference_price") or 0)
        except (TypeError, ValueError):
            p = 0
        if p > 0:
            return p
    return None


def _price_error(candidate: dict, ref_price: float | None) -> float | None:
    if not ref_price or ref_price <= 0:
        return None
    try:
        p = float(candidate.get("current_price") or 0)
    except (TypeError, ValueError):
        p = 0
    if p <= 0:
        return None
    return abs(math.log(p / ref_price))


def _ticker_overlap(coin_id: str, base: str, expected_exchanges: set[str]) -> int:
    try:
        data = _get_json(
            "https://api.coingecko.com/api/v3/coins/"
            + quote(coin_id, safe="")
            + "/tickers?include_exchange_logo=false&depth=false"
        )
    except Exception:
        return 0
    score = 0
    for t in (data or {}).get("tickers") or []:
        if str(t.get("base") or "").upper() != base:
            continue
        if str(t.get("target") or "").upper() not in {"USDT", "USDC", "USD"}:
            continue
        name = str(((t.get("market") or {}).get("name") or "")).strip().lower()
        ident = str(((t.get("market") or {}).get("identifier") or "")).strip().lower()
        text = name + " " + ident
        matched = False
        for exchange in expected_exchanges:
            aliases = EXCHANGE_ALIASES.get(exchange, {exchange})
            if any(alias in text for alias in aliases):
                matched = True
                break
        if matched:
            score += 1
    return score


def _resolve_ambiguous(alert: dict, base: str, matches: list[dict]) -> tuple[dict | None, dict]:
    ref = _cex_reference_price(alert)
    ranked = []
    for row in matches:
        err = _price_error(row, ref)
        ranked.append((999.0 if err is None else err, row))
    ranked.sort(key=lambda x: x[0])
    if ranked and ranked[0][0] <= math.log(1.08):
        second = ranked[1][0] if len(ranked) > 1 else 999.0
        if second > max(math.log(1.16), ranked[0][0] * 2.0):
            return ranked[0][1], {
                "method": "CEX_PRICE_COHERENCE",
                "reference_price": ref,
                "relative_log_error": round(ranked[0][0], 6),
                "candidate_count": len(matches),
            }

    expected = {str(x).lower() for x in (alert.get("exchanges") or []) if str(x).strip()}
    ticker_scores = []
    for row in matches:
        coin_id = str(row.get("id") or "").strip()
        overlap = _ticker_overlap(coin_id, base, expected) if coin_id else 0
        err = _price_error(row, ref)
        ticker_scores.append((overlap, -(999.0 if err is None else err), row))
    ticker_scores.sort(reverse=True, key=lambda x: (x[0], x[1]))
    if ticker_scores and ticker_scores[0][0] >= 1:
        best = ticker_scores[0]
        second_overlap = ticker_scores[1][0] if len(ticker_scores) > 1 else -1
        best_err = -best[1]
        if best[0] > second_overlap and (best[0] >= 2 or best_err <= math.log(1.20)):
            return best[2], {
                "method": "COINGECKO_TICKER_EXCHANGE_OVERLAP",
                "reference_price": ref,
                "ticker_exchange_overlap": best[0],
                "relative_log_error": None if best_err >= 900 else round(best_err, 6),
                "candidate_count": len(matches),
            }
    return None, {"method": "AMBIGUOUS_FAIL_CLOSED", "candidate_count": len(matches), "reference_price": ref}


def run(path: Path = DATA / "cex-revival-radar.json") -> dict:
    if not path.exists():
        raise SystemExit("CEX_REVIVAL_RADAR_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = list(payload.get("alerts") or [])
    symbols = [_base_symbol(x.get("symbol")) for x in raw]
    market_by_symbol = _fetch_by_symbols(symbols) if symbols else {}

    kept, rejected = [], []
    for alert in raw:
        base = _base_symbol(alert.get("symbol"))
        matches = market_by_symbol.get(base) or []
        chosen = None
        identity_evidence = None
        if len(matches) == 1:
            chosen = matches[0]
            identity_evidence = {"method": "UNIQUE_COINGECKO_SYMBOL", "candidate_count": 1}
        elif len(matches) > 1:
            chosen, identity_evidence = _resolve_ambiguous(alert, base, matches)
        if chosen is None:
            rejected.append({
                "symbol": alert.get("symbol"),
                "base_symbol": base,
                "reason": "AGE_IDENTITY_AMBIGUOUS" if matches else "AGE_IDENTITY_NOT_FOUND",
                "coingecko_matches": len(matches),
                "identity_evidence": identity_evidence,
            })
            continue

        meta = _age_meta(chosen, "COINGECKO_ATH_OR_ATL_AFTER_CEX_IDENTITY_PREFLIGHT")
        if not meta:
            rejected.append({
                "symbol": alert.get("symbol"),
                "base_symbol": base,
                "reason": "UNDER_180_DAYS_OR_AGE_UNVERIFIED",
                "coingecko_id": chosen.get("id"),
                "identity_evidence": identity_evidence,
            })
            continue
        kept.append({
            **alert,
            **meta,
            "cex_identity_preflight_verified": True,
            "cex_identity_preflight": identity_evidence,
        })

    payload["version"] = max(int(payload.get("version") or 0), 9)
    payload["alerts"] = kept
    payload["alerts_count"] = len(kept)
    payload["raw_alerts_before_age_gate"] = len(raw)
    payload["age_gate"] = {
        "status": "ENFORCED_FAIL_CLOSED",
        "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
        "accepted": len(kept),
        "rejected": len(rejected),
        "identity_rule": "UNIQUE_SYMBOL_OR_STRICT_CEX_PRICE/TICKER_COHERENCE_TO_ONE_COINGECKO_ID",
        "evidence_rule": "EXACT_COINGECKO_ID_THEN_EARLIEST_ATH_OR_ATL_PROVES_180D",
        "unknown_or_unresolved_identity": "REJECT",
        "rejections": rejected[:100],
    }
    payload["generated_identity_preflight_at"] = now_utc().isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["age_gate"]


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
