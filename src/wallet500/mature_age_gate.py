from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_data import token_pairs

DATA = Path("data")
MIN_MARKET_AGE_DAYS = 180
UA = {"User-Agent": "Wallet500/1.5", "Accept": "application/json"}
_TRANSIENT_HTTP = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_MAX_RETRY_AFTER_SECONDS = 30


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: object) -> datetime | None:
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


def age_days_from_evidence(evidence_at: object, now: datetime) -> int | None:
    d = parse_dt(evidence_at)
    if d is None or d > now:
        return None
    return int((now - d).total_seconds() // 86400)


def earliest_market_evidence(row: dict) -> tuple[str | None, int | None]:
    now = now_utc()
    dates = [parse_dt(row.get("ath_date")), parse_dt(row.get("atl_date"))]
    dates = [x for x in dates if x is not None and x <= now]
    if not dates:
        return None, None
    evidence = min(dates)
    return evidence.isoformat(), int((now - evidence).total_seconds() // 86400)


def _headers() -> dict:
    h = dict(UA)
    key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def _retry_delay(attempt: int, error: HTTPError | None = None) -> float:
    if error is not None:
        raw = str(error.headers.get("Retry-After") or "").strip()
        try:
            if raw:
                return min(float(raw), _MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            pass
    return float(min(2 ** attempt, 8))


def _get_json(url: str, timeout: int = 25):
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        req = Request(url, headers=_headers())
        try:
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in _TRANSIENT_HTTP or attempt == _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(attempt, exc))
        except URLError as exc:
            last_error = exc
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(attempt))
    # Defensive fail-closed path; normal exhaustion re-raises above.
    if last_error is not None:
        raise last_error
    raise RuntimeError("market data request failed without an error")


def _cg_markets(params: dict) -> list[dict]:
    base = "https://api.coingecko.com/api/v3/coins/markets?"
    data = _get_json(base + urlencode(params, doseq=True))
    if not isinstance(data, list):
        raise RuntimeError("CoinGecko markets response is not a list")
    return data


def fetch_by_ids(ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    clean = list(dict.fromkeys(str(x).strip() for x in ids if str(x).strip()))
    for start in range(0, len(clean), 180):
        batch = clean[start:start + 180]
        rows = _cg_markets({
            "vs_currency": "usd",
            "ids": ",".join(batch),
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false",
        })
        for row in rows:
            coin_id = str(row.get("id") or "").strip()
            if coin_id:
                out[coin_id] = row
    return out


def fetch_by_symbols(symbols: list[str]) -> dict[str, list[dict]]:
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
        s = s[:-5]
    elif s.endswith("USDT"):
        s = s[:-4]
    return s


def _verified_meta_from_market(row: dict, source: str) -> dict | None:
    evidence_at, age_days = earliest_market_evidence(row)
    if evidence_at is None or age_days is None or age_days < MIN_MARKET_AGE_DAYS:
        return None
    return {
        "market_age_verified": True,
        "market_age_min_days": age_days,
        "market_age_evidence_at": evidence_at,
        "market_age_evidence_source": source,
        "coingecko_id": row.get("id"),
    }


def enforce_cex(path: Path = DATA / "cex-revival-radar.json") -> dict:
    d = json.loads(path.read_text())
    rows = d.get("rows") if isinstance(d.get("rows"), list) else []
    ids = [str(r.get("coingecko_id") or "").strip() for r in rows]
    ids_map = fetch_by_ids(ids)
    symbols_map = fetch_by_symbols([_base_symbol(r.get("symbol")) for r in rows])
    kept = []
    rejected = []
    for row in rows:
        cid = str(row.get("coingecko_id") or "").strip()
        meta = _verified_meta_from_market(ids_map.get(cid, {}), "coingecko_id") if cid else None
        if meta is None:
            sym = _base_symbol(row.get("symbol"))
            candidates = symbols_map.get(sym, [])
            valid = [(_verified_meta_from_market(x, "coingecko_symbol"), x) for x in candidates]
            valid = [(m, x) for m, x in valid if m]
            if len(valid) == 1:
                meta = valid[0][0]
        if meta is None:
            rejected.append({"symbol": row.get("symbol"), "reason": "MARKET_AGE_LT_180D_OR_UNVERIFIED"})
            continue
        row.update(meta)
        kept.append(row)
    d["rows"] = kept
    d["count"] = len(kept)
    d["mature_age_gate"] = {"minimum_days": MIN_MARKET_AGE_DAYS, "fail_closed": True, "rejected": rejected}
    path.write_text(json.dumps(d, indent=2))
    return d


def enforce_solana(path: Path = DATA / "revival-1000-latest.json") -> dict:
    d = json.loads(path.read_text())
    coins = d.get("coins") if isinstance(d.get("coins"), list) else []
    ids = [str(r.get("coingecko_id") or "").strip() for r in coins]
    ids_map = fetch_by_ids(ids)
    symbols_map = fetch_by_symbols([r.get("symbol") for r in coins])
    kept = []
    rejected = []
    for row in coins:
        cid = str(row.get("coingecko_id") or "").strip()
        meta = _verified_meta_from_market(ids_map.get(cid, {}), "coingecko_id") if cid else None
        if meta is None:
            sym = str(row.get("symbol") or "").strip().upper()
            candidates = symbols_map.get(sym, [])
            valid = [(_verified_meta_from_market(x, "coingecko_symbol"), x) for x in candidates]
            valid = [(m, x) for m, x in valid if m]
            if len(valid) == 1:
                meta = valid[0][0]
        if meta is None:
            rejected.append({"symbol": row.get("symbol"), "reason": "MARKET_AGE_LT_180D_OR_UNVERIFIED"})
            continue
        row.update(meta)
        kept.append(row)
    d["coins"] = kept
    counts = d.setdefault("counts", {})
    counts["mature_age_verified"] = len(kept)
    counts["mature_age_rejected"] = len(rejected)
    d["mature_age_gate"] = {"minimum_days": MIN_MARKET_AGE_DAYS, "fail_closed": True, "rejected": rejected}
    path.write_text(json.dumps(d, indent=2))
    return d


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cex", action="store_true")
    parser.add_argument("--solana", action="store_true")
    args = parser.parse_args()
    if not args.cex and not args.solana:
        args.cex = args.solana = True
    out = {}
    if args.cex:
        out["cex"] = enforce_cex()
    if args.solana:
        out["solana"] = enforce_solana()
    print(json.dumps({k: (v.get("count") or v.get("counts", {}).get("mature_age_verified")) for k, v in out.items()}, indent=2))


if __name__ == "__main__":
    main()
