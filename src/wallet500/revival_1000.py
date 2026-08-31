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
MODE = "RESEARCH_ONLY_REVIVAL_SOLANA_500_V4"
NETWORK = "solana"
MAX_CANDIDATES = 500
DEX_BATCH_SIZE = 30
BASE58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

# Stable-value assets do not belong in Revival research: their intended price
# behavior is fundamentally different from the drawdown/revival behavior we
# are trying to learn. Keep both exact known identifiers and conservative
# symbol/name heuristics so wrapped/bridged stable variants are also removed.
STABLE_IDS = {
    "tether", "usd-coin", "dai", "usds", "usd1-wlfi", "ethena-usde",
    "paypal-usd", "first-digital-usd", "true-usd", "pax-dollar",
    "gemini-dollar", "frax", "liquity-usd", "crvusd", "usdd", "usdb",
    "usual-usd", "usual-usd0", "usd0-liquid-bond", "eurc", "stasis-eurs",
}
STABLE_SYMBOLS = {
    "USDT", "USDC", "DAI", "USDS", "USD1", "USDE", "PYUSD", "FDUSD",
    "TUSD", "USDP", "GUSD", "FRAX", "LUSD", "CRVUSD", "USDD", "USDB",
    "USDX", "USD0", "USDY", "EURC", "EURS", "EURCV",
}

# Wrapped, pegged, liquid-staking, LP and tokenized receipt assets are not part
# of the native Solana Revival universe. Exact symbols cover common cases and
# the name rules provide a conservative second line of defence.
PEGGED_DERIVATIVE_SYMBOLS = {
    "WBTC", "CBBTC", "TBTC", "LBTC", "SOLVBTC", "WSOL",
    "BNSOL", "JITOSOL", "JUPSOL", "MSOL", "STSOL", "VSOL",
    "JLP", "SUSDE", "SYRUPUSDC", "USYC", "USTB", "BUILD",
}
PEGGED_DERIVATIVE_NAME_TERMS = (
    "wrapped ",
    "wrapped bitcoin",
    "wrapped btc",
    "bridged ",
    "wormhole",
    "portal token",
    "staked sol",
    "staked usd",
    "liquid staked",
    "liquid staking",
    "restaked",
    "liquidity provider token",
    "liquidity provider",
    "lp token",
    "yield bearing",
    "yield-bearing",
    "tokenized treasury",
    "tokenized fund",
    "government securities fund",
    "institutional digital liquidity fund",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, headers: dict | None = None, timeout: int = 25):
    req = Request(url, headers={"User-Agent": "Wallet500/1.0", **(headers or {})})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def coingecko_headers() -> dict:
    key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    return {"x-cg-demo-api-key": key} if key else {}


def is_stable_like(x: dict) -> bool:
    coin_id = str(x.get("id") or "").strip().lower()
    symbol = str(x.get("symbol") or "").strip().upper()
    name = str(x.get("name") or "").strip().lower()
    compact = "".join(ch for ch in symbol if ch.isalnum())
    if coin_id in STABLE_IDS or symbol in STABLE_SYMBOLS:
        return True
    if compact in STABLE_SYMBOLS:
        return True
    if len(compact) <= 10 and (compact.startswith("USD") or compact.endswith("USD")):
        return True
    if "stablecoin" in name or "stable coin" in name:
        return True
    return False


def is_pegged_or_derivative_like(x: dict) -> bool:
    """Conservatively reject wrapped/pegged/receipt/tokenized representations."""
    symbol = str(x.get("symbol") or "").strip().upper()
    name = str(x.get("name") or "").strip().lower()
    if symbol in PEGGED_DERIVATIVE_SYMBOLS:
        return True
    return any(term in name for term in PEGGED_DERIVATIVE_NAME_TERMS)


