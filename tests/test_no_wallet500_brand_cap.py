import json

from wallet500 import global_listing_intelligence as listing
from wallet500 import production_age_governance as age_governance
from wallet500 import revival_1000 as revival


def test_revival_brand_number_is_not_candidate_cap():
    assert revival.MAX_CANDIDATES is None


def test_global_listing_watchlist_keeps_more_than_500_candidates(tmp_path, monkeypatch):
    watchlist = tmp_path / "manual-watchlist.json"
    monkeypatch.setattr(listing, "WATCHLIST", watchlist)

    rows = [
        {"chain": "solana", "token": f"token-{i}", "source": "GLOBAL_LISTING_INTELLIGENCE"}
        for i in range(620)
    ]
    manual_count, auto_count = listing._merge_watchlist(rows)

    saved = json.loads(watchlist.read_text(encoding="utf-8"))
    assert manual_count == 0
    assert auto_count == 620
    assert len(saved) == 620


def test_age_governance_quarantine_audits_more_than_500_candidates(tmp_path, monkeypatch):
    active = tmp_path / "active-qualified-candidates.json"
    audit = tmp_path / "active-qualified-age-gate.json"
    rows = [
        {"chain": "solana", "token": f"token-{i}", "pair_address": f"pair-{i}"}
        for i in range(620)
    ]
    active.write_text(json.dumps(rows), encoding="utf-8")

    # Force the fail-closed policy-drift branch without changing production policy.
    monkeypatch.setattr(age_governance, "MIN_MARKET_AGE_DAYS", 91)
    report = age_governance.run(active, audit)

    assert report["quarantined"] == 620
    assert len(report["rejections"]) == 620
    assert json.loads(active.read_text(encoding="utf-8")) == []
