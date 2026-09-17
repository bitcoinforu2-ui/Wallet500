from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path

import resilient_http
import unified_watch_engine as engine

ROOT = Path(__file__).resolve().parents[1]
HTTP_STATE = ROOT / "data/http-resilience-state.json"


def resilient_http_json(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    if host == "api.geckoterminal.com":
        # Exact-pair consensus remains mandatory, but 429 itself is fail-closed.
        # A 429 installs a shared 15s cooldown for subsequent targets instead of
        # retrying the same target repeatedly and amplifying throttling.
        return resilient_http.request_json(
            url,
            timeout=20,
            attempts=1,
            cache_ttl=15,
            min_interval=4.0,
            user_agent="Wallet500-UnifiedWatch/3.0",
        )
    return resilient_http.request_json(
        url,
        timeout=20,
        attempts=3,
        cache_ttl=15,
        user_agent="Wallet500-UnifiedWatch/3.0",
    )


def main():
    # Give the previous collector stage a short quiet period, then use a
    # process-shared per-host limiter/cooldown. Exact identity/spread checks in
    # unified_watch_engine are intentionally unchanged and remain fail-closed.
    time.sleep(4)
    engine.http_json = resilient_http_json
    rc = engine.main()
    HTTP_STATE.write_text(json.dumps({
        "version": 2,
        "updated_at": engine.now_iso(),
        "component": "unified_watch",
        "strategy": "STRICT_EXACT_PAIR_4S_GECKO_PACING_429_CIRCUIT_BREAKER_NO_RETRY_STORM",
        "metrics": resilient_http.metrics(),
    }, indent=2, ensure_ascii=False) + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