def active_platforms(platforms: dict | None) -> set[str]:
    """Return CoinGecko platform keys that actually expose a non-empty address."""
    if not isinstance(platforms, dict):
        return set()
    return {str(k).strip().lower() for k, v in platforms.items() if str(v or "").strip()}


def has_solana_only_platform(platforms: dict | None) -> bool:
    """Strict footprint rule: a listed asset must expose only a Solana contract."""
    return active_platforms(platforms) == {"solana"}


def looks_like_solana_address(value: object) -> bool:
    """Basic structural validation for a base58 Solana mint/account address."""
    s = str(value or "").strip()
    return 32 <= len(s) <= 44 and all(ch in BASE58 for ch in s)


def fetch_solana_only_contracts(headers: dict) -> dict[str, str]:
    """Return CoinGecko ID -> exact Solana address for Solana-only assets."""
    raw = fetch_json(
        "https://api.coingecko.com/api/v3/coins/list?include_platform=true",
        headers=headers,
    )
    if not isinstance(raw, list):
        raise RuntimeError("CoinGecko coin list is not a list")
    contracts: dict[str, str] = {}
    for x in raw:
        platforms = x.get("platforms") or {}
        if not has_solana_only_platform(platforms):
            continue
        coin_id = str(x.get("id") or "").strip()
        address = str(platforms.get("solana") or "").strip()
        if coin_id and looks_like_solana_address(address):
            contracts[coin_id] = address
    if len(contracts) < 100:
        raise RuntimeError(f"insufficient Solana-only contracts: {len(contracts)}")
    return contracts


def _pair_liquidity_usd(pair: dict) -> float:
    try:
        return float((pair.get("liquidity") or {}).get("usd") or 0)
    except (TypeError, ValueError):
        return 0.0


def _pair_volume_24h_usd(pair: dict) -> float:
    try:
        return float((pair.get("volume") or {}).get("h24") or 0)
    except (TypeError, ValueError):
        return 0.0


def select_best_dex_pair(token_address: str, pairs: list[dict]) -> dict | None:
    """Choose a verified DexScreener Solana pair for the exact token mint."""
    if not looks_like_solana_address(token_address):
        return None
    valid: list[dict] = []
    for pair in pairs or []:
        if str(pair.get("chainId") or "").lower() != NETWORK:
            continue
        base = str((pair.get("baseToken") or {}).get("address") or "")
        quote_addr = str((pair.get("quoteToken") or {}).get("address") or "")
        if token_address not in {base, quote_addr}:
            continue
        pair_address = str(pair.get("pairAddress") or "").strip()
        url = str(pair.get("url") or "").strip()
        if not looks_like_solana_address(pair_address):
            continue
        if not url.startswith("https://dexscreener.com/solana/"):
            continue
        valid.append(pair)
    if not valid:
        return None
    return max(valid, key=lambda p: (_pair_liquidity_usd(p), _pair_volume_24h_usd(p)))


def fetch_dex_pair_map(token_addresses: list[str]) -> dict[str, dict]:
    """Resolve exact token mints to verified DexScreener pair URLs in batches."""
    unique = list(dict.fromkeys(a for a in token_addresses if looks_like_solana_address(a)))
    result: dict[str, dict] = {}
    for start in range(0, len(unique), DEX_BATCH_SIZE):
        batch = unique[start:start + DEX_BATCH_SIZE]
        joined = ",".join(batch)
        try:
            pairs = fetch_json(
                "https://api.dexscreener.com/tokens/v1/solana/" + quote(joined, safe=","),
                timeout=20,
            )
        except Exception:
            # DEX links are convenience metadata, not a market-source truth gate.
            # If DexScreener is temporarily unavailable we keep the asset and show
            # no DEX button instead of manufacturing a broken link.
            continue
        if not isinstance(pairs, list):
            continue
        for token_address in batch:
            best = select_best_dex_pair(token_address, pairs)
            if not best:
                continue
            result[token_address] = {
                "dex_link": str(best.get("url") or "").strip(),
                "dex_pair_address": str(best.get("pairAddress") or "").strip(),
                "dex_id": best.get("dexId"),
                "dex_pair_liquidity_usd": _pair_liquidity_usd(best),
                "dex_pair_volume_24h_usd": _pair_volume_24h_usd(best),
                "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
            }
        if start + DEX_BATCH_SIZE < len(unique):
            time.sleep(0.08)
    return result


