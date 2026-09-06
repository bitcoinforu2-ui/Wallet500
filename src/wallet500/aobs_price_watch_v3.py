from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.request

import aobs_price_watch_v2 as v2

RPC_MIN_INTERVAL_SECONDS = 0.55
OPENSEA_URL = f"https://opensea.io/token/robinhood/{v2.base.TOKEN_CA.lower()}"
_last_rpc_started = 0.0
_original_rpc = v2._rpc


def _throttled_rpc(method: str, params: list, timeout: int = 25, attempts: int = 3):
    """Throttle Robinhood public-RPC requests if the deep fallback is used manually."""
    global _last_rpc_started
    now = time.monotonic()
    wait = RPC_MIN_INTERVAL_SECONDS - (now - _last_rpc_started)
    if wait > 0:
        time.sleep(wait)
    _last_rpc_started = time.monotonic()
    return _original_rpc(method, params, timeout=timeout, attempts=attempts)


def _parse_exact_opensea_holders(raw_html: str) -> int | None:
    """Accept only an exact integer tied to a holder-count label/key; never a rounded 1.27K value."""
    patterns = [
        r'"holdersCount"\s*:\s*"?([0-9][0-9,]*)"?',
        r'"holderCount"\s*:\s*"?([0-9][0-9,]*)"?',
        r'"holders_count"\s*:\s*"?([0-9][0-9,]*)"?',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_html, flags=re.IGNORECASE)
        if match:
            try:
                value = int(match.group(1).replace(",", ""))
                return value if value > 0 else None
            except ValueError:
                pass

    text = html.unescape(re.sub(r"<[^>]+>", " ", raw_html))
    text = re.sub(r"\s+", " ", text)
    # Require at least three digits/commas and whitespace after the value so rounded forms like 1.27K are rejected.
    for label in ("Holders", "Holder"):
        match = re.search(rf"\b{label}\s+([0-9][0-9,]{{2,}})(?=\s|$)", text, flags=re.IGNORECASE)
        if match:
            try:
                value = int(match.group(1).replace(",", ""))
                return value if value > 0 else None
            except ValueError:
                pass
    return None


def _fetch_opensea_holder_count(max_attempts: int = 2) -> tuple[int | None, str | None]:
    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(
                OPENSEA_URL,
                headers={
                    "accept": "text/html,application/xhtml+xml",
                    "accept-language": "en-US,en;q=0.9",
                    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 Wallet500/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
            # Identity must be present in the exact-contract page/URL context before accepting the count.
            ca = v2.base.TOKEN_CA.lower()
            if ca not in raw.lower() and ca not in OPENSEA_URL.lower():
                raise RuntimeError("OpenSea exact-contract identity missing")
            count = _parse_exact_opensea_holders(raw)
            if count is None:
                raise RuntimeError("OpenSea page has no exact integer holder count")
            return count, None
        except Exception as exc:
            last_error = str(exc)[:220]
            if attempt < max_attempts:
                time.sleep(attempt)
    return None, last_error


def _verified_holder_source(now):
    """Fast exact-contract holder source stack: Blockscout -> OpenSea. No slow RPC bootstrap in the 5m alert path."""
    block_count, block_url, block_error = v2._fetch_blockscout_holder_count(max_attempts=1)
    if block_count is not None:
        return block_count, "BLOCKSCOUT_EXACT_CONTRACT", block_url, None

    open_count, open_error = _fetch_opensea_holder_count(max_attempts=2)
    if open_count is not None:
        warning = None if not block_error else f"Blockscout unavailable: {block_error}"
        return open_count, "OPENSEA_EXACT_CONTRACT", OPENSEA_URL, warning

    detail = f"Blockscout: {block_error or 'unavailable'} | OpenSea: {open_error or 'unavailable'}"
    return None, None, None, detail[:500]


def run() -> dict:
    # Keep the public RPC implementation available for a future/background deep bootstrap,
    # but do not let it delay or rate-limit the five-minute Telegram price watcher.
    v2.BASELINE_LOOKBACK_HOURS = 30
    v2._rpc = _throttled_rpc
    v2._fetch_verified_holder_count = _verified_holder_source
    return v2.run()


def self_test() -> None:
    v2.base.self_test()
    v2.self_test()
    assert RPC_MIN_INTERVAL_SECONDS >= 0.5
    assert v2.BASELINE_LOOKBACK_HOURS >= 24
    assert _parse_exact_opensea_holders('<div>Holders 1,268 </div>') == 1268
    assert _parse_exact_opensea_holders('<div>Holders 1.27K </div>') is None
    assert _parse_exact_opensea_holders('{"holdersCount":1268}') == 1268
    print("AOBS exact-contract holder-source self-test: OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        run()


if __name__ == "__main__":
    main()
