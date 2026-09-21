from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/new-chain-bootstrap-radar.json"
STATE = ROOT / "data/new-chain-bootstrap-state.json"

GECKO = "https://api.geckoterminal.com/api/v2"
UA = "Wallet500-NewChainBootstrap/1.0"

CORE_NETWORKS = {
    "solana", "eth", "ethereum", "bsc", "base", "arbitrum",
    "optimism", "polygon_pos", "polygon", "avax", "avalanche",
}
SEED_NETWORKS = {
    "arc": {
        "network": "arc",
        "dex_chain": "arc",
        "evm": True,
        "launch_date": "2026-09-16T00:00:00+00:00",
        "activation_reason": "SEEDED_NEW_MAINNET_ARC",
        "bootstrap_days": 30,
        "catalyst": "Circle Arc public mainnet launch",
    },
    "robinhood": {
        "network": "robinhood",
        "dex_chain": "robinhood",
        "evm": True,
        "launch_date": None,
        "activation_reason": "SEEDED_EMERGING_MAINNET_ROBINHOOD",
        "bootstrap_days": 30,
        "catalyst": "Robinhood Chain mainnet; explicit bootstrap coverage prevents provider-baseline blindness",
    }
}
IGNORE_NETWORK_PARTS = (
    "testnet", "devnet", "sepolia", "goerli", "mumbai", "amoy",
    "fuji", "holesky", "test", "local",
)
STABLE_OR_BASE_SYMBOLS = {
    "USDC", "USDT", "DAI", "USDS", "USDE", "WETH", "ETH",
    "WBNB", "BNB", "WSOL", "SOL", "WBTC", "BTC", "CIRBTC",
}

NETWORK_FAST_SCAN_PAGES = max(1, min(8, int(os.getenv("NEW_CHAIN_NETWORK_FAST_SCAN_PAGES", "3"))))
NETWORK_FULL_SCAN_MAX_PAGES = max(3, min(30, int(os.getenv("NEW_CHAIN_NETWORK_FULL_SCAN_MAX_PAGES", "20"))))
NETWORK_FULL_SCAN_INTERVAL_MINUTES = max(15, int(os.getenv("NEW_CHAIN_NETWORK_FULL_SCAN_INTERVAL_MINUTES", "60")))
NEW_POOL_SCAN_PAGES = max(1, min(3, int(os.getenv("NEW_CHAIN_NEW_POOL_SCAN_PAGES", "2"))))
AUTO_ACTIVE_DAYS = max(1, int(os.getenv("NEW_CHAIN_AUTO_ACTIVE_DAYS", "14")))
MAX_AUTO_NETWORKS = max(1, int(os.getenv("NEW_CHAIN_MAX_AUTO_NETWORKS", "4")))
MIN_LIQUIDITY = float(os.getenv("NEW_CHAIN_MIN_LIQUIDITY_USD", "5000"))
MIN_VOLUME_H1 = float(os.getenv("NEW_CHAIN_MIN_VOLUME_H1_USD", "3000"))
MIN_VOLUME_H24 = float(os.getenv("NEW_CHAIN_MIN_VOLUME_H24_USD", "15000"))
MIN_ACTIVITY_H1 = int(os.getenv("NEW_CHAIN_MIN_ACTIVITY_H1", "12"))
MIN_SCORE = float(os.getenv("NEW_CHAIN_MIN_BOOTSTRAP_SCORE", "45"))
MAX_PAIR_AGE_HOURS = float(os.getenv("NEW_CHAIN_MAX_PAIR_AGE_HOURS", "168"))
HTTP_MIN_INTERVAL_SECONDS = float(os.getenv("NEW_CHAIN_HTTP_MIN_INTERVAL_SECONDS", "6.2"))

_last_http_at = 0.0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def num(value, default=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError, OverflowError):
        return default


def integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def parse_dt(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _get(url: str, timeout: int = 20, attempts: int = 3):
    global _last_http_at
    last_error = None
    for attempt in range(max(1, attempts)):
        wait = HTTP_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_http_at)
        if wait > 0:
            time.sleep(wait)
        try:
            req = Request(
                url,
                headers={
                    "Accept": "application/json;version=20230203",
                    "User-Agent": UA,
                },
            )
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt + 1 >= attempts:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = max(8.0, float(retry_after or 0))
            except Exception:
                delay = 8.0 * (attempt + 1)
            time.sleep(delay)
        finally:
            _last_http_at = time.monotonic()
    if last_error:
        raise last_error
    raise RuntimeError("HTTP_REQUEST_FAILED")


