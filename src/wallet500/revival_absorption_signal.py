from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from wallet500.revival_1000 import looks_like_solana_address

DATA = Path("data")
LATEST = DATA / "revival-1000-latest.json"
NETWORK = "solana"
DEX_BATCH_SIZE = 30

# Research-only gate. It is deliberately conservative and never promotes a coin
# to PRE-ALPHA/production. DexScreener exposes buy/sell transaction counts but
# not verified buy-vs-sell USD notional, so this is explicitly a proxy signal.
MIN_LIQUIDITY_USD = 50_000.0
MIN_VOLUME_24H_USD = 10_000.0
MIN_TXNS_24H = 40
MIN_VOLUME_TO_LIQUIDITY = 0.05
MAX_SELL_BUY_COUNT_RATIO = 2.0


def n(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fetch_json(url: str, timeout: int = 20):
    req = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Wallet500/1.0"},
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def exact_pair_for_coin(coin: dict, pairs: list[dict]) -> dict | None:
    """Resolve only the already-verified immutable pair; never switch pools."""
    wanted_pair = str(coin.get("dex_pair_address") or "").strip().lower()
    token = str(coin.get("token_address") or "").strip()
    if not wanted_pair or not looks_like_solana_address(token):
        return None

    for pair in pairs or []:
        if str(pair.get("chainId") or "").lower() != NETWORK:
            continue
        if str(pair.get("pairAddress") or "").strip().lower() != wanted_pair:
            continue
        base = str((pair.get("baseToken") or {}).get("address") or "")
        quote_token = str((pair.get("quoteToken") or {}).get("address") or "")
        if token not in {base, quote_token}:
            continue
        return pair
    return None


def compute_absorption_proxy(coin: dict, pair: dict | None) -> dict:
    """Detect sell-count dominance being absorbed while price/activity stay constructive.

    IMPORTANT: this does not claim buy USD volume > sell USD volume. The current
    DexScreener pair feed does not expose verified directional USD notional.
    """
    if not pair:
        return {
            "signal": False,
            "signal_type": "DATA_UNAVAILABLE",
            "research_only": True,
            "exact_buy_sell_notional_verified": False,
            "buy_volume_24h_usd": None,
            "sell_volume_24h_usd": None,
            "notional_volume_note": "DIRECTIONAL_USD_NOTIONAL_NOT_EXPOSED_BY_CURRENT_DEXSCREENER_PAIR_FEED",
        }

    txns = pair.get("txns") or {}
    h24_tx = txns.get("h24") or {}
    h6_tx = txns.get("h6") or {}
    h1_tx = txns.get("h1") or {}
    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}
    liquidity = pair.get("liquidity") or {}

    buys_h24 = int(n(h24_tx.get("buys")))
    sells_h24 = int(n(h24_tx.get("sells")))
    buys_h6 = int(n(h6_tx.get("buys")))
    sells_h6 = int(n(h6_tx.get("sells")))
    buys_h1 = int(n(h1_tx.get("buys")))
    sells_h1 = int(n(h1_tx.get("sells")))
    txns_h24 = buys_h24 + sells_h24

    liquidity_usd = max(n(liquidity.get("usd")), 0.0)
    volume_24h_usd = max(n(volume.get("h24")), 0.0)
    volume_to_liquidity = volume_24h_usd / liquidity_usd if liquidity_usd > 0 else 0.0
    price_change_h24 = n(price_change.get("h24"), n(coin.get("change_24h_pct")))
    price_change_h6 = n(price_change.get("h6"))
    price_change_h1 = n(price_change.get("h1"))
    sell_buy_ratio = sells_h24 / buys_h24 if buys_h24 > 0 else None

    criteria = {
        "sell_count_gt_buy_count": sells_h24 > buys_h24 and buys_h24 > 0,
        "sell_buy_count_ratio_le_2": sell_buy_ratio is not None and sell_buy_ratio <= MAX_SELL_BUY_COUNT_RATIO,
        "liquidity_ge_50k": liquidity_usd >= MIN_LIQUIDITY_USD,
        "volume_24h_ge_10k": volume_24h_usd >= MIN_VOLUME_24H_USD,
        "txns_24h_ge_40": txns_h24 >= MIN_TXNS_24H,
        "volume_to_liquidity_ge_5pct": volume_to_liquidity >= MIN_VOLUME_TO_LIQUIDITY,
        "price_change_24h_positive": price_change_h24 > 0,
    }
    signal = all(criteria.values())

    score = 0
    if criteria["sell_count_gt_buy_count"]:
        score += 25
    if criteria["sell_buy_count_ratio_le_2"]:
        score += 10
    if criteria["liquidity_ge_50k"]:
        score += 15
    if criteria["volume_24h_ge_10k"]:
        score += 10
    if criteria["txns_24h_ge_40"]:
        score += 10
    if criteria["volume_to_liquidity_ge_5pct"]:
        score += 10
    if criteria["price_change_24h_positive"]:
        score += 10
    if price_change_h6 > 0:
        score += 5
    if price_change_h1 >= -5:
        score += 5

    return {
        "signal": signal,
        "signal_type": "SELL_COUNT_ABSORPTION_PROXY" if signal else "NONE",
        "research_only": True,
        "score": min(100, score),
        "pair_address": pair.get("pairAddress"),
        "buys_h24": buys_h24,
        "sells_h24": sells_h24,
        "buys_h6": buys_h6,
        "sells_h6": sells_h6,
        "buys_h1": buys_h1,
        "sells_h1": sells_h1,
        "sell_buy_count_ratio_h24": None if sell_buy_ratio is None else round(sell_buy_ratio, 4),
        "liquidity_usd": round(liquidity_usd, 2),
        "volume_24h_usd": round(volume_24h_usd, 2),
        "volume_to_liquidity": round(volume_to_liquidity, 4),
        "price_change_h24_pct": round(price_change_h24, 4),
        "price_change_h6_pct": round(price_change_h6, 4),
        "price_change_h1_pct": round(price_change_h1, 4),
        "criteria": criteria,
        "exact_buy_sell_notional_verified": False,
        "buy_volume_24h_usd": None,
        "sell_volume_24h_usd": None,
        "notional_volume_note": "DIRECTIONAL_USD_NOTIONAL_NOT_EXPOSED_BY_CURRENT_DEXSCREENER_PAIR_FEED",
    }


