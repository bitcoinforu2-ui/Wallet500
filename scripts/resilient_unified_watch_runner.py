from __future__ import annotations

import json
import time
from pathlib import Path

import resilient_http
import unified_watch_engine as engine

ROOT = Path(__file__).resolve().parents[1]
HTTP_STATE = ROOT / "data/http-resilience-state.json"


def resilient_http_json(url):
    return resilient_http.request_json(
        url,
        timeout=20,
        attempts=5,
        cache_ttl=20,
        user_agent="Wallet500-UnifiedWatch/2.0",
    )


def main():
    # Give the previous collector stage a short quiet period, then use a
    # process-shared per-host rate limiter and 429/5xx exponential backoff.
    time.sleep(4)
    engine.http_json = resilient_http_json
    rc = engine.main()
    HTTP_STATE.write_text(json.dumps({
        "version": 1,
        "updated_at": engine.now_iso(),
        "component": "unified_watch",
        "metrics": resilient_http.metrics(),
    }, indent=2, ensure_ascii=False) + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