def _extract_token_id(token_id: str, token_obj: dict) -> str:
    attrs = (token_obj or {}).get("attributes") or {}
    address = str(attrs.get("address") or "").strip()
    if address:
        return address
    raw = str(token_id or "")
    return raw.split("_", 1)[1] if "_" in raw else ""


def _pool_age_hours(created_at, now: datetime) -> float | None:
    dt = parse_dt(created_at)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def score_pool(row: dict) -> tuple[float, list[str]]:
    liq = num(row.get("liquidity_usd"))
    vol1 = num(row.get("volume_h1"))
    vol24 = num(row.get("volume_h24"))
    buys = integer(row.get("buys_h1"))
    sells = integer(row.get("sells_h1"))
    activity = buys + sells
    ratio = (buys + 1.0) / (sells + 1.0)
    h1 = num(row.get("price_change_h1"))
    age = row.get("pair_age_hours")
    score = 0.0
    reasons: list[str] = []

    if liq >= 100_000:
        score += 22
        reasons.append("LIQUIDITY_100K_PLUS")
    elif liq >= 50_000:
        score += 18
        reasons.append("LIQUIDITY_50K_PLUS")
    elif liq >= 10_000:
        score += 12
        reasons.append("LIQUIDITY_10K_PLUS")
    elif liq >= MIN_LIQUIDITY:
        score += 7
        reasons.append("LIQUIDITY_MIN_PASS")

    if vol1 >= 100_000:
        score += 20
        reasons.append("VOLUME_H1_100K_PLUS")
    elif vol1 >= 25_000:
        score += 15
        reasons.append("VOLUME_H1_25K_PLUS")
    elif vol1 >= MIN_VOLUME_H1:
        score += 9
        reasons.append("VOLUME_H1_ACTIVE")
    elif vol24 >= MIN_VOLUME_H24:
        score += 6
        reasons.append("VOLUME_H24_ACTIVE")

    turnover = vol1 / liq if liq > 0 else 0.0
    if turnover >= 1.0:
        score += 18
        reasons.append("FAST_TURNOVER_1X_PLUS")
    elif turnover >= 0.30:
        score += 10
        reasons.append("FAST_TURNOVER_0_3X_PLUS")

    if activity >= 150:
        score += 15
        reasons.append("ACTIVITY_H1_150_PLUS")
    elif activity >= 50:
        score += 11
        reasons.append("ACTIVITY_H1_50_PLUS")
    elif activity >= MIN_ACTIVITY_H1:
        score += 6
        reasons.append("ACTIVITY_H1_ACTIVE")

    if ratio >= 2.0 and buys >= 10:
        score += 10
        reasons.append("BUY_PRESSURE_2X")
    elif ratio >= 1.35 and buys >= 8:
        score += 6
        reasons.append("BUY_PRESSURE_POSITIVE")

    if h1 >= 20:
        score += 9
        reasons.append("MOMENTUM_H1_20_PLUS")
    elif h1 >= 5:
        score += 5
        reasons.append("MOMENTUM_H1_POSITIVE")

    if age is not None:
        if age <= 24:
            score += 10
            reasons.append("PAIR_FIRST_24H")
        elif age <= 72:
            score += 7
            reasons.append("PAIR_FIRST_72H")
        elif age <= MAX_PAIR_AGE_HOURS:
            score += 3
            reasons.append("PAIR_BOOTSTRAP_WINDOW")

    return round(min(100.0, score), 1), reasons


def candidate_eligible(row: dict) -> bool:
    if str(row.get("symbol") or "").upper() in STABLE_OR_BASE_SYMBOLS:
        return False
    age = row.get("pair_age_hours")
    if age is None or age > MAX_PAIR_AGE_HOURS:
        return False
    liq = num(row.get("liquidity_usd"))
    vol1 = num(row.get("volume_h1"))
    vol24 = num(row.get("volume_h24"))
    activity = integer(row.get("buys_h1")) + integer(row.get("sells_h1"))
    if liq < MIN_LIQUIDITY:
        return False
    if vol1 < MIN_VOLUME_H1 and vol24 < MIN_VOLUME_H24:
        return False
    if activity < MIN_ACTIVITY_H1:
        return False
    return True


