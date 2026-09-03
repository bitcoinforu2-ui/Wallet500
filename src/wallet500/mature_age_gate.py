from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_data import token_pairs

DATA = Path("data")
MIN_MARKET_AGE_DAYS = 180
UA = {"User-Agent": "Wallet500/1.5", "Accept": "application/json"}


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


def _get_json(url: str, timeout: int = 25):
    req = Request(url, headers=_headers())
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


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
    if not path.exists():
        raise SystemExit("CEX_REVIVAL_RADAR_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = list(payload.get("alerts") or [])
    symbols = [_base_symbol(x.get("symbol")) for x in raw]
    market_by_symbol = fetch_by_symbols(symbols) if symbols else {}

    kept = []
    rejected = []
    for alert in raw:
        base = _base_symbol(alert.get("symbol"))
        matches = market_by_symbol.get(base) or []
        if len(matches) != 1:
            rejected.append({
                "symbol": alert.get("symbol"),
                "base_symbol": base,
                "reason": "AGE_IDENTITY_AMBIGUOUS" if len(matches) > 1 else "AGE_IDENTITY_NOT_FOUND",
                "coingecko_matches": len(matches),
            })
            continue
        meta = _verified_meta_from_market(
            matches[0],
            "COINGECKO_ATH_OR_ATL_HISTORICAL_EVIDENCE_UNIQUE_SYMBOL",
        )
        if not meta:
            evidence_at, age_days = earliest_market_evidence(matches[0])
            rejected.append({
                "symbol": alert.get("symbol"),
                "base_symbol": base,
                "reason": "UNDER_180_DAYS" if age_days is not None else "AGE_UNVERIFIED",
                "market_age_min_days": age_days,
                "market_age_evidence_at": evidence_at,
                "coingecko_id": matches[0].get("id"),
            })
            continue
        kept.append({**alert, **meta})

    payload["version"] = max(int(payload.get("version") or 0), 7)
    payload["alerts"] = kept
    payload["alerts_count"] = len(kept)
    payload["raw_alerts_before_age_gate"] = len(raw)
    payload["age_gate"] = {
        "status": "ENFORCED_FAIL_CLOSED",
        "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
        "accepted": len(kept),
        "rejected": len(rejected),
        "identity_rule": "CEX_SYMBOL_MUST_MAP_TO_EXACTLY_ONE_COINGECKO_MARKET",
        "evidence_rule": "EARLIEST_ATH_OR_ATL_DATE_MUST_PROVE_AT_LEAST_180_DAYS_OF_MARKET_HISTORY",
        "unknown_or_ambiguous_age": "REJECT",
        "rejections": rejected[:100],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["age_gate"]


def _pair_age_meta(coin: dict) -> dict | None:
    try:
        age = float(coin.get("pair_age_days"))
    except (TypeError, ValueError):
        return None
    if age < MIN_MARKET_AGE_DAYS:
        return None
    now = now_utc()
    evidence = datetime.fromtimestamp(now.timestamp() - age * 86400, tz=timezone.utc)
    return {
        "market_age_verified": True,
        "market_age_min_days": int(age),
        "market_age_evidence_at": evidence.isoformat(),
        "market_age_evidence_source": "DEXSCREENER_PAIR_CREATED_AT_LOWER_BOUND",
    }


def _recompute_revival_counts(payload: dict) -> None:
    coins = list(payload.get("coins") or [])
    counts = payload.setdefault("counts", {})
    counts["universe"] = len(coins)
    counts["dex_verified_pairs"] = sum(1 for x in coins if x.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR")
    counts["core_drawdown_watch"] = sum(
        1 for x in coins if 70 <= float(x.get("drawdown_from_ath_pct") or -1) <= 95
    )
    counts["waking_market_only"] = sum(1 for x in coins if x.get("watch_status") == "WAKING_MARKET_ONLY")
    counts["absorption_proxy_watch"] = sum(
        1 for x in coins if (x.get("order_flow_absorption") or {}).get("signal") is True
    )
    counts["absorption_candidate_proxy_watch"] = sum(1 for x in coins if x.get("absorption_candidate_proxy") is True)
    expansion = [x for x in coins if x.get("source") == "revival_discovery_state+dexscreener_absorption_expansion"]
    counts["absorption_discovery_expansion_added"] = len(expansion)
    counts["absorption_discovery_strict_added"] = sum(
        1 for x in expansion if (x.get("order_flow_absorption") or {}).get("signal") is True
    )
    counts["absorption_discovery_candidate_added"] = sum(
        1 for x in expansion if x.get("watch_status") == "ABSORPTION_CANDIDATE_DISCOVERY_EXPANSION"
    )


def enforce_revival(path: Path = DATA / "revival-1000-latest.json") -> dict:
    if not path.exists():
        raise SystemExit("REVIVAL_1000_LATEST_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = list(payload.get("coins") or [])
    exact_ids = [
        str(x.get("id") or "") for x in raw
        if x.get("source") != "revival_discovery_state+dexscreener_absorption_expansion"
        and str(x.get("id") or "").strip()
        and not str(x.get("id") or "").startswith("discovery:")
    ]
    market_by_id = fetch_by_ids(exact_ids) if exact_ids else {}

    kept = []
    rejected = []
    for coin in raw:
        is_expansion = coin.get("source") == "revival_discovery_state+dexscreener_absorption_expansion"
        meta = _pair_age_meta(coin) if is_expansion else None
        if not is_expansion:
            coin_id = str(coin.get("id") or "").strip()
            market = market_by_id.get(coin_id)
            if market:
                meta = _verified_meta_from_market(
                    market,
                    "COINGECKO_ATH_OR_ATL_HISTORICAL_EVIDENCE_EXACT_ID",
                )
        if not meta:
            rejected.append({
                "symbol": coin.get("symbol"),
                "id": coin.get("id"),
                "source": coin.get("source"),
                "pair_age_days": coin.get("pair_age_days"),
                "reason": "UNDER_180_DAYS_OR_AGE_UNVERIFIED",
            })
            continue
        kept.append({**coin, **meta})

    payload["coins"] = kept
    payload["asset_age_filter"] = "VERIFIED_MARKET_AGE_GTE_180_DAYS_ONLY"
    payload["age_gate"] = {
        "status": "ENFORCED_FAIL_CLOSED",
        "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
        "raw_universe_before_age_gate": len(raw),
        "accepted": len(kept),
        "rejected": len(rejected),
        "unknown_age": "REJECT",
        "evidence_sources": [
            "COINGECKO_ATH_OR_ATL_HISTORICAL_EVIDENCE_EXACT_ID",
            "DEXSCREENER_PAIR_CREATED_AT_LOWER_BOUND",
        ],
        "rejections": rejected[:100],
    }
    _recompute_revival_counts(payload)
    counts = payload.setdefault("counts", {})
    counts["age_gate_raw_universe"] = len(raw)
    counts["age_gate_rejected"] = len(rejected)
    counts["age_verified_180d_plus"] = len(kept)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["age_gate"]


def _same_address(chain: str, left: object, right: object) -> bool:
    a = str(left or "").strip()
    b = str(right or "").strip()
    if not a or not b:
        return False
    if chain.lower() in {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "polygon"}:
        return a.lower() == b.lower()
    return a == b


def _meta_from_pair_created_at(pair_created_at: object, source: str) -> dict | None:
    try:
        ms = float(pair_created_at or 0)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    now = now_utc()
    evidence = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    if evidence > now:
        return None
    age_days = int((now - evidence).total_seconds() // 86400)
    if age_days < MIN_MARKET_AGE_DAYS:
        return None
    return {
        "market_age_verified": True,
        "market_age_min_days": age_days,
        "market_age_evidence_at": evidence.isoformat(),
        "market_age_evidence_source": source,
    }


def _oldest_exact_token_pair_meta(row: dict) -> dict | None:
    chain = str(row.get("chain") or "").strip().lower()
    token = str(row.get("token") or row.get("mint") or row.get("token_address") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    locked = str(row.get("locked_pair_address") or "").strip()
    if not chain or not token or not pair or not locked:
        return None
    if row.get("pair_identity_locked") is not True or not _same_address(chain, pair, locked):
        return None

    meta = _meta_from_pair_created_at(
        row.get("pair_created_at"),
        "DEXSCREENER_EXACT_LOCKED_PAIR_CREATED_AT",
    )
    if meta:
        return meta

    pairs = token_pairs(chain, token)
    oldest_ms = None
    oldest_pair = None
    for candidate in pairs or []:
        base = (candidate.get("baseToken") or {}).get("address")
        quote_token = (candidate.get("quoteToken") or {}).get("address")
        if not (_same_address(chain, token, base) or _same_address(chain, token, quote_token)):
            continue
        try:
            ms = float(candidate.get("pairCreatedAt") or 0)
        except (TypeError, ValueError):
            continue
        if ms > 0 and (oldest_ms is None or ms < oldest_ms):
            oldest_ms = ms
            oldest_pair = candidate.get("pairAddress")
    meta = _meta_from_pair_created_at(
        oldest_ms,
        "DEXSCREENER_OLDEST_CURRENT_EXACT_TOKEN_PAIR_CREATED_AT",
    )
    if meta:
        meta["market_age_evidence_pair_address"] = oldest_pair
    return meta


def enforce_active_candidates(
    path: Path = DATA / "active-qualified-candidates.json",
    audit_path: Path = DATA / "active-qualified-age-gate.json",
) -> dict:
    if not path.exists():
        raise SystemExit("ACTIVE_QUALIFIED_CANDIDATES_MISSING")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("ACTIVE_QUALIFIED_CANDIDATES_NOT_LIST")

    kept = []
    rejected = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        meta = _oldest_exact_token_pair_meta(row)
        if not meta:
            rejected.append({
                "chain": row.get("chain"),
                "token": row.get("token") or row.get("mint") or row.get("token_address"),
                "pair_address": row.get("pair_address"),
                "reason": "UNDER_180_DAYS_OR_EXACT_MARKET_AGE_UNVERIFIED",
            })
            continue
        kept.append({**row, **meta})

    path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "version": 1,
        "generated_at": now_utc().isoformat(),
        "status": "ENFORCED_FAIL_CLOSED",
        "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
        "raw_active_before_age_gate": len(raw),
        "accepted": len(kept),
        "rejected": len(rejected),
        "identity_rule": "EXACT_CHAIN_TOKEN_AND_LOCKED_PAIR_REQUIRED; SYMBOL_NOT_USED",
        "evidence_rule": "EXACT_LOCKED_PAIR_OR_OLDEST_CURRENT_EXACT_TOKEN_PAIR_MUST_PROVE_AT_LEAST_180_DAYS",
        "unknown_age": "REJECT",
        "rejections": rejected[:500],
    }
    audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def validate_file(path: Path, collection_key: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = list(payload.get(collection_key) or [])
    bad = [x for x in rows if x.get("market_age_verified") is not True or int(x.get("market_age_min_days") or 0) < MIN_MARKET_AGE_DAYS]
    if bad:
        raise SystemExit(f"MATURE_AGE_GATE_VIOLATION:{path}:{len(bad)}")
    gate = payload.get("age_gate") or {}
    if gate.get("status") != "ENFORCED_FAIL_CLOSED" or int(gate.get("minimum_market_age_days") or 0) != MIN_MARKET_AGE_DAYS:
        raise SystemExit(f"MATURE_AGE_GATE_METADATA_MISSING:{path}")


def validate_active_file(path: Path = DATA / "active-qualified-candidates.json") -> None:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("ACTIVE_AGE_GATE_OUTPUT_NOT_LIST")
    bad = [x for x in rows if x.get("market_age_verified") is not True or int(x.get("market_age_min_days") or 0) < MIN_MARKET_AGE_DAYS]
    if bad:
        raise SystemExit(f"ACTIVE_MATURE_AGE_GATE_VIOLATION:{len(bad)}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cex", action="store_true")
    p.add_argument("--revival", action="store_true")
    p.add_argument("--active", action="store_true")
    args = p.parse_args()
    selected = args.cex or args.revival or args.active
    do_cex = args.cex or not selected
    do_revival = args.revival or not selected
    do_active = args.active or not selected
    report = {"minimum_market_age_days": MIN_MARKET_AGE_DAYS}
    if do_cex:
        report["cex"] = enforce_cex()
        validate_file(DATA / "cex-revival-radar.json", "alerts")
    if do_revival:
        report["revival"] = enforce_revival()
        validate_file(DATA / "revival-1000-latest.json", "coins")
    if do_active:
        report["active"] = enforce_active_candidates()
        validate_active_file()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
