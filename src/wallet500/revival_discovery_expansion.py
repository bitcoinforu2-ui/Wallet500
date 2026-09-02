from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from wallet500 import revival_1000 as core
from wallet500.revival_absorption_signal import compute_absorption_proxy

DATA = Path("data")
LATEST = DATA / "revival-1000-latest.json"
REVIVAL_STATE = DATA / "revival-state.json"
NETWORK = "solana"
DEX_BATCH_SIZE = 30
MODE = "RESEARCH_ONLY_REVIVAL_SOLANA_EXPANDED_V5"
MIN_AGE_DAYS = 180.0
DISCOVERY_DENY_SYMBOLS = {
    "SOL", "WSOL", "BTC", "WBTC", "CBBTC", "TBTC", "LBTC", "SOLVBTC",
    "ETH", "WETH", "BNB", "WBNB", "USDT", "USDC", "DAI", "PYUSD", "FDUSD",
    "USDS", "USDE", "TUSD", "USDP", "GUSD", "FRAX", "LUSD", "CRVUSD",
    "JITOSOL", "JUPSOL", "MSOL", "STSOL", "BNSOL", "VSOL", "JLP",
}


def n(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def pair_age_days(pair: dict) -> float | None:
    try:
        ms = float(pair.get("pairCreatedAt") or 0)
        if ms <= 0:
            return None
        created = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400.0)
    except Exception:
        return None


def token_symbol(token: str, pair: dict) -> str:
    base = pair.get("baseToken") or {}
    quote_token = pair.get("quoteToken") or {}
    if str(base.get("address") or "") == token:
        return str(base.get("symbol") or "").strip().upper()
    if str(quote_token.get("address") or "") == token:
        return str(quote_token.get("symbol") or "").strip().upper()
    return ""


def discovery_asset_allowed(token: str, pair: dict) -> bool:
    symbol = token_symbol(token, pair)
    if not symbol or symbol in DISCOVERY_DENY_SYMBOLS:
        return False
    probe = {"symbol": symbol, "name": symbol, "id": ""}
    return not core.is_stable_like(probe) and not core.is_pegged_or_derivative_like(probe)


def load_known_solana_tokens() -> list[str]:
    if not REVIVAL_STATE.exists():
        return []
    try:
        state = json.loads(REVIVAL_STATE.read_text())
    except Exception:
        return []
    records = state.get("tokens") or {}
    tokens, seen = [], set()
    if isinstance(records, dict):
        for row in records.values():
            if not isinstance(row, dict) or row.get("chain") != NETWORK:
                continue
            token = str(row.get("token") or "").strip()
            if core.looks_like_solana_address(token) and token not in seen:
                seen.add(token)
                tokens.append(token)
    return tokens


def fetch_pairs_for_tokens(tokens: list[str]) -> tuple[dict[str, dict], list[dict]]:
    pair_map, failures = {}, []
    for start in range(0, len(tokens), DEX_BATCH_SIZE):
        batch = tokens[start:start + DEX_BATCH_SIZE]
        pairs, last_error = None, None
        for attempt in range(3):
            try:
                pairs = core.fetch_json(
                    "https://api.dexscreener.com/tokens/v1/solana/" + quote(",".join(batch), safe=","),
                    timeout=25,
                )
                if not isinstance(pairs, list):
                    raise RuntimeError("DexScreener response is not a list")
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
        if not isinstance(pairs, list):
            failures.append({"start": start, "size": len(batch), "error": f"{type(last_error).__name__}: {last_error}"})
            continue
        for token in batch:
            pair = core.select_best_dex_pair(token, pairs)
            if pair:
                pair_map[token] = pair
        if start + DEX_BATCH_SIZE < len(tokens):
            time.sleep(0.12)
    return pair_map, failures