def parse_pool_payload(network: str, payload: dict, lane: str, now: datetime) -> list[dict]:
    included = {
        str(x.get("id")): x
        for x in (payload.get("included") or [])
        if isinstance(x, dict)
    }
    rows = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") or {}
        rel = ((item.get("relationships") or {}).get("base_token") or {}).get("data") or {}
        token_id = str(rel.get("id") or "")
        token_obj = included.get(token_id) or {}
        token_attrs = token_obj.get("attributes") or {}
        token = _extract_token_id(token_id, token_obj)
        pair = str(attrs.get("address") or "").strip()
        if not token or not pair:
            continue
        vol = attrs.get("volume_usd") or {}
        tx = attrs.get("transactions") or {}
        h1tx = tx.get("h1") or {}
        change = attrs.get("price_change_percentage") or {}
        age = _pool_age_hours(attrs.get("pool_created_at"), now)
        row = {
            "network": network,
            "chain": network,
            "contract": token,
            "pair": pair,
            "symbol": token_attrs.get("symbol"),
            "name": token_attrs.get("name"),
            "dex_url": f"https://www.geckoterminal.com/{network}/pools/{pair}",
            "price_usd": num(attrs.get("base_token_price_usd")),
            "liquidity_usd": num(attrs.get("reserve_in_usd")),
            "volume_h1": num(vol.get("h1")),
            "volume_h24": num(vol.get("h24")),
            "buys_h1": integer(h1tx.get("buys")),
            "sells_h1": integer(h1tx.get("sells")),
            "price_change_h1": num(change.get("h1")),
            "price_change_h24": num(change.get("h24")),
            "pair_created_at": attrs.get("pool_created_at"),
            "pair_age_hours": round(age, 3) if age is not None else None,
            "source": f"geckoterminal:{lane}",
            "sources": [f"geckoterminal:{lane}"],
            "source_confirmations": 1,
            "exact_pair_verified_from_gecko": True,
        }
        score, reasons = score_pool(row)
        row["bootstrap_score"] = score
        row["bootstrap_reasons"] = reasons
        row["bootstrap_actionable_watch"] = bool(candidate_eligible(row) and score >= MIN_SCORE)
        row["status"] = "BOOTSTRAP_CANDIDATE" if row["bootstrap_actionable_watch"] else "RESEARCH_ONLY"
        rows.append(row)
    return rows


