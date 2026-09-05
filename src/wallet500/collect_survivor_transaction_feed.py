from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
OUT = DATA / "wallet-transaction-observations.json"
BITQUERY_ENDPOINT = os.getenv("BITQUERY_ENDPOINT", "").strip() or "https://streaming.bitquery.io/graphql"
NETWORK = {
    "solana": "Solana",
    "ethereum": "Ethereum",
    "eth": "Ethereum",
    "bsc": "Binance Smart Chain",
    "bnb": "Binance Smart Chain",
}


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def norm(value) -> str:
    return str(value or "").strip().lower()


def gql_string(value: str) -> str:
    return json.dumps(str(value))


def pair_query(network: str, pair: str, hours: int = 1, limit: int = 500) -> str:
    """Query Bitquery Trading.Trades for one exact pool.

    Pair.Pool.Address is the portable exact-pool key on both Solana and EVM.
    Pair.Market.Address is intentionally NOT used as the pool key: on EVM it
    can identify the protocol factory instead of the pool and may silently
    return a different pool's trades.
    """
    return f'''query {{
  Trading {{
    Trades(
      limit: {{count: {int(limit)}}}
      orderBy: {{descending: Block_Time}}
      where: {{
        Block: {{Time: {{since_relative: {{hours_ago: {int(hours)}}}}}}}
        Pair: {{
          Pool: {{Address: {{is: {gql_string(pair)}}}}}
          Market: {{Network: {{is: {gql_string(network)}}}}}
        }}
      }}
    ) {{
      Side
      Block {{ Time }}
      Trader {{ Address }}
      AmountsInUsd {{ Base Quote }}
      Pair {{
        Token {{ Address Symbol }}
        QuoteToken {{ Address Symbol }}
        Pool {{ Address Id }}
        Market {{ Address Network Program Protocol }}
      }}
      TransactionHeader {{ Hash }}
    }}
  }}
}}'''


