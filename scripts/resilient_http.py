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
    # Public GeckoTerminal quota can be shared by hosted-runner egress IPs.
    # Deliberately stay far below the nominal public limit.
    "api.geckoterminal.com": 4.0,
    "api.dexscreener.com": 0.35,
    "api.gateio.ws": 0.35,
    "fx-api.gateio.ws": 0.35,
    "api.hyperliquid.xyz": 0.35,
    "fapi.binance.com": 0.50,
    "api.bybit.com": 0.50,
    "www.okx.com": 0.50,
    "api.mainnet-beta.solana.com": 0.25,
    "eth.blockscout.com": 0.25,
    "base.blockscout.com": 0.25,
    "arbitrum.blockscout.com": 0.25,
    "optimism.blockscout.com": 0.25,
    "polygon.blockscout.com": 0.25,
    "bsc.blockscout.com": 0.25,
}

CIRCUIT_BREAKERS = {
    # Hosted-runner egress IPs can inherit a shared GeckoTerminal quota.
    # After repeated 429s, fail this provider fast for a short window so callers
    # can use their exact-identity fallback instead of serially sleeping.
    "api.geckoterminal.com": {
        "http_429_threshold": 3,
        "open_seconds": 120.0,
    },
}

_CIRCUIT_STATE: dict[str, dict[str, float | int]] = {}

_STATS = {
    "requests": 0,
    "cache_hits": 0,
    "retries": 0,
    "http_429": 0,
    "http_5xx": 0,
    "cooldowns": 0,
    "circuit_opens": 0,
    "circuit_fast_fails": 0,
    "errors": 0,
    "hosts": {},
}


def _host_stats(host: str) -> dict:
    return _STATS["hosts"].setdefault(host, {
        "requests": 0,
        "cache_hits": 0,
        "retries": 0,
        "http_429": 0,
        "cooldowns": 0,
        "circuit_opens": 0,
        "circuit_fast_fails": 0,
        "errors": 0,
    })


def _safe_host(host: str) -> str:
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in host)


def _circuit_state(host: str) -> dict[str, float | int]:
    return _CIRCUIT_STATE.setdefault(host, {
        "consecutive_429": 0,
        "open_until": 0.0,
    })


def _raise_if_circuit_open(host: str) -> None:
    cfg = CIRCUIT_BREAKERS.get(host)
    if not cfg:
        return
    state = _circuit_state(host)
    now = time.time()
    open_until = float(state.get("open_until") or 0.0)
    if open_until <= now:
        if open_until:
            state["open_until"] = 0.0
        return
    remaining = max(0.0, open_until - now)
    _STATS["circuit_fast_fails"] += 1
    hs = _host_stats(host)
    hs["circuit_fast_fails"] += 1
    _STATS["errors"] += 1
    hs["errors"] += 1
    raise RuntimeError(f"HTTP_CIRCUIT_OPEN:{host}:{remaining:.1f}s")


def _record_http_429(host: str, retry_after: float) -> None:
    cfg = CIRCUIT_BREAKERS.get(host)
    if not cfg:
        return
    state = _circuit_state(host)
    count = int(state.get("consecutive_429") or 0) + 1
    state["consecutive_429"] = count
    threshold = max(1, int(cfg.get("http_429_threshold") or 1))
    if count < threshold:
        return
    open_seconds = max(float(cfg.get("open_seconds") or 0.0), max(0.0, retry_after))
    if open_seconds <= 0:
        return
    new_until = time.time() + open_seconds
    previous_until = float(state.get("open_until") or 0.0)
    if new_until > previous_until:
        state["open_until"] = new_until
        _STATS["circuit_opens"] += 1
        _host_stats(host)["circuit_opens"] += 1


def _record_http_success(host: str) -> None:
    if host not in CIRCUIT_BREAKERS:
        return
    state = _circuit_state(host)
    state["consecutive_429"] = 0
    state["open_until"] = 0.0


def _cooldown_path(host: str) -> Path:
    return LOCK_DIR / (_safe_host(host) + ".cooldown")


def _set_cooldown(host: str, seconds: float) -> None:
    seconds = max(0.0, float(seconds))
    if seconds <= 0:
        return
    p = _cooldown_path(host)
    until = time.time() + seconds
    try:
        current = 0.0
        if p.exists():
            current = float(p.read_text().strip() or 0)
        if until > current:
            p.write_text(str(until))
        _STATS["cooldowns"] += 1
        _host_stats(host)["cooldowns"] += 1
    except Exception:
        pass


def _cooldown_wait(host: str) -> float:
    p = _cooldown_path(host)
    if not p.exists():
        return 0.0
    try:
        return max(0.0, float(p.read_text().strip() or 0) - time.time())
    except Exception:
        return 0.0


def _pace(host: str, min_interval: float | None) -> None:
    interval = DEFAULT_INTERVALS.get(host, 0.10) if min_interval is None else max(0.0, float(min_interval))
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
        wait_interval = max(0.0, interval - (time.monotonic() - last))
        wait_cooldown = _cooldown_wait(host)
        wait = max(wait_interval, wait_cooldown)
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
    user_agent: str = "Wallet500-ResilientHTTP/2.0",
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
        _raise_if_circuit_open(host)
        _pace(host, min_interval)
        _STATS["requests"] += 1
        hs["requests"] += 1
        req = urllib.request.Request(url, data=payload, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                _record_http_success(host)
                if method == "GET" and cache_ttl > 0:
                    _cache_put(cache_path, body)
                return body
        except urllib.error.HTTPError as exc:
            last_error = exc
            code = int(getattr(exc, "code", 0) or 0)
            retryable = code == 429 or 500 <= code < 600
            retry_after = 0.0
            try:
                retry_after = float(exc.headers.get("Retry-After") or 0)
            except Exception:
                retry_after = 0.0
            if code == 429:
                _STATS["http_429"] += 1
                hs["http_429"] += 1
                # Even if this caller is fail-closed/no-retry, protect the next
                # request for this host instead of creating a retry storm.
                default_cooldown = 15.0 if host == "api.geckoterminal.com" else 5.0
                _set_cooldown(host, max(retry_after, default_cooldown))
                _record_http_429(host, retry_after)
            elif 500 <= code < 600:
                _STATS["http_5xx"] += 1
                _set_cooldown(host, max(retry_after, 2.0))
            if not retryable or attempt >= total_attempts - 1:
                _STATS["errors"] += 1
                hs["errors"] += 1
                raise
            _STATS["retries"] += 1
            hs["retries"] += 1
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
    user_agent: str = "Wallet500-ResilientHTTP/2.0",
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
    user_agent: str = "Wallet500-ResilientHTTP/2.0",
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