def merge_candidates(rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in rows:
        network = str(row.get("network") or "").lower()
        pair = str(row.get("pair") or "").lower()
        key = f"{network}:{pair}"
        prior = merged.get(key)
        if prior is None:
            merged[key] = dict(row)
            continue
        sources = list(dict.fromkeys((prior.get("sources") or []) + (row.get("sources") or [])))
        if num(row.get("bootstrap_score")) > num(prior.get("bootstrap_score")):
            keep = dict(row)
        else:
            keep = dict(prior)
        keep["sources"] = sources
        keep["source_confirmations"] = len(sources)
        keep["bootstrap_score"] = max(num(prior.get("bootstrap_score")), num(row.get("bootstrap_score")))
        keep["bootstrap_actionable_watch"] = bool(
            prior.get("bootstrap_actionable_watch") or row.get("bootstrap_actionable_watch")
        )
        keep["status"] = "BOOTSTRAP_CANDIDATE" if keep["bootstrap_actionable_watch"] else "RESEARCH_ONLY"
        merged[key] = keep
    return sorted(
        merged.values(),
        key=lambda x: (
            x.get("bootstrap_actionable_watch") is True,
            num(x.get("bootstrap_score")),
            num(x.get("liquidity_usd")),
            num(x.get("volume_h1")),
        ),
        reverse=True,
    )


def discover_supported_networks(max_pages: int) -> tuple[list[str], list[dict]]:
    found: list[str] = []
    errors: list[dict] = []
    for page in range(1, max(1, int(max_pages)) + 1):
        try:
            payload = _get(f"{GECKO}/networks?{urlencode({'page': page})}")
        except HTTPError as exc:
            # GeckoTerminal returns HTTP 400 when pagination has moved past the
            # current network catalog. Treat that as end-of-catalog, not as an
            # error; continuing only creates a rate-limit storm that can starve
            # the actual Arc/new-pool scan.
            if exc.code == 400 and found:
                break
            errors.append({"stage": "network_index", "page": page, "error": f"HTTPError:{exc.code}"})
            break
        except Exception as exc:
            errors.append({"stage": "network_index", "page": page, "error": f"{type(exc).__name__}:{str(exc)[:180]}"})
            break
        data = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(data, list) or not data:
            break
        for item in data:
            nid = str((item or {}).get("id") or "").strip().lower()
            if nid and nid not in found:
                found.append(nid)
    return found, errors


def _is_auto_candidate(network: str) -> bool:
    n = str(network or "").lower()
    if not n or n in CORE_NETWORKS or n in SEED_NETWORKS:
        return False
    return not any(part in n for part in IGNORE_NETWORK_PARTS)


def update_network_state(state: dict, supported: list[str], now: datetime) -> tuple[dict, list[str]]:
    known = state.get("known_networks") if isinstance(state.get("known_networks"), dict) else {}
    known = dict(known)
    baseline_initialized = bool(state.get("baseline_initialized"))
    newly_seen: list[str] = []

    for network in supported:
        if network in known:
            known[network]["last_seen_at"] = now.isoformat()
            continue
        known[network] = {
            "first_seen_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "classification": "POST_BASELINE_NEW_NETWORK" if baseline_initialized else "INITIAL_BASELINE",
        }
        if baseline_initialized and _is_auto_candidate(network):
            newly_seen.append(network)

    for network, cfg in SEED_NETWORKS.items():
        rec = dict(known.get(network) or {})
        rec.setdefault("first_seen_at", cfg.get("launch_date") or now.isoformat())
        rec["last_seen_at"] = now.isoformat()
        rec["classification"] = "SEEDED_BOOTSTRAP_NETWORK"
        known[network] = rec

    next_state = {
        "version": 1,
        "updated_at": now.isoformat(),
        "baseline_initialized": baseline_initialized or bool(supported),
        "known_networks": known,
        "auto_active_networks": list(state.get("auto_active_networks") or []),
    }

    active_auto = []
    cutoff = now.timestamp() - AUTO_ACTIVE_DAYS * 86400
    existing_auto = list(dict.fromkeys((state.get("auto_active_networks") or []) + newly_seen))
    for network in existing_auto:
        rec = known.get(network) or {}
        first = parse_dt(rec.get("first_seen_at"))
        if first and first.timestamp() >= cutoff and _is_auto_candidate(network):
            active_auto.append(network)
    active_auto.sort(key=lambda n: str((known.get(n) or {}).get("first_seen_at") or ""), reverse=True)
    next_state["auto_active_networks"] = active_auto[:MAX_AUTO_NETWORKS]
    return next_state, newly_seen


def active_networks(state: dict) -> list[str]:
    rows = list(SEED_NETWORKS)
    rows.extend(state.get("auto_active_networks") or [])
    return list(dict.fromkeys(rows))


def collect_network(network: str, now: datetime) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []
    requests = [("new_pools", f"new_pools:p{page}", page) for page in range(1, NEW_POOL_SCAN_PAGES + 1)]
    requests.extend([
        ("trending_pools", "trending_pools", 1),
        ("pools", "top_pools", 1),
    ])
    for endpoint, lane, page in requests:
        try:
            payload = _get(
                f"{GECKO}/networks/{network}/{endpoint}?{urlencode({'page': page, 'include': 'base_token'})}"
            )
            rows.extend(parse_pool_payload(network, payload, lane, now))
        except Exception as exc:
            errors.append({
                "stage": lane,
                "network": network,
                "page": page,
                "error": f"{type(exc).__name__}:{str(exc)[:180]}",
            })
    return rows, errors


def run(now: datetime | None = None) -> dict:
    now = (now or now_utc()).astimezone(timezone.utc)
    state = load(STATE, {"version": 1, "baseline_initialized": False, "known_networks": {}, "auto_active_networks": []})

    last_full = parse_dt(state.get("last_full_network_scan_at"))
    full_scan_due = (
        not bool(state.get("baseline_initialized"))
        or last_full is None
        or (now - last_full).total_seconds() >= NETWORK_FULL_SCAN_INTERVAL_MINUTES * 60
    )
    catalog_pages = NETWORK_FULL_SCAN_MAX_PAGES if full_scan_due else NETWORK_FAST_SCAN_PAGES
    supported, errors = discover_supported_networks(catalog_pages)
    state, newly_seen = update_network_state(state, supported, now)
    if full_scan_due and supported:
        state["last_full_network_scan_at"] = now.isoformat()
    state["last_catalog_scan_at"] = now.isoformat()
    state["last_catalog_scan_mode"] = "FULL" if full_scan_due else "FAST"
    state["last_catalog_pages_requested"] = catalog_pages
    networks = active_networks(state)

    rows: list[dict] = []
    chain_reports: list[dict] = []
    for network in networks:
        network_rows, network_errors = collect_network(network, now)
        errors.extend(network_errors)
        merged = merge_candidates(network_rows)
        rows.extend(merged)
        cfg = SEED_NETWORKS.get(network) or {}
        chain_reports.append({
            "network": network,
            "activation_reason": cfg.get("activation_reason") or "AUTO_DETECTED_PROVIDER_NETWORK",
            "launch_date": cfg.get("launch_date") or (state.get("known_networks", {}).get(network) or {}).get("first_seen_at"),
            "catalyst": cfg.get("catalyst"),
            "pairs_seen": len(merged),
            "bootstrap_candidates": sum(x.get("bootstrap_actionable_watch") is True for x in merged),
            "max_bootstrap_score": max([num(x.get("bootstrap_score")) for x in merged] or [0.0]),
            "max_liquidity_usd": max([num(x.get("liquidity_usd")) for x in merged] or [0.0]),
            "max_volume_h1_usd": max([num(x.get("volume_h1")) for x in merged] or [0.0]),
        })

    ranked = merge_candidates(rows)
    candidates = [x for x in ranked if x.get("bootstrap_actionable_watch") is True][:60]
    for row in candidates:
        row["bootstrap_final_buy_lane"] = True
        row["deep_investigation"] = True
        row["full_intelligence"] = True
        row["exact_identity_required"] = True
        row["exact_pair_required"] = True
        row["telegram_policy"] = "FINAL_BUY_ONLY"
        row["first_seen_at"] = row.get("pair_created_at") or now.isoformat()
        row["bootstrap_network_first_seen_at"] = (
            (state.get("known_networks", {}).get(row["network"]) or {}).get("first_seen_at")
            or now.isoformat()
        )

    report = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": "NEW_CHAIN_BOOTSTRAP_RADAR_V1",
        "status": "LIVE" if networks else "DEGRADED_NO_ACTIVE_NETWORKS",
        "automatic_trade": False,
        "telegram_policy": "FINAL_BUY_ONLY_AFTER_UNIFIED_GATE",
        "seed_networks": list(SEED_NETWORKS),
        "auto_detected_new_networks_this_run": newly_seen,
        "active_networks": networks,
        "supported_networks_sampled": len(supported),
        "thresholds": {
            "min_liquidity_usd": MIN_LIQUIDITY,
            "min_volume_h1_usd": MIN_VOLUME_H1,
            "min_volume_h24_usd": MIN_VOLUME_H24,
            "min_activity_h1": MIN_ACTIVITY_H1,
            "min_bootstrap_score": MIN_SCORE,
            "max_pair_age_hours": MAX_PAIR_AGE_HOURS,
            "auto_active_days": AUTO_ACTIVE_DAYS,
            "network_fast_scan_pages": NETWORK_FAST_SCAN_PAGES,
            "network_full_scan_max_pages": NETWORK_FULL_SCAN_MAX_PAGES,
            "network_full_scan_interval_minutes": NETWORK_FULL_SCAN_INTERVAL_MINUTES,
            "new_pool_scan_pages": NEW_POOL_SCAN_PAGES,
        },
        "network_catalog": {
            "scan_mode": state.get("last_catalog_scan_mode"),
            "pages_requested": state.get("last_catalog_pages_requested"),
            "last_full_scan_at": state.get("last_full_network_scan_at"),
        },
        "counts": {
            "active_networks": len(networks),
            "pairs_seen": len(ranked),
            "bootstrap_candidates": len(candidates),
            "errors": len(errors),
        },
        "chains": chain_reports,
        "candidates": candidates,
        "errors": errors[-30:],
        "truth_contract": {
            "provider_network_index_bootstraps_future_networks": True,
            "initial_provider_catalog_is_full_baseline_not_false_new_chain": True,
            "hourly_full_provider_catalog_detects_networks_outside_fast_pages": True,
            "seeded_arc_is_active_immediately": True,
            "exact_chain_contract_pair_required_before_final_buy": True,
            "research_detection_never_auto_trades": True,
            "telegram_only_after_unified_final_buy_gate": True,
        },
    }
    write(STATE, state)
    write(OUT, report)
    return report


def main() -> int:
    payload = run()
    print(json.dumps({
        "status": payload.get("status"),
        "active_networks": payload.get("active_networks"),
        "bootstrap_candidates": (payload.get("counts") or {}).get("bootstrap_candidates"),
        "errors": (payload.get("counts") or {}).get("errors"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
