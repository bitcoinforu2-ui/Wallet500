from __future__ import annotations

import json
from urllib.error import HTTPError

import scripts.new_chain_bootstrap_radar as radar


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_catalog_400_after_data_is_clean_end_of_catalog(monkeypatch):
    calls = []

    def fake_get(url, timeout=20, attempts=3):
        calls.append(url)
        if len(calls) == 1:
            return {"data": [{"id": "eth"}, {"id": "arc"}]}
        raise HTTPError(url, 400, "Bad Request", None, None)

    monkeypatch.setattr(radar, "_get", fake_get)
    found, errors = radar.discover_supported_networks(20)

    assert found == ["eth", "arc"]
    assert errors == []
    assert len(calls) == 2


def test_catalog_error_before_any_data_is_reported(monkeypatch):
    def fake_get(url, timeout=20, attempts=3):
        raise HTTPError(url, 500, "Server Error", None, None)

    monkeypatch.setattr(radar, "_get", fake_get)
    found, errors = radar.discover_supported_networks(20)

    assert found == []
    assert len(errors) == 1
    assert errors[0]["page"] == 1
    assert errors[0]["error"] == "HTTPError:500"


def test_http_429_retries_with_backoff(monkeypatch):
    attempts = {"count": 0}
    sleeps = []
    ticks = iter([100.0, 100.0, 110.0, 110.0, 120.0, 120.0, 130.0, 130.0])

    def fake_monotonic():
        return next(ticks)

    def fake_sleep(seconds):
        sleeps.append(seconds)

    def fake_urlopen(req, timeout=20):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                {"Retry-After": "9"},
                None,
            )
        return _Response({"ok": True})

    monkeypatch.setattr(radar.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(radar.time, "sleep", fake_sleep)
    monkeypatch.setattr(radar, "urlopen", fake_urlopen)
    monkeypatch.setattr(radar, "_last_http_at", 0.0)

    assert radar._get("https://example.test", attempts=2) == {"ok": True}
    assert attempts["count"] == 2
    assert any(seconds >= 9 for seconds in sleeps)


def test_cirbtc_is_filtered_from_bootstrap_candidates():
    row = {
        "symbol": "cirBTC",
        "pair_age_hours": 10,
        "liquidity_usd": 1_000_000,
        "volume_h1": 100_000,
        "volume_h24": 1_000_000,
        "buys_h1": 500,
        "sells_h1": 300,
    }
    assert radar.candidate_eligible(row) is False
