from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - GitHub runners are Linux
    fcntl = None

CACHE_DIR = Path(tempfile.gettempdir()) / "wallet500-http-cache"
LOCK_DIR = Path(tempfile.gettempdir()) / "wallet500-http-locks"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOCK_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_INTERVALS = {
    "api.geckoterminal.com": 2.15,
    "api.dexscreener.com": 0.35,
    "api.gateio.ws": 0.30,
    "fx-api.gateio.ws": 0.30,
    "fapi.binance.com": 0.35,
    "api.bybit.com": 0.30,
    "www.okx.com": 0.30,
    "api.mainnet-beta.solana.com": 0.25,
    "eth.blockscout.com": 0.25,
    "base.blockscout.com": 0.25,
    "arbitrum.blockscout.com": 0.25,
    "optimism.blockscout.com": 0.25,
    "polygon.blockscout.com": 0.25,
    "bsc.blockscout.com": 0.25,
}

_STATS = {
    "requests": 0,
    "cache_hits": 0,
    "retries": 0,
    "http_429": 0,
    "http_5xx": 0,
    "errors": 0,
    "hosts": {},
}


def _host_stats(host: str) -> dict:
    return _STATS["hosts"].setdefault(host, {
        "requests": 0,
        "cache_hits": 0,
        "retries": 0,
        "http_429": 0,
        "errors": 0,
    })


def _safe_host(host: str) -> str:
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in host)


def _pace(host: str, min_interval: float | None) -> None:
    interval = DEFAULT_INTERVALS.get(host, 0.10) if min_interval is None else max(0.0, float(min_interval))
    if interval <= 0:
        return
    lock_path = LOCK_DIR / (_safe_host(host) + ".lock")
    with lock_path.open("a+") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read().strip()
        try:
            last = float(raw) if raw else 0.0
        except ValueError:
            last = 0.0
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        fh.seek(0)
        fh.truncate()
        fh.write(str(time.monotonic()))
        fh.flush()
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _cache_path(method: str, url: str, payload: bytes | None) -> Path:
    h = hashlib.sha256()
    h.update(method.encode())
    h.update(b"\0")
    h.update(url.encode())
    h.update(b"\0")
    h.update(payload or b"")
    return CACHE_DIR / (h.hexdigest() + ".json")


def _cache_get(path: Path, ttl: float) -> bytes | None:
    if ttl <= 0 or not path.exists():
        return None
    try:
        doc = json.loads(path.read_text())
        if time.time() - float(doc["saved_at"]) > ttl:
            return None
        return bytes.fromhex(doc["body_hex"])
    except Exception:
        return None


def _cache_put(path: Path, body: bytes) -> None:
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"saved_at": time.time(), "body_hex": body.hex()}))
        os.replace(tmp, path)
    except Exception:
        pass


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    payload: bytes | None = None,
    headers: dict | None = None,
    timeout: float = 15,
    attempts: int = 5,
    cache_ttl: float = 0,
    min_interval: float | None = None,
    user_agent: str = "Wallet500-ResilientHTTP/1.0",
) -> bytes:
    method = method.upper()
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    hs = _host_stats(host)
    cache_path = _cache_path(method, url, payload)
    if method == "GET":
        cached = _cache_get(cache_path, cache_ttl)
        if cached is not None:
            _STATS["cache_hits"] += 1
            hs["cache_hits"] += 1
            return cached

    req_headers = {"User-Agent": user_agent, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    last_error: Exception | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(total_attempts):
        _pace(host, min_interval)
        _STATS["requests"] += 1
        hs["requests"] += 1
        req = urllib.request.Request(url, data=payload, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                if method == "GET" and cache_ttl > 0:
                    _cache_put(cache_path, body)
                return body
        except urllib.error.HTTPError as exc:
            last_error = exc
            code = int(getattr(exc, "code", 0) or 0)
            retryable = code == 429 or 500 <= code < 600
            if code == 429:
                _STATS["http_429"] += 1
                hs["http_429"] += 1
            elif 500 <= code < 600:
                _STATS["http_5xx"] += 1
            if not retryable or attempt >= total_attempts - 1:
                _STATS["errors"] += 1
                hs["errors"] += 1
                raise
            _STATS["retries"] += 1
            hs["retries"] += 1
            retry_after = 0.0
            try:
                retry_after = float(exc.headers.get("Retry-After") or 0)
            except Exception:
                retry_after = 0.0
            delay = max(retry_after, min(30.0, (2 ** attempt) + random.uniform(0.15, 0.75)))
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= total_attempts - 1:
                _STATS["errors"] += 1
                hs["errors"] += 1
                raise
            _STATS["retries"] += 1
            hs["retries"] += 1
            time.sleep(min(15.0, (1.5 ** attempt) + random.uniform(0.1, 0.5)))

    if last_error:
        raise last_error
    raise RuntimeError("HTTP_REQUEST_FAILED_WITHOUT_EXCEPTION")


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | list | None = None,
    headers: dict | None = None,
    timeout: float = 15,
    attempts: int = 5,
    cache_ttl: float = 0,
    min_interval: float | None = None,
    user_agent: str = "Wallet500-ResilientHTTP/1.0",
):
    raw_payload = None
    merged_headers = dict(headers or {})
    if payload is not None:
        raw_payload = json.dumps(payload, separators=(",", ":")).encode()
        merged_headers.setdefault("Content-Type", "application/json")
    body = request_bytes(
        url,
        method=method,
        payload=raw_payload,
        headers=merged_headers,
        timeout=timeout,
        attempts=attempts,
        cache_ttl=cache_ttl,
        min_interval=min_interval,
        user_agent=user_agent,
    )
    return json.loads(body.decode("utf-8"))


def request_text(
    url: str,
    *,
    timeout: float = 15,
    attempts: int = 5,
    cache_ttl: float = 0,
    min_interval: float | None = None,
    user_agent: str = "Wallet500-ResilientHTTP/1.0",
    accept: str = "text/plain,*/*",
) -> str:
    body = request_bytes(
        url,
        headers={"Accept": accept},
        timeout=timeout,
        attempts=attempts,
        cache_ttl=cache_ttl,
        min_interval=min_interval,
        user_agent=user_agent,
    )
    return body.decode("utf-8", "ignore")


def metrics() -> dict:
    return json.loads(json.dumps(_STATS))
