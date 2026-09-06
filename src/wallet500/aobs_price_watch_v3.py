from __future__ import annotations

import argparse
import time

import aobs_price_watch_v2 as v2

RPC_MIN_INTERVAL_SECONDS = 0.55
_last_rpc_started = 0.0
_original_rpc = v2._rpc


def _throttled_rpc(method: str, params: list, timeout: int = 25, attempts: int = 3):
    """Respect Robinhood public-RPC rate limits during the one-time holder baseline."""
    global _last_rpc_started
    now = time.monotonic()
    wait = RPC_MIN_INTERVAL_SECONDS - (now - _last_rpc_started)
    if wait > 0:
        time.sleep(wait)
    _last_rpc_started = time.monotonic()
    return _original_rpc(method, params, timeout=timeout, attempts=attempts)


def run() -> dict:
    # AOBS is <1 day old; 30h keeps a conservative pre-launch buffer while
    # avoiding unnecessary public-RPC load. An incomplete baseline fails closed
    # because v2 rejects any Transfer ledger that goes negative.
    v2.BASELINE_LOOKBACK_HOURS = 30
    v2._rpc = _throttled_rpc
    return v2.run()


def self_test() -> None:
    v2.base.self_test()
    v2.self_test()
    assert RPC_MIN_INTERVAL_SECONDS >= 0.5
    assert v2.BASELINE_LOOKBACK_HOURS >= 24
    print("AOBS holder RPC throttle self-test: OK")


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
