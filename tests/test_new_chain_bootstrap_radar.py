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


def test_full_catalog_advances_across_runs_without_starving_seed_networks(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(radar, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(radar, "OUT", tmp_path / "report.json")
    monkeypatch.setattr(radar, "NETWORK_FULL_SCAN_MAX_PAGES", 4)
    monkeypatch.setattr(radar, "CATALOG_PAGES_PER_RUN", 2)
    monkeypatch.setattr(radar, "NETWORKS_PER_RUN", 2)
    seen, scanned = [], []

    def discovery(max_pages, start_page=1):
        seen.append((max_pages, start_page))
        radar._catalog_pages_visited = max_pages
        radar._catalog_ended = False
        return ["eth"], []

    monkeypatch.setattr(radar, "discover_supported_networks", discovery)
    monkeypatch.setattr(radar, "collect_network", lambda network, now: (scanned.append(network) or [], []))
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    first = radar.run(now)
    assert seen == [(2, 1)]
    assert first["network_catalog"]["sweep_in_progress"] is True
    assert first["network_catalog"]["next_page"] == 3
    assert scanned == ["arc", "robinhood"]
    second = radar.run(now + timedelta(minutes=10))
    assert seen == [(2, 1), (2, 3)]
    assert second["network_catalog"]["sweep_in_progress"] is False
    assert second["network_catalog"]["next_page"] == 1
    assert json.loads((tmp_path / "state.json").read_text())["last_full_network_scan_at"]


def test_round_robin_deferred_networks_are_reported(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(radar, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(radar, "OUT", tmp_path / "report.json")
    monkeypatch.setattr(radar, "NETWORKS_PER_RUN", 2)
    (tmp_path / "state.json").write_text(json.dumps({
        "baseline_initialized": True, "known_networks": {"xphere": {"first_seen_at": now.isoformat()}},
        "auto_active_networks": ["xphere"],
        "last_full_network_scan_at": now.isoformat(),
    }))
    def discovery(max_pages, start_page=1):
        radar._catalog_pages_visited = 1
        radar._catalog_ended = False
        return [], []
    monkeypatch.setattr(radar, "discover_supported_networks", discovery)
    scanned = []
    monkeypatch.setattr(radar, "collect_network", lambda network, t: (scanned.append(network) or [], []))
    a = radar.run(now)
    b = radar.run(now + timedelta(minutes=10))
    assert a["counts"]["networks_rotating_deferred"] == 1
    assert a["deferred_networks"] == ["xphere"]
    assert b["deferred_networks"] == ["robinhood"]
    assert scanned == ["arc", "robinhood", "xphere", "arc"]
    assert a["coverage_status"] == "ROTATING_PARTIAL"


def test_initial_catalog_never_announces_incomplete_baseline_as_new(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(radar, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(radar, "OUT", tmp_path / "report.json")
    monkeypatch.setattr(radar, "NETWORKS_PER_RUN", 2)
    monkeypatch.setattr(radar, "NETWORK_FULL_SCAN_MAX_PAGES", 4)
    monkeypatch.setattr(radar, "CATALOG_PAGES_PER_RUN", 2)
    def discovery(max_pages, start_page=1):
        radar._catalog_pages_visited = 2
        radar._catalog_ended = False
        return ["brandnew"] if start_page == 3 else ["oldnet"], []
    monkeypatch.setattr(radar, "discover_supported_networks", discovery)
    monkeypatch.setattr(radar, "collect_network", lambda network, t: ([], []))
    first = radar.run(now)
    second = radar.run(now + timedelta(minutes=10))
    assert first["auto_detected_new_networks_this_run"] == []
    assert second["auto_detected_new_networks_this_run"] == []
    assert json.loads((tmp_path / "state.json").read_text())["baseline_initialized"] is True
