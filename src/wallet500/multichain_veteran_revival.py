from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_data import snapshot as market_snapshot

DATA = Path("data")
GECKO = "https://api.geckoterminal.com/api/v2"
CORE_NETWORKS = {
    "solana": "solana",
    "ethereum": "eth",
    "bsc": "bsc",
    "arbitrum": "arbitrum",
    "base": "base",
}
EVM_CHAINS = {"ethereum", "bsc", "arbitrum", "base"}
MIN_VETERAN_AGE_DAYS = 180
MIN_LIQUIDITY_USD = 50_000.0
MIN_VOLUME_H1_USD = 15_000.0
MIN_TXNS_H1 = 50
WATCH_SCORE = 70
MAX_WORKERS = 10
UA = {"Accept": "application/json", "User-Agent": "Wallet500/1.7"}

# Infrastructure/stable assets are discovery noise, not revival targets.
BLOCKED_ADDRESSES = {
    "solana": {
        "So11111111111111111111111111111111111111112",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "Es9vMFrzaCERmJfrF4H2FYD9iG6vGvL5JZtJm6Gq5tQ",
    },
    "ethereum": {
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "0x6b175474e89094c44da98b954eedeac495271d0f",
        "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    },
    "bsc": {
        "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
        "0x55d398326f99059ff775485246999027b3197955",
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
        "0xc5f0f7b66764f6ec8c8dff7ba683102295e16409",
    },
    "arbitrum": {
        "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
        "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
        "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8",
        "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
        "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f",
    },
    "base": {
        "0x4200000000000000000000000000000000000006",
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",
        "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
    },
}
BLOCKED_SYMBOLS = {
    "USDT", "USDC", "USDBC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD",
    "WETH", "WBNB", "WBTC", "CBETH", "CBBTC", "WSTETH", "STETH", "WSOL",
}


def _get_json(url: str, timeout: int = 18):
    req = Request(url, headers=UA)
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _norm(chain: str, value: object) -> str:
    text = str(value or "").strip()
    return text.lower() if chain in EVM_CHAINS else text


def _key(chain: str, token: object) -> str:
    return f"{chain}:{_norm(chain, token)}"


def _finite(value: object, default: float = 0.0) -> float:
    try:
        out = float(value or 0)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _pair_age_days(pair_created_at: object, now_dt: datetime) -> float | None:
    try:
        raw = float(pair_created_at or 0)
        # Missing/zero creation time is unknown age, never an epoch-age veteran.
        if not math.isfinite(raw) or raw <= 0:
            return None
        # DexScreener uses milliseconds. Test fixtures may use seconds.
        if raw > 10_000_000_000:
            raw /= 1000.0
        created = datetime.fromtimestamp(raw, tz=timezone.utc)
        if created > now_dt:
            return None
        return max(0.0, (now_dt - created).total_seconds() / 86400.0)
    except Exception:
        return None


def _evidence_age_days(value: object, now_dt: datetime) -> float | None:
    observed = _parse_dt(value)
    if observed is None or observed > now_dt:
        return None
    return max(0.0, (now_dt - observed).total_seconds() / 86400.0)


def _blocked(chain: str, token: object, symbol: object = None) -> bool:
    address = _norm(chain, token)
    if not address:
        return True
    blocked = {_norm(chain, x) for x in BLOCKED_ADDRESSES.get(chain, set())}
    if address in blocked:
        return True
    return str(symbol or "").upper().strip() in BLOCKED_SYMBOLS


def _extract_token(rel: dict, included: dict[str, dict]) -> tuple[str | None, str | None, str | None]:
    ref = (rel or {}).get("data") or {}
    tid = ref.get("id")
    obj = included.get(tid, {}) if tid else {}
    attrs = (obj or {}).get("attributes") or {}
    address = attrs.get("address")
    if not address and tid and "_" in tid:
        address = tid.split("_", 1)[1]
    return address, attrs.get("symbol"), attrs.get("name")


def _discover_chain(chain: str, network: str) -> tuple[list[dict], list[dict]]:
    found: dict[str, dict] = {}
    errors = []
    for endpoint in ("trending_pools", "pools"):
        params = urlencode({"page": 1, "include": "base_token,quote_token"})
        try:
            payload = _get_json(f"{GECKO}/networks/{network}/{endpoint}?{params}")
        except Exception as exc:
            errors.append({"chain": chain, "source": endpoint, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        included = {
            x.get("id"): x for x in (payload.get("included") or [])
            if isinstance(x, dict) and x.get("id")
        }
        for pool in payload.get("data") or []:
            if not isinstance(pool, dict):
                continue
            relationships = pool.get("relationships") or {}
            attrs = pool.get("attributes") or {}
            for side in ("base_token", "quote_token"):
                token, symbol, name = _extract_token(relationships.get(side) or {}, included)
                if not token or _blocked(chain, token, symbol):
                    continue
                k = _key(chain, token)
                row = found.setdefault(k, {
                    "chain": chain,
                    "token": token,
                    "symbol": symbol,
                    "name": name,
                    "discovery_sources": [],
                    "source_pool_addresses": [],
                })
                source = f"geckoterminal:{endpoint}"
                if source not in row["discovery_sources"]:
                    row["discovery_sources"].append(source)
                pool_address = attrs.get("address")
                if pool_address and pool_address not in row["source_pool_addresses"]:
                    row["source_pool_addresses"].append(pool_address)
    return list(found.values()), errors


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _spot_base_symbol(value: object) -> str:
    symbol = str(value or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def _discover_spot_registry_candidates(data_dir: Path) -> list[dict]:
    """Translate current Spot watches to exact on-chain candidates only via registry identity.

    A symbol alone can never inject a DEX candidate. The base symbol merely selects
    a pre-existing exact registry record, whose chain+contract is the actual identity.
    """
    spot = _load(data_dir / "cex-spot-revival-radar.json", {})
    registry = _load(data_dir / "cex-identity-registry.json", {})
    symbols = registry.get("symbols") if isinstance(registry, dict) else {}
    symbols = symbols if isinstance(symbols, dict) else {}
    watch_bases = {
        _spot_base_symbol(row.get("symbol"))
        for row in (spot.get("watchlist") or [])
        if isinstance(row, dict) and _spot_base_symbol(row.get("symbol"))
    }
    rows = []
    for symbol, meta in symbols.items():
        if not isinstance(meta, dict):
            continue
        canonical_symbol = str(symbol or "").upper().strip()
        if canonical_symbol not in watch_bases:
            continue
        chain = str(meta.get("chain") or "").lower().strip()
        token = str(meta.get("token_address") or "").strip()
        if chain not in CORE_NETWORKS or not token or _blocked(chain, token, canonical_symbol):
            continue
        rows.append({
            "chain": chain,
            "token": token,
            "symbol": canonical_symbol,
            "name": meta.get("name"),
            "discovery_sources": ["cex-spot-exact-registry-trigger"],
            "source_pool_addresses": [],
            "registry_identity_verified": True,
            "market_age_evidence_at": meta.get("market_age_evidence_at"),
            "market_age_evidence_source": meta.get("evidence_source") or "EXACT_IDENTITY_REGISTRY",
            "coingecko_id": meta.get("coingecko_id"),
        })
    return rows


def _merge_candidate(existing: dict, incoming: dict) -> dict:
    merged = {**existing}
    for field in ("discovery_sources", "source_pool_addresses"):
        values = list(merged.get(field) or [])
        for value in incoming.get(field) or []:
            if value not in values:
                values.append(value)
        merged[field] = values
    for field in (
        "symbol", "name", "registry_identity_verified", "market_age_evidence_at",
        "market_age_evidence_source", "coingecko_id",
    ):
        if incoming.get(field) not in (None, "", False):
            merged[field] = incoming.get(field)
    return merged


def discover_core_candidates(data_dir: Path = DATA) -> tuple[list[dict], list[dict]]:
    rows = []
    errors = []
    with ThreadPoolExecutor(max_workers=len(CORE_NETWORKS)) as pool:
        futures = {
            pool.submit(_discover_chain, chain, network): chain
            for chain, network in CORE_NETWORKS.items()
        }
        for fut in as_completed(futures):
            try:
                got, errs = fut.result()
                rows.extend(got)
                errors.extend(errs)
            except Exception as exc:
                chain = futures[fut]
                errors.append({"chain": chain, "source": "discovery", "error": f"{type(exc).__name__}: {exc}"[:300]})

    # CEX Spot watches with a pre-verified exact registry identity get a direct
    # DEX recheck even when the token is absent from GeckoTerminal page-1 pools.
    # This closes the IDOS-class coverage gap without enabling symbol-only action.
    rows.extend(_discover_spot_registry_candidates(data_dir))

    dedup: dict[str, dict] = {}
    for row in rows:
        key = _key(row["chain"], row["token"])
        if key in dedup:
            dedup[key] = _merge_candidate(dedup[key], row)
        else:
            dedup[key] = row
    return list(dedup.values()), errors


def _spot_exact_confirmation(data_dir: Path, chain: str, token: str) -> dict:
    registry = _load(data_dir / "cex-identity-registry.json", {})
    symbols = registry.get("symbols") if isinstance(registry, dict) else {}
    exact_symbol = None
    for symbol, meta in (symbols or {}).items():
        if not isinstance(meta, dict):
            continue
        if str(meta.get("chain") or "").lower() != chain:
            continue
        if _norm(chain, meta.get("token_address")) == _norm(chain, token):
            exact_symbol = str(symbol or "").upper().strip()
            break
    if not exact_symbol:
        return {"verified": False, "reason": "NO_EXACT_IDENTITY_REGISTRY_MAPPING"}

    spot = _load(data_dir / "cex-spot-revival-radar.json", {})
    matches = []
    for row in spot.get("watchlist") or []:
        if _spot_base_symbol(row.get("symbol")) == exact_symbol:
            matches.append(row)
    if not matches:
        return {"verified": False, "reason": "NO_CURRENT_SPOT_WATCH_FOR_EXACT_REGISTRY_IDENTITY", "symbol": exact_symbol}
    best = max(matches, key=lambda x: _finite(x.get("spot_revival_score")))
    return {
        "verified": True,
        "reason": "EXACT_REGISTRY_IDENTITY_PLUS_CEX_SPOT_WATCH",
        "symbol": exact_symbol,
        "spot_revival_score": best.get("spot_revival_score"),
        "exchanges": best.get("exchanges") or [],
        "coherent_confirmations": best.get("coherent_confirmations", 0),
    }


def _score(row: dict, snap: dict, now_dt: datetime, previous: dict | None, cex_spot: dict) -> dict:
    pair_age_days = _pair_age_days(snap.get("pair_created_at"), now_dt)
    registry_age_days = None
    if row.get("registry_identity_verified") is True:
        registry_age_days = _evidence_age_days(row.get("market_age_evidence_at"), now_dt)
    age_candidates = [x for x in (pair_age_days, registry_age_days) if x is not None]
    age_days = max(age_candidates) if age_candidates else None
    if registry_age_days is not None and (pair_age_days is None or registry_age_days >= pair_age_days):
        age_source = row.get("market_age_evidence_source") or "EXACT_IDENTITY_REGISTRY"
    else:
        age_source = "EXACT_SELECTED_PAIR_CREATED_AT_LOWER_BOUND"

    liq = _finite(snap.get("liquidity_usd"))
    vol_h1 = _finite(snap.get("volume_h1"))
    buys = int(snap.get("buys_h1") or 0)
    sells = int(snap.get("sells_h1") or 0)
    txns = buys + sells
    buy_sell = buys / max(sells, 1) if txns else 0.0
    turnover = vol_h1 / max(liq, 1.0) if vol_h1 > 0 else 0.0
    h1 = _finite(snap.get("price_change_h1"))
    h24 = _finite(snap.get("price_change_h24"))

    blockers = []
    if snap.get("token_identity_verified") is not True or not snap.get("pair_address"):
        blockers.append("EXACT_TOKEN_PAIR_IDENTITY_UNVERIFIED")
    if age_days is None or age_days < MIN_VETERAN_AGE_DAYS:
        blockers.append("PAIR_AGE_LT_180D_OR_UNKNOWN")
    if liq < MIN_LIQUIDITY_USD:
        blockers.append("LIVE_LIQUIDITY_LT_50K")
    if vol_h1 < MIN_VOLUME_H1_USD:
        blockers.append("VOLUME_H1_LT_15K")
    if txns < MIN_TXNS_H1:
        blockers.append("TXNS_H1_LT_50")

    chase_risk = h1 > 50 or h24 > 100
    score = 0
    reasons = []
    if not blockers:
        score += 20
        reasons.append("VETERAN_180D_EXACT_PAIR_LIQUIDITY_ACTIVITY_PASS")
        if turnover >= 0.50:
            score += 20
            reasons.append("H1_TURNOVER_GE_0_50")
        elif turnover >= 0.20:
            score += 12
            reasons.append("H1_TURNOVER_GE_0_20")
        if buy_sell >= 1.40:
            score += 20
            reasons.append("BUY_SELL_GE_1_40")
        elif buy_sell >= 1.18:
            score += 12
            reasons.append("BUY_SELL_GE_1_18")
        if txns >= 350:
            score += 15
            reasons.append("TXNS_H1_GE_350")
        elif txns >= 100:
            score += 8
            reasons.append("TXNS_H1_GE_100")
        if -5 <= h1 <= 20:
            score += 10
            reasons.append("CONTROLLED_H1_PRICE_STRUCTURE")
        if cex_spot.get("verified") is True:
            score += 15
            reasons.append("CEX_SPOT_EXACT_IDENTITY_CONFIRMATION")

        prev_vol = _finite((previous or {}).get("volume_h1"))
        prev_liq = _finite((previous or {}).get("liquidity_usd"))
        if prev_vol > 0 and vol_h1 / prev_vol >= 1.50:
            score += 10
            reasons.append("H1_VOLUME_ACCELERATION_GE_1_5X_PREVIOUS_OBSERVATION")
        if prev_liq > 0 and liq / prev_liq >= 0.90:
            score += 5
            reasons.append("LIQUIDITY_RETENTION_GE_90PCT")

    score = min(100, score)
    status = "INELIGIBLE_FAIL_CLOSED"
    if not blockers:
        status = "LATE_MOVE_DO_NOT_CHASE" if chase_risk else ("DNA_WATCH_RESEARCH" if score >= WATCH_SCORE else "VETERAN_RESEARCH_WATCH")

    return {
        **row,
        **snap,
        "market_age_verified": age_days is not None and age_days >= MIN_VETERAN_AGE_DAYS,
        "market_age_min_days": round(age_days, 2) if age_days is not None else None,
        "market_age_pair_days": round(pair_age_days, 2) if pair_age_days is not None else None,
        "market_age_registry_days": round(registry_age_days, 2) if registry_age_days is not None else None,
        "market_age_evidence_source": age_source,
        "real_time_gate": {
            "live_liquidity_usd": liq,
            "volume_h1_usd": vol_h1,
            "txns_h1": txns,
            "buy_sell_ratio_h1": round(buy_sell, 4),
            "turnover_h1": round(turnover, 4),
            "price_change_h1_pct": h1,
            "price_change_h24_pct": h24,
        },
        "cex_spot_confirmation": cex_spot,
        "winner_dna_score_research": score,
        "winner_dna_reasons": reasons,
        "blockers": blockers,
        "chase_risk": chase_risk,
        "status": status,
        "research_only": True,
        "actionable": False,
        "production_portfolio_impact": "NONE",
    }


def run(data_dir: Path = DATA, now: str | None = None) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    now_dt = _parse_dt(now) if now else datetime.now(timezone.utc)
    now_dt = now_dt or datetime.now(timezone.utc)
    observed_at = now_dt.isoformat()

    discovered, discovery_errors = discover_core_candidates(data_dir)
    state_path = data_dir / "multichain-veteran-revival-state.json"
    state = _load(state_path, {})
    previous_tokens = state.get("tokens") if isinstance(state.get("tokens"), dict) else {}

    snapshots = []
    errors = list(discovery_errors)
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(discovered)))) as pool:
        futures = {
            pool.submit(market_snapshot, row["chain"], row["token"]): row
            for row in discovered
        }
        for fut in as_completed(futures):
            row = futures[fut]
            try:
                snap = fut.result()
            except Exception as exc:
                snap = None
                errors.append({"chain": row["chain"], "token": row["token"], "error": f"{type(exc).__name__}: {exc}"[:300]})
            if not snap:
                continue
            key = _key(row["chain"], row["token"])
            previous_history = (previous_tokens.get(key) or {}).get("history") if isinstance(previous_tokens.get(key), dict) else []
            previous = previous_history[-1] if isinstance(previous_history, list) and previous_history else None
            cex_spot = _spot_exact_confirmation(data_dir, row["chain"], row["token"])
            snapshots.append(_score(row, snap, now_dt, previous, cex_spot))

    tokens = dict(previous_tokens)
    for row in snapshots:
        key = _key(row["chain"], row["token"])
        prev = tokens.get(key) if isinstance(tokens.get(key), dict) else {}
        history = prev.get("history") if isinstance(prev.get("history"), list) else []
        history.append({
            "observed_at": observed_at,
            "pair_address": row.get("pair_address"),
            "price_usd": row.get("price_usd"),
            "liquidity_usd": row.get("liquidity_usd"),
            "volume_h1": row.get("volume_h1"),
            "buys_h1": row.get("buys_h1"),
            "sells_h1": row.get("sells_h1"),
            "status": row.get("status"),
            "winner_dna_score_research": row.get("winner_dna_score_research"),
        })
        tokens[key] = {
            "chain": row["chain"],
            "token": row["token"],
            "first_seen_at": prev.get("first_seen_at") or observed_at,
            "last_seen_at": observed_at,
            "history": history[-48:],
        }

    state_payload = {
        "version": 2,
        "updated_at": observed_at,
        "no_hindsight": True,
        "tokens": tokens,
    }
    state_path.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    eligible = [x for x in snapshots if not x.get("blockers")]
    watches = [x for x in eligible if x.get("status") == "DNA_WATCH_RESEARCH"]
    late = [x for x in eligible if x.get("status") == "LATE_MOVE_DO_NOT_CHASE"]
    watches.sort(key=lambda x: (x.get("winner_dna_score_research", 0), x.get("volume_h1", 0)), reverse=True)

    counts_by_chain = {}
    for chain in CORE_NETWORKS:
        chain_rows = [x for x in snapshots if x.get("chain") == chain]
        counts_by_chain[chain] = {
            "snapshots": len(chain_rows),
            "veteran_gate_pass": sum(1 for x in chain_rows if not x.get("blockers")),
            "dna_watch": sum(1 for x in chain_rows if x.get("status") == "DNA_WATCH_RESEARCH"),
            "late_move": sum(1 for x in chain_rows if x.get("status") == "LATE_MOVE_DO_NOT_CHASE"),
        }

    spot_registry_triggered = sum(
        1 for row in discovered
        if "cex-spot-exact-registry-trigger" in (row.get("discovery_sources") or [])
    )
    payload = {
        "version": 2,
        "generated_at": observed_at,
        "mode": "RESEARCH_ONLY_CORE_MULTICHAIN_VETERAN_REVIVAL_V2",
        "core_chains": list(CORE_NETWORKS),
        "policy": {
            "minimum_market_age_days": MIN_VETERAN_AGE_DAYS,
            "minimum_live_liquidity_usd": MIN_LIQUIDITY_USD,
            "minimum_volume_h1_usd": MIN_VOLUME_H1_USD,
            "minimum_txns_h1": MIN_TXNS_H1,
            "exact_token_pair_required": True,
            "stable_wrapped_assets_excluded": True,
            "unknown_age": "FAIL_CLOSED",
            "veteran_age_evidence": "EXACT_SELECTED_PAIR_OR_EXACT_REGISTRY_CHAIN_CONTRACT_HISTORY",
            "symbol_only_cex_confirmation": "FORBIDDEN",
            "spot_watch_direct_recheck": "ONLY_PREVERIFIED_EXACT_REGISTRY_CHAIN_CONTRACT",
            "production_portfolio_impact": "NONE",
            "no_hindsight": True,
        },
        "discovered": len(discovered),
        "spot_registry_triggered": spot_registry_triggered,
        "snapshots": len(snapshots),
        "veteran_gate_pass": len(eligible),
        "dna_watch_count": len(watches),
        "late_move_count": len(late),
        "counts_by_chain": counts_by_chain,
        "dna_watch": watches[:50],
        "veteran_watch": sorted(eligible, key=lambda x: x.get("winner_dna_score_research", 0), reverse=True)[:100],
        "all_snapshots": snapshots[:250],
        "errors_count": len(errors),
        "errors": errors[-50:],
    }
    (data_dir / "multichain-veteran-revival.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