def bitquery(query: str, token: str) -> dict:
    body = json.dumps({"query": query}).encode()
    req = Request(
        BITQUERY_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Wallet500/exact-pair-transaction-collector-v2",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if payload.get("errors"):
        raise RuntimeError("BITQUERY_GRAPHQL_ERROR:" + json.dumps(payload["errors"])[:1000])
    return payload.get("data") or {}


def normalize_trade(trade: dict, watch_row: dict) -> dict | None:
    pair = trade.get("Pair") or {}
    pool = pair.get("Pool") or {}
    market = pair.get("Market") or {}
    expected_pair = norm(watch_row.get("pair_address"))
    if norm(pool.get("Address")) != expected_pair:
        return None
    token = pair.get("Token") or {}
    quote = pair.get("QuoteToken") or {}
    target = norm(watch_row.get("token"))
    base_addr = norm(token.get("Address"))
    quote_addr = norm(quote.get("Address"))
    side = str(trade.get("Side") or "").upper()
    amounts = trade.get("AmountsInUsd") or {}
    if target == base_addr:
        usd = amounts.get("Base")
        target_side = side
    elif target == quote_addr:
        usd = amounts.get("Quote")
        target_side = "SELL" if side == "BUY" else "BUY" if side == "SELL" else side
    else:
        return None
    try:
        usd_value = float(usd)
    except (TypeError, ValueError):
        return None
    trader = str((trade.get("Trader") or {}).get("Address") or "").strip()
    tx_hash = str((trade.get("TransactionHeader") or {}).get("Hash") or "").strip()
    if target_side not in {"BUY", "SELL"} or not trader or not tx_hash or usd_value < 0:
        return None
    return {
        "tx_hash": tx_hash,
        "timestamp": (trade.get("Block") or {}).get("Time"),
        "wallet": trader,
        "side": target_side,
        "usd_value": usd_value,
        "verified_swap": True,
        "pair_address": watch_row.get("pair_address"),
        "token": watch_row.get("token"),
        "source": "BITQUERY_TRADING_TRADES_V2",
        "pool_address_verified": pool.get("Address"),
        "pool_id": pool.get("Id"),
        "market_address": market.get("Address"),
        "market_program": market.get("Program"),
        "market_protocol": market.get("Protocol"),
    }


def collect_row(row: dict, token: str, hours: int, limit: int) -> dict:
    chain = norm(row.get("chain"))
    network = NETWORK.get(chain)
    pair = str(row.get("pair_address") or "").strip()
    target = str(row.get("token") or "").strip()
    if not network or not pair or not target:
        return {
            "chain": row.get("chain"), "token": target, "pair_address": pair,
            "source": "BITQUERY_TRADING_TRADES_V2", "coverage": "UNSUPPORTED_OR_MISSING_IDENTITY", "transactions": [],
        }
    query_pair = pair.lower() if chain in {"ethereum", "eth", "bsc", "bnb"} else pair
    try:
        data = bitquery(pair_query(network, query_pair, hours=hours, limit=limit), token)
        trades = ((data.get("Trading") or {}).get("Trades") or [])
        transactions = []
        for trade in trades:
            x = normalize_trade(trade, row)
            if x:
                transactions.append(x)
        # Bitquery recommends composite deduplication for Trading.Trades. A
        # transaction can legitimately contain more than one swap leg, so tx
        # hash alone is too aggressive and can erase real activity.
        dedup = {}
        for x in transactions:
            key = (x["tx_hash"], norm(x["wallet"]), x["side"], round(float(x["usd_value"]), 8))
            dedup[key] = x
        transactions = list(dedup.values())
        return {
            "chain": row.get("chain"), "token": target, "pair_address": pair,
            "source": "BITQUERY_TRADING_TRADES_V2",
            "coverage": "VERIFIED_EXACT_PAIR_SWAP_FEED" if transactions else "NO_MATCHING_TRADES_IN_WINDOW",
            "queried_network": network,
            "pool_identity_field": "Pair.Pool.Address",
            "window_hours": hours,
            "transactions": transactions,
        }
    except Exception as exc:
        return {
            "chain": row.get("chain"), "token": target, "pair_address": pair,
            "source": "BITQUERY_TRADING_TRADES_V2", "coverage": "PROVIDER_ERROR",
            "pool_identity_field": "Pair.Pool.Address",
            "error": str(exc)[:1000], "transactions": [],
        }


def main():
    watch = load(WATCH, {})
    if not watch:
        raise SystemExit("SURVIVOR_WATCH_OUTPUT_MISSING")
    access_token = os.getenv("BITQUERY_TOKEN", "").strip()
    try:
        hours = max(1, min(6, int(os.getenv("WALLET500_TX_WINDOW_HOURS", "1"))))
    except ValueError:
        hours = 1
    try:
        limit = max(50, min(1000, int(os.getenv("WALLET500_TX_LIMIT_PER_PAIR", "500"))))
    except ValueError:
        limit = 500

    observed_at = datetime.now(timezone.utc).isoformat()
    if not access_token:
        payload = {
            "version": 2,
            "observed_at": observed_at,
            "provider": "BITQUERY_TRADING_TRADES_V2",
            "provider_status": "BITQUERY_TOKEN_MISSING",
            "exact_pair_only": True,
            "pool_identity_field": "Pair.Pool.Address",
            "tokens": [],
        }
        dump(OUT, payload)
        print(json.dumps({"provider_status": "BITQUERY_TOKEN_MISSING", "tokens": 0}))
        return

    rows = [collect_row(row, access_token, hours, limit) for row in watch.get("tokens") or []]
    payload = {
        "version": 2,
        "observed_at": observed_at,
        "provider": "BITQUERY_TRADING_TRADES_V2",
        "provider_status": "OK" if all(x.get("coverage") != "PROVIDER_ERROR" for x in rows) else "PARTIAL_PROVIDER_ERRORS",
        "exact_pair_only": True,
        "pool_identity_field": "Pair.Pool.Address",
        "tokens": rows,
    }
    dump(OUT, payload)
    print(json.dumps({
        "provider_status": payload["provider_status"],
        "tokens": len(rows),
        "tokens_with_swaps": sum(1 for x in rows if x.get("transactions")),
        "verified_swaps": sum(len(x.get("transactions") or []) for x in rows),
    }))


if __name__ == "__main__":
    main()
