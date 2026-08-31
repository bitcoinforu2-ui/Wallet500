from __future__ import annotations

import json
import time
from urllib.parse import quote

from wallet500 import revival_1000 as core

MODE = "RESEARCH_ONLY_REVIVAL_SOLANA_ALL_V5"
PER_PAGE = 250


def fetch_page(url: str, headers: dict) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            batch = core.fetch_json(url, headers=headers, timeout=30)
            if not isinstance(batch, list):
                raise RuntimeError("CoinGecko response is not a list")
            return batch
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"CoinGecko page failed after retries: {last_error}")


def fetch_coingecko_all() -> tuple[list[dict], int]:
    """Read the Solana ecosystem feed to exhaustion; no fixed candidate cap."""
    headers = core.coingecko_headers()
    solana_contracts = core.fetch_solana_only_contracts(headers)
    out: list[dict] = []
    page = 1
    pages_read = 0
    fingerprints: set[tuple[str, ...]] = set()

    while True:
        url = (
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
            "&category=solana-ecosystem&order=market_cap_desc"
            f"&per_page={PER_PAGE}&page={page}&sparkline=false"
            "&price_change_percentage=7d,30d"
        )
        batch = fetch_page(url, headers)
        pages_read += 1
        if not batch:
            break

        fingerprint = tuple(str(x.get("id") or "") for x in batch)
        if fingerprint in fingerprints:
            raise RuntimeError(f"CoinGecko repeated page detected at page={page}")
        fingerprints.add(fingerprint)

        out.extend(x for x in batch if str(x.get("id") or "") in solana_contracts)
        if len(batch) < PER_PAGE:
            break
        page += 1
        time.sleep(1.5)

    rows: list[dict] = []
    seen: set[str] = set()
    for x in out:
        coin_id = str(x.get("id") or "")
        if not coin_id or coin_id in seen or core.is_stable_like(x) or core.is_pegged_or_derivative_like(x):
            continue
        token_address = solana_contracts.get(coin_id)
        if not core.looks_like_solana_address(token_address):
            continue
        seen.add(coin_id)
        ath = x.get("ath")
        price = x.get("current_price")
        dd = None
        if ath and price is not None and float(ath) > 0:
            dd = (1.0 - float(price) / float(ath)) * 100.0
        rows.append({
            "source": "coingecko",
            "network": core.NETWORK,
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

    rows.sort(key=lambda x: (x.get("market_cap_usd") is None, -core.n(x.get("market_cap_usd"))))

    dex_pairs = core.fetch_dex_pair_map([str(x.get("token_address") or "") for x in rows])
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
    return rows, pages_read


def main() -> None:
    failures: list[dict] = []
    try:
        rows, pages_read = fetch_coingecko_all()
    except Exception as exc:
        failures.append({
            "failure_code": "REVIVAL_SOLANA_FULL_UNIVERSE_SOURCE_FAILED",
            "source": "coingecko",
            "severity": "BLOCKING",
            "blocks_production": False,
            "actual": f"{type(exc).__name__}: {exc}",
            "diagnosed_at": core.now_iso(),
        })
        raise SystemExit("REVIVAL_SOLANA_FULL_UNIVERSE_SOURCE_FAILED")

    if len(rows) < 100:
        raise SystemExit(f"REVIVAL_SOLANA_INSUFFICIENT_VERIFIED_UNIVERSE:{len(rows)}")

    # core.build historically slices by MAX_CANDIDATES. Set it to the observed
    # source size so there is no predetermined universe ceiling.
    core.MAX_CANDIDATES = len(rows)
    payload = core.build(
        rows,
        "coingecko_complete_pagination+dexscreener_pair_resolution+previous_snapshot_survival",
        failures,
    )
    payload["mode"] = MODE
    payload["source_pagination_complete"] = True
    payload["source_pages_read"] = pages_read
    payload["candidate_cap"] = None
    payload["universe_definition"] = (
        "ALL_SOLANA_ONLY_PLATFORM_ASSETS_RETURNED_BY_COMPLETE_SOLANA_ECOSYSTEM_FEED_PAGINATION; "
        "ANY OTHER ACTIVE PLATFORM ADDRESS, STABLE, WRAPPED, PEGGED, STAKED, LP OR TOKENIZED RECEIPT IS EXCLUDED"
    )
    core.LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({
        "mode": MODE,
        "network": core.NETWORK,
        "source_pages_read": pages_read,
        "candidate_cap": None,
        **payload["counts"],
        "failures": len(failures),
    }))


if __name__ == "__main__":
    main()
