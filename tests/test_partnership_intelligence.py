import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wallet500 import partnership_intelligence as p

MINT = "rizo34MUwbCBqpSTSfnEktdWB4CTByqqYh8zBxL3WAR"
TARGET = {
    "symbol": "RIZO", "chain": "solana", "contract": MINT,
    "aliases": ["HahaYes", "RIZO"], "queries": [],
    "verified_primary_hosts": ["tesla.com", "xtakeover.com"],
}


def setup(tmp_path):
    (tmp_path / "partnership-watch-targets.json").write_text(
        json.dumps({"targets": [TARGET]}), encoding="utf-8")
    (tmp_path / "partnership-evidence-inbox.json").write_text("[]", encoding="utf-8")


def test_https_hostname_defends_against_spoofing():
    assert p.host_allowed("https://www.tesla.com/blog/xyz", {"tesla.com"})
    assert not p.host_allowed("https://tesla.com.attacker.org/news", {"tesla.com"})
    assert not p.host_allowed("http://tesla.com/news", {"tesla.com"})
    assert not p.host_allowed("https://tesla.com@attacker.org/news", {"tesla.com"})
    assert not p.host_allowed("https://tesla.com:444/news", {"tesla.com"})


def test_other_chains_and_symbol_only_do_not_create_token_identity():
    assert p.exact_match({"chain": "solana", "symbol": "RIZO"}, TARGET) is False
    assert p.exact_match({"chain": "ethereum", "contract": MINT}, TARGET) is False
    assert p.exact_match({"chain": "solana", "contract": MINT}, TARGET) is True


def test_first_run_is_baseline_and_no_telegram(tmp_path):
    setup(tmp_path)
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    def headlines(target, errors):
        return [p.evidence(target, "HahaYes shows up at Tesla event",
                           "https://news.google.com/articles/abc", "2026-10-01",
                           "GOOGLE_NEWS_DISCOVERY", "UNVERIFIED_DISCOVERY", "not proof")]
    response = p.run(tmp_path, t0, news_fetcher=headlines)
    report = p.load(tmp_path / "partnership-intelligence-latest.json", {})
    assert response["status"] == "BASELINE"
    assert report["new_events"] == 0
    assert report["initial_baseline_events"] == 1
    assert report["manual_review"] == []
    assert report["telegram_sent"] == 0
    assert p.run(tmp_path, t0 + timedelta(hours=1), news_fetcher=headlines)["status"] == "SKIPPED_COOLDOWN"
    assert p.run(tmp_path, t0 + timedelta(hours=7), news_fetcher=headlines)["new_events"] == 0


def test_primary_must_contain_exact_contract_even_if_website_is_official(monkeypatch):
    errors = []
    monkeypatch.setattr(p, "fetch", lambda url, allowed: "<h1>Tesla owners HahaYes mascot</h1>")
    row = {"url": "https://www.tesla.com/blog/example", "title": "Mascot", "published_at": "2026-10-01"}
    out = p.verify_primary(TARGET, row, errors)
    assert out["classification"] == "PRIMARY_CONTEXT_ONLY"
    assert not out["partnership_confirmed"]
    monkeypatch.setattr(p, "fetch", lambda url, allowed: "<main>" + MINT + " mentioned in document</main>")
    out = p.verify_primary(TARGET, row, errors)
    assert out["classification"] == "PRIMARY_EXACT_CONTRACT_REVIEW"
    assert not out["partnership_confirmed"] and not out["telegram_eligible"]
    assert not errors


def test_spoofed_primary_domain_is_ignored_without_fetch(monkeypatch):
    monkeypatch.setattr(p, "fetch", lambda *args: (_ for _ in ()).throw(AssertionError("should not fetch")))
    assert p.verify_primary(TARGET, {"url": "https://www.tesla.com.evil.net/news"}, []) is None


def test_existing_events_require_exact_contract_and_chain(tmp_path, monkeypatch):
    setup(tmp_path)
    (tmp_path / "catalyst-wire-live.json").write_text(json.dumps({"events": [
        {"symbol": "RIZO", "chain": "solana", "source_url": "https://a.org/1"},
        {"symbol": "RIZO", "chain": "ethereum", "contract": MINT, "source_url": "https://a.org/2"},
        {"symbol": "RIZO", "chain": "solana", "contract": MINT, "source_url": "https://a.org/3"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(p, "CATALYST", tmp_path / "catalyst-wire-live.json")
    monkeypatch.setattr(p, "SOCIAL", tmp_path / "social-catalyst-ledger.json")
    data = p.ingest_existing(TARGET)
    assert len(data) == 1
    assert data[0]["classification"] == "EXACT_IDENTITY_SECONDARY"


def test_new_official_document_is_review_only(tmp_path, monkeypatch):
    setup(tmp_path)
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    p.run(tmp_path, t0, news_fetcher=lambda *args: [])
    proof = {"chain": "solana", "contract": MINT, "url": "https://xtakeover.com/announcements/1",
             "title": "Partnership evidence", "published_at": "2026-10-01"}
    (tmp_path / "partnership-evidence-inbox.json").write_text(json.dumps([proof]), encoding="utf-8")
    monkeypatch.setattr(p, "fetch", lambda url, allowed: "<p>" + MINT + "</p>")
    response = p.run(tmp_path, t0 + timedelta(hours=7), news_fetcher=lambda *args: [])
    report = p.load(tmp_path / "partnership-intelligence-latest.json", {})
    assert response["manual_review"] == 1
    assert report["manual_review"][0]["classification"] == "PRIMARY_EXACT_CONTRACT_REVIEW"
    assert report["manual_review"][0]["partnership_confirmed"] is False
    assert report["telegram_sent"] == 0