def fetch_coingecko() -> list[dict]:
    """Fetch ranked Solana-only assets, excluding stable and pegged/derivative representations."""
    headers = coingecko_headers()
    solana_contracts = fetch_solana_only_contracts(headers)
    out: list[dict] = []

    # Pull a wider source universe so strict identity filtering still leaves up
    # to 500 valid candidates. An asset is rejected if CoinGecko exposes any
    # other active platform address.
    for page in range(1, 5):
        url = (
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
            "&category=solana-ecosystem&order=market_cap_desc"
            f"&per_page=250&page={page}&sparkline=false"
            "&price_change_percentage=7d,30d"
        )
        batch = fetch_json(url, headers=headers)
        if not isinstance(batch, list):
            raise RuntimeError("CoinGecko response is not a list")
        out.extend(x for x in batch if str(x.get("id") or "") in solana_contracts)
        if len(batch) < 250:
            break
        time.sleep(1.2)

    rows = []
    seen: set[str] = set()
    for x in out:
        coin_id = str(x.get("id") or "")
        if not coin_id or coin_id in seen or is_stable_like(x) or is_pegged_or_derivative_like(x):
            continue
        token_address = solana_contracts.get(coin_id)
        if not looks_like_solana_address(token_address):
            continue
        seen.add(coin_id)
        ath = x.get("ath")
        price = x.get("current_price")
        dd = None
        if ath and price is not None and float(ath) > 0:
            dd = (1.0 - float(price) / float(ath)) * 100.0
        rows.append({
            "source": "coingecko",
            "network": NETWORK,
            "network_verified": True,
            "network_verification": "COINGECKO_SOLANA_ONLY_ACTIVE_PLATFORM_FOOTPRINT",
            "solana_only_platform_verified": True,
            "stablecoin_excluded": True,
            "pegged_derivative_excluded": True,
            "id": coin_id,
            "token_address": token_address,
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

    rows.sort(key=lambda x: (x.get("market_cap_usd") is None, -n(x.get("market_cap_usd"))))
    rows = rows[:MAX_CANDIDATES]

    dex_pairs = fetch_dex_pair_map([str(x.get("token_address") or "") for x in rows])
    for x in rows:
        pair = dex_pairs.get(str(x.get("token_address") or ""))
        if pair:
            x.update(pair)
        else:
            x["dex_link"] = None
            x["dex_pair_address"] = None
            x["dex_id"] = None
            x["dex_pair_liquidity_usd"] = None
            x["dex_pair_volume_24h_usd"] = None
            x["dex_link_type"] = "NO_VERIFIED_DEX_PAIR"
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
        return {"version": 4, "network": NETWORK, "first_t0": now_iso(), "coins": {}}
    try:
        state = json.loads(STATE.read_text())
    except Exception:
        state = {"version": 4, "network": NETWORK, "first_t0": now_iso(), "coins": {}}
    state["version"] = 4
    state["network"] = NETWORK
    return state


def build(rows: list[dict], source: str, failures: list[dict]) -> dict:
    ts = now_iso()
    state = load_state()
    coins_state = state.setdefault("coins", {})
    normalized = []
    for i, x in enumerate(rows[:MAX_CANDIDATES], 1):
        if (
            x.get("network") != NETWORK
            or x.get("network_verified") is not True
            or x.get("solana_only_platform_verified") is not True
            or not looks_like_solana_address(x.get("token_address"))
            or is_stable_like(x)
            or is_pegged_or_derivative_like(x)
        ):
            continue
        x["universe_rank"] = len(normalized) + 1
        x["market_cap_rank"] = x.get("market_cap_rank") or x["universe_rank"]
        if x.get("dex_link_type") != "DEXSCREENER_VERIFIED_PAIR":
            x["dex_link"] = None
            x["dex_pair_address"] = None
            x["dex_link_type"] = "NO_VERIFIED_DEX_PAIR"
        x["coingecko_link"] = "https://www.coingecko.com/en/coins/" + str(x.get("id") or "")
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
        st = coins_state.setdefault(
            key,
            {
                "first_seen_at": ts,
                "t0_price_usd": x.get("price_usd"),
                "t0_rank": x["universe_rank"],
                "network": NETWORK,
                "token_address": x.get("token_address"),
            },
        )
        if not st.get("token_address"):
            st["token_address"] = x.get("token_address")
        x["t0"] = st
        normalized.append(x)

    state["last_updated_at"] = ts
    state["coins"] = coins_state
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    core_count = sum(1 for x in normalized if x["watch_status"] != "OUTSIDE_CORE_DRAWDOWN_BAND")
    waking = sum(1 for x in normalized if x["watch_status"] == "WAKING_MARKET_ONLY")
    dex_verified = sum(1 for x in normalized if x.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR")
    return {
        "version": 4,
        "mode": MODE,
        "network": NETWORK,
        "network_filter": "STRICT_SOLANA_ONLY_PLATFORM_FOOTPRINT",
        "asset_filter": "SOLANA_ONLY_PLATFORM_NON_STABLE_NON_PEGGED_ONLY",
        "generated_at": ts,
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "universe_definition": "UP_TO_500_SOLANA_ONLY_PLATFORM_ASSETS_BY_MARKET_CAP_FROM_SOLANA_ECOSYSTEM_FEED; ANY OTHER ACTIVE PLATFORM ADDRESS, STABLE, WRAPPED, PEGGED, STAKED, LP OR TOKENIZED_RECEIPT IS EXCLUDED",
        "source": source,
        "counts": {
            "universe": len(normalized),
            "core_drawdown_watch": core_count,
            "waking_market_only": waking,
            "pre_alpha": 0,
            "dex_verified_pairs": dex_verified,
        },
        "scoring_contract": {
            "market_score_max": 100,
            "stablecoins": "EXCLUDED",
            "wrapped_pegged_derivatives": "EXCLUDED",
            "cross_platform_assets": "EXCLUDED",
            "dex_links": "EXACT_VERIFIED_PAIR_URL_OR_NONE",
            "holder_growth": "PENDING_VERIFIED_SOURCE",
            "concentration_decline": "PENDING_VERIFIED_SOURCE",
            "fundamentals_product_community": "PENDING_VERIFIED_SOURCE",
            "rule": "MISSING_EVIDENCE_NEVER_IMPUTED_AS_TRUE",
        },
        "failures": failures,
        "coins": normalized,
    }


def main() -> None:
    failures = []
    try:
        rows = fetch_coingecko()
    except Exception as e:
        failures.append({
            "failure_code": "REVIVAL_SOLANA_UNIVERSE_SOURCE_FAILED",
            "source": "coingecko",
            "severity": "BLOCKING",
            "blocks_production": False,
            "actual": f"{type(e).__name__}: {e}",
            "diagnosed_at": now_iso(),
        })
        raise SystemExit("REVIVAL_SOLANA_NO_VERIFIED_MARKET_SOURCE")

    if len(rows) < 100:
        raise SystemExit(f"REVIVAL_SOLANA_INSUFFICIENT_VERIFIED_UNIVERSE:{len(rows)}")
    payload = build(rows, "coingecko+dexscreener_pair_resolution", failures)
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"mode": MODE, "network": NETWORK, "source": payload["source"], **payload["counts"], "failures": len(failures)}))


if __name__ == "__main__":
    main()