def to_candidate(token: str, pair: dict, flow: dict, rank: int) -> dict:
    symbol = token_symbol(token, pair)
    liq = n((pair.get("liquidity") or {}).get("usd"))
    vol24 = n((pair.get("volume") or {}).get("h24"))
    ch = pair.get("priceChange") or {}
    age = pair_age_days(pair)
    now = core.now_iso()
    return {
        "source": "revival_discovery_state+dexscreener_absorption_expansion",
        "network": NETWORK,
        "network_verified": True,
        "network_verification": "REVIVAL_DISCOVERY_STATE_SOLANA_TOKEN_PLUS_CURRENT_DEXSCREENER_PAIR",
        "solana_only_platform_verified": False,
        "cross_platform_status": "UNKNOWN_RESEARCH_ONLY",
        "stablecoin_excluded": True,
        "pegged_derivative_excluded": True,
        "id": "discovery:" + token,
        "token_address": token,
        "symbol": symbol,
        "name": symbol,
        "market_cap_rank": None,
        "market_cap_usd": n(pair.get("marketCap"), n(pair.get("fdv"))),
        "price_usd": n(pair.get("priceUsd")),
        "volume_24h_usd": vol24,
        "ath_usd": None,
        "ath_date": None,
        "drawdown_from_ath_pct": None,
        "change_24h_pct": n(ch.get("h24")),
        "change_7d_pct": None,
        "change_30d_pct": None,
        "dex_link": str(pair.get("url") or ""),
        "dex_pair_address": str(pair.get("pairAddress") or ""),
        "dex_id": pair.get("dexId"),
        "dex_pair_liquidity_usd": liq,
        "dex_pair_volume_24h_usd": vol24,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "universe_rank": rank,
        "coingecko_link": None,
        "watch_score_market_only": 0.0,
        "watch_reasons_market_only": [],
        "revival_score_verified": 0.0,
        "revival_score_components": {},
        "revival_score_reasons": ["DISCOVERY_EXPANSION_ABSORPTION_ONLY"],
        "revival_evidence_coverage_pct": 55,
        "previous_snapshot_at": None,
        "watch_status": "ABSORPTION_WATCH_DISCOVERY_EXPANSION",
        "holder_growth_verified": None,
        "concentration_change_verified": None,
        "smart_money_verified": None,
        "fundamental_evidence_verified": None,
        "pre_alpha_eligible": False,
        "pre_alpha_blocker": "DISCOVERY_EXPANSION_RESEARCH_ONLY_REQUIRES_FULL_VERIFICATION",
        "pair_age_days": None if age is None else round(age, 2),
        "order_flow_absorption": flow,
        "watch_triggers": ["SELL_COUNT_ABSORPTION_PROXY", "DISCOVERY_STATE_EXPANSION"],
        "research_watch_eligible": True,
        "t0": {
            "first_seen_at": now,
            "t0_price_usd": n(pair.get("priceUsd")),
            "t0_rank": rank,
            "network": NETWORK,
            "token_address": token,
            "last_seen_at": now,
            "last_dex_pair_address": str(pair.get("pairAddress") or ""),
            "last_dex_pair_liquidity_usd": liq,
            "last_dex_pair_volume_24h_usd": vol24,
            "last_revival_score_verified": 0.0,
        },
    }


def main() -> None:
    if not LATEST.exists():
        raise SystemExit("REVIVAL_EXPANSION_LATEST_MISSING")
    payload = json.loads(LATEST.read_text())
    coins = payload.get("coins") or []
    base_count = len(coins)
    existing = {str(x.get("token_address") or "") for x in coins}
    known = load_known_solana_tokens()
    scan_tokens = [t for t in known if t not in existing]
    pair_map, failures = fetch_pairs_for_tokens(scan_tokens)
    added, rejected_age, rejected_asset = [], 0, 0
    for token in scan_tokens:
        pair = pair_map.get(token)
        if not pair:
            continue
        age = pair_age_days(pair)
        if age is None or age < MIN_AGE_DAYS:
            rejected_age += 1
            continue
        if not discovery_asset_allowed(token, pair):
            rejected_asset += 1
            continue
        flow = compute_absorption_proxy({"change_24h_pct": n((pair.get("priceChange") or {}).get("h24"))}, pair)
        if flow.get("signal") is True:
            added.append(to_candidate(token, pair, flow, base_count + len(added) + 1))
    coins.extend(added)
    payload["coins"] = coins
    payload["mode"] = MODE
    payload["candidate_cap"] = None
    payload["universe_definition"] = (
        "COINGECKO SOLANA-ONLY BASE PLUS ALL CURRENT ABSORPTION-SIGNAL TOKENS FROM THE PERSISTED SOLANA REVIVAL DISCOVERY STATE; NO FIXED TOTAL CANDIDATE CAP; DISCOVERY PAIRS MUST BE AT LEAST 180 DAYS OLD"
    )
    payload["discovery_expansion_contract"] = {
        "version": "REVIVAL_DISCOVERY_ABSORPTION_EXPANSION_V1",
        "research_only": True,
        "production_portfolio_impact": "NONE",
        "known_solana_tokens": len(known),
        "tokens_scanned_outside_base": len(scan_tokens),
        "minimum_pair_age_days": MIN_AGE_DAYS,
        "cross_platform_status": "UNKNOWN_FOR_DISCOVERY_EXPANSION; PRE_ALPHA_FORBIDDEN",
        "stable_and_obvious_pegged_assets": "EXCLUDED",
        "fixed_candidate_cap": None,
    }
    counts = payload.setdefault("counts", {})
    counts["base_sol_only_universe"] = base_count
    counts["discovery_state_solana_known"] = len(known)
    counts["discovery_state_outside_base_scanned"] = len(scan_tokens)
    counts["absorption_discovery_expansion_added"] = len(added)
    counts["universe"] = len(coins)
    counts["absorption_proxy_watch"] = sum(1 for x in coins if (x.get("order_flow_absorption") or {}).get("signal") is True)
    counts["discovery_expansion_rejected_age"] = rejected_age
    counts["discovery_expansion_rejected_asset"] = rejected_asset
    payload["source"] = str(payload.get("source") or "") + "+revival_discovery_state_absorption_expansion"
    if failures:
        payload.setdefault("failures", []).append({
            "failure_code": "DISCOVERY_EXPANSION_PARTIAL_DEX_BATCH_FAILURE",
            "severity": "NON_BLOCKING_RESEARCH_LAYER",
            "blocks_production": False,
            "batches": failures,
        })
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({
        "known_solana": len(known),
        "outside_base_scanned": len(scan_tokens),
        "added_absorption": len(added),
        "combined_universe": len(coins),
        "batch_failures": len(failures),
    }))


if __name__ == "__main__":
    main()