def fetch_exact_pairs(coins: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    eligible = [
        coin for coin in coins
        if coin.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
        and looks_like_solana_address(coin.get("token_address"))
        and str(coin.get("dex_pair_address") or "").strip()
    ]
    pair_map: dict[str, dict] = {}
    failures: list[dict] = []

    for start in range(0, len(eligible), DEX_BATCH_SIZE):
        batch = eligible[start:start + DEX_BATCH_SIZE]
        addresses = [str(coin.get("token_address")) for coin in batch]
        try:
            pairs = fetch_json(
                "https://api.dexscreener.com/tokens/v1/solana/" + quote(",".join(addresses), safe=","),
                timeout=20,
            )
            if not isinstance(pairs, list):
                raise RuntimeError("DexScreener batch response is not a list")
        except Exception as exc:
            failures.append({
                "batch_start": start,
                "batch_size": len(batch),
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        for coin in batch:
            pair = exact_pair_for_coin(coin, pairs)
            if pair:
                pair_map[str(coin.get("dex_pair_address")).lower()] = pair
        if start + DEX_BATCH_SIZE < len(eligible):
            time.sleep(0.08)

    return pair_map, failures


def apply_absorption_layer(payload: dict, pair_map: dict[str, dict], failures: list[dict] | None = None) -> dict:
    coins = payload.get("coins") or []
    signal_count = 0
    outside_core_count = 0
    unavailable_count = 0

    for coin in coins:
        pair_key = str(coin.get("dex_pair_address") or "").strip().lower()
        pair = pair_map.get(pair_key)
        signal = compute_absorption_proxy(coin, pair)
        coin["order_flow_absorption"] = signal

        triggers = list(coin.get("watch_triggers") or [])
        if signal.get("signal") is True:
            signal_count += 1
            if signal["signal_type"] not in triggers:
                triggers.append(signal["signal_type"])
            coin["watch_triggers"] = triggers
            coin["research_watch_eligible"] = True
            coin["pre_alpha_eligible"] = False

            old_status = str(coin.get("watch_status") or "")
            coin["watch_status_before_absorption"] = old_status
            if old_status != "WAKING_MARKET_ONLY":
                coin["watch_status"] = "ABSORPTION_WATCH"
            if old_status == "OUTSIDE_CORE_DRAWDOWN_BAND":
                outside_core_count += 1
        elif signal.get("signal_type") == "DATA_UNAVAILABLE":
            unavailable_count += 1

    counts = payload.setdefault("counts", {})
    counts["absorption_proxy_watch"] = signal_count
    counts["absorption_proxy_outside_core"] = outside_core_count
    counts["absorption_pair_data_unavailable"] = unavailable_count

    payload["order_flow_absorption_contract"] = {
        "version": "SELL_COUNT_ABSORPTION_PROXY_V1",
        "research_only": True,
        "production_portfolio_impact": "NONE",
        "pair_identity": "EXISTING_VERIFIED_EXACT_PAIR_ONLY_NO_POOL_SWITCHING",
        "trigger": "SELLS_H24_GT_BUYS_H24_WITH_POSITIVE_24H_PRICE_AND_HEALTHY_LIQUIDITY_ACTIVITY",
        "minimum_liquidity_usd": MIN_LIQUIDITY_USD,
        "minimum_volume_24h_usd": MIN_VOLUME_24H_USD,
        "minimum_txns_24h": MIN_TXNS_24H,
        "minimum_volume_to_liquidity": MIN_VOLUME_TO_LIQUIDITY,
        "maximum_sell_buy_count_ratio": MAX_SELL_BUY_COUNT_RATIO,
        "directional_usd_notional": "NOT_AVAILABLE_FROM_CURRENT_DEXSCREENER_PAIR_FEED",
        "truth_rule": "PROXY_NEVER_CLAIMS_BUY_USD_VOLUME_GT_SELL_USD_VOLUME_WITHOUT_A_VERIFIED_DIRECTIONAL_NOTIONAL_SOURCE",
        "pre_alpha_promotion": "FORBIDDEN",
        "revival_score_mutation": "NONE",
    }
    if failures:
        payload.setdefault("failures", []).append({
            "failure_code": "ABSORPTION_PROXY_PARTIAL_PAIR_REFRESH_FAILURE",
            "severity": "NON_BLOCKING_RESEARCH_LAYER",
            "blocks_production": False,
            "batches": failures,
        })
    payload["source"] = str(payload.get("source") or "") + "+dexscreener_sell_count_absorption_proxy"
    return payload


def main() -> None:
    if not LATEST.exists():
        raise SystemExit("REVIVAL_ABSORPTION_LATEST_MISSING")

    payload = json.loads(LATEST.read_text())
    if payload.get("network") != NETWORK:
        raise SystemExit("REVIVAL_ABSORPTION_NETWORK_NOT_SOLANA")
    if payload.get("production_portfolio_impact") != "NONE":
        raise SystemExit("REVIVAL_ABSORPTION_UNSAFE_PRODUCTION_MODE")

    pair_map, failures = fetch_exact_pairs(payload.get("coins") or [])
    payload = apply_absorption_layer(payload, pair_map, failures)
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    counts = payload.get("counts") or {}
    print(json.dumps({
        "absorption_proxy_watch": counts.get("absorption_proxy_watch", 0),
        "absorption_proxy_outside_core": counts.get("absorption_proxy_outside_core", 0),
        "pair_data_unavailable": counts.get("absorption_pair_data_unavailable", 0),
        "batch_failures": len(failures),
    }))


if __name__ == "__main__":
    main()
