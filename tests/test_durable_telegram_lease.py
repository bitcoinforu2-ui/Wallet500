"""At-most-once exact-episode Telegram send claims under crash and overlap."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from scripts import durable_telegram_lease as lease


class FakeGitHub:
    def __init__(self):
        self.refs = {}
        self.lock = threading.Lock()
        self.fail_ack = False
        self.reject_without_existing_ref = False

    def __call__(self, token, repo, method, path, payload=None, allowed=(200,)):
        assert token == "fake-token" and repo == "example/wallet500"
        if method == "GET" and path == "/git/ref/heads/main":
            return 200, {"object": {"sha": "abc123"}}
        if method == "POST" and path == "/git/refs":
            ref = payload["ref"]
            if self.fail_ack and lease.DELIVERED_ROOT in ref:
                raise TimeoutError("ack timed out")
            if self.reject_without_existing_ref:
                return 422, {}
            with self.lock:
                if ref in self.refs:
                    return 422, {}
                self.refs[ref] = payload["sha"]
            return 201, {}
        if method == "GET" and path.startswith("/git/ref/heads/"):
            ref = "refs/heads/" + path.removeprefix("/git/ref/heads/")
            return (200, {"object": {"sha": self.refs[ref]}}) if ref in self.refs else (404, {})
        raise AssertionError((method, path))


@pytest.fixture
def fake_github(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/wallet500")
    gh = FakeGitHub()
    monkeypatch.setattr(lease, "_api", gh)
    return gh


def test_claim_must_be_durable_before_telegram_send(fake_github):
    events = []
    receipt = lease.send_once("base:CA:PAIR", "PRE_BUY", 1, "message", lambda msg: events.append(msg) or 314)
    assert receipt["status"] == "DELIVERED_LEDGER_CONFIRMED"
    assert receipt["message_id"] == 314
    assert events == ["message"]
    assert len(fake_github.refs) == 2
    with pytest.raises(lease.LeaseAlreadyExists) as duplicate:
        lease.send_once("base:CA:PAIR", "PRE_BUY", 1, "duplicate", lambda msg: events.append(msg))
    assert duplicate.value.delivered is True
    assert events == ["message"]


def test_crash_after_claim_never_auto_resends(fake_github):
    with pytest.raises(TimeoutError):
        lease.send_once("base:CA:PAIR", "FINAL_BUY", 1, "message", lambda _: (_ for _ in ()).throw(TimeoutError("Telegram reply lost")))
    calls = []
    with pytest.raises(lease.LeaseAlreadyExists) as duplicate:
        lease.send_once("base:CA:PAIR", "FINAL_BUY", 1, "message", lambda msg: calls.append(msg))
    assert duplicate.value.delivered is False
    assert calls == []


def test_ack_timeout_does_not_retry_an_irreversible_send(fake_github):
    fake_github.fail_ack = True
    calls = []
    receipt = lease.send_once("base:CA:PAIR", "FINAL_BUY", 1, "message", lambda msg: calls.append(msg) or 55)
    assert receipt["status"] == "SENT_LEDGER_ACK_UNCERTAIN"
    with pytest.raises(lease.LeaseAlreadyExists) as existing:
        lease.send_once("base:CA:PAIR", "FINAL_BUY", 1, "again", lambda msg: calls.append(msg))
    assert existing.value.delivered is False
    assert calls == ["message"]


def test_distinct_confirmation_stages_and_real_reentries_have_distinct_keys(fake_github):
    assert len({
        lease.event_id("base:CA:PAIR", "PRE_BUY", 1),
        lease.event_id("base:CA:PAIR", "FINAL_BUY", 1),
        lease.event_id("base:CA:PAIR", "PRE_BUY", 2),
        lease.event_id("base:CA:OTHER", "PRE_BUY", 1),
    }) == 4


def test_unexpected_422_without_verified_ref_fails_closed(fake_github):
    fake_github.reject_without_existing_ref = True
    sent = []
    with pytest.raises(RuntimeError, match="CLAIM_REJECTED_WITHOUT_EXISTING_REF"):
        lease.send_once("base:CA:PAIR", "FINAL_BUY", 1, "message", lambda msg: sent.append(msg))
    assert sent == []


def test_missing_github_credentials_never_sends(fake_github, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN")
    sent = []
    with pytest.raises(RuntimeError, match="CREDENTIALS_UNAVAILABLE"):
        lease.send_once("base:CA:PAIR", "FINAL_BUY", 1, "message", lambda msg: sent.append(msg))
    assert sent == []


def test_overlapping_runs_claim_exactly_once(fake_github):
    results = []
    def worker(_):
        try:
            receipt = lease.send_once("base:CA:PAIR", "PRE_BUY", 1, "message", lambda msg: results.append(msg))
            return receipt["status"]
        except lease.LeaseAlreadyExists:
            return "BLOCKED_DUPLICATE"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, range(2)))
    assert sorted(outcomes) == ["BLOCKED_DUPLICATE", "DELIVERED_LEDGER_CONFIRMED"]
    assert len(results) == 1
