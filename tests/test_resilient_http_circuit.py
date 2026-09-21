import time
import urllib.error

import pytest

from scripts import resilient_http as rh


HOST = "api.geckoterminal.com"
URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools/test"


def _reset_host_state():
    rh._CIRCUIT_STATE.pop(HOST, None)
    rh._STATS["hosts"].pop(HOST, None)


def test_repeated_geckoterminal_429_opens_fail_fast_circuit(monkeypatch):
    _reset_host_state()
    monkeypatch.setattr(rh, "_pace", lambda host, min_interval: None)
    monkeypatch.setattr(rh, "_set_cooldown", lambda host, seconds: None)

    calls = {"count": 0}

    def fake_urlopen(req, timeout):
        calls["count"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(rh.urllib.request, "urlopen", fake_urlopen)

    for _ in range(3):
        with pytest.raises(urllib.error.HTTPError):
            rh.request_bytes(URL, attempts=1, min_interval=0)

    assert calls["count"] == 3
    state = rh._CIRCUIT_STATE[HOST]
    assert int(state["consecutive_429"]) == 3
    assert float(state["open_until"]) > time.time()

    with pytest.raises(RuntimeError, match="HTTP_CIRCUIT_OPEN"):
        rh.request_bytes(URL, attempts=1, min_interval=0)

    # Circuit rejection happens before another network call.
    assert calls["count"] == 3
    host_metrics = rh.metrics()["hosts"][HOST]
    assert host_metrics["circuit_opens"] >= 1
    assert host_metrics["circuit_fast_fails"] >= 1


def test_success_after_circuit_expiry_resets_429_streak(monkeypatch):
    _reset_host_state()
    rh._CIRCUIT_STATE[HOST] = {
        "consecutive_429": 3,
        "open_until": time.time() - 1,
    }
    monkeypatch.setattr(rh, "_pace", lambda host, min_interval: None)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    monkeypatch.setattr(rh.urllib.request, "urlopen", lambda req, timeout: Response())

    assert rh.request_bytes(URL, attempts=1, min_interval=0) == b"{}"
    state = rh._CIRCUIT_STATE[HOST]
    assert int(state["consecutive_429"]) == 0
    assert float(state["open_until"]) == 0.0
