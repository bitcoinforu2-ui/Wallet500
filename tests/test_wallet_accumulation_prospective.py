from datetime import datetime, timedelta, timezone

from wallet500 import wallet_accumulation_prospective as m


def test_marker_is_research_only_raw_wallet_pattern():
    snap = {
        "h1": {"resolved_swaps": 4, "unique_buyers": 3, "unique_sellers": 2, "net_accumulating_wallets": 3, "net_distributing_wallets": 1, "wallet_buy_sell_ratio": 1.5},
        "h4": {},
    }
    assert m._research_accumulation_marker(snap) is True
    snap["h1"]["net_accumulating_wallets"] = 1
    snap["h1"]["net_distributing_wallets"] = 2
    assert m._research_accumulation_marker(snap) is False


def test_locked_cohort_exact_pair_and_no_hindsight(monkeypatch, tmp_path):
    evidence = {
        "generated_at": "2026-09-12T00:00:00Z",
        "selection_policy": {"wallet_insight_priority_bridge": {"selected_tokens": ["MINT"]}},
        "tokens": [{
            "token_address": "MINT", "symbol": "X", "exact_pair": "PAIR", "status": "LIVE_FORWARD_ONLY",
            "coverage": {"coverage_quality": "VERIFIED"},
            "windows": {"h1": {"resolved_swaps": 4, "unique_buyers": 3, "unique_sellers": 2, "net_accumulating_wallets": 3, "net_distributing_wallets": 1, "wallet_buy_sell_ratio": 1.5}},
        }],
    }
    monkeypatch.setattr(m, "EVIDENCE", tmp_path / "evidence.json")
    monkeypatch.setattr(m, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(m, "REPORT", tmp_path / "report.json")
    m._write(m.EVIDENCE, evidence)
    t0 = datetime(2026, 9, 12, tzinfo=timezone.utc)
    r1 = m.run(now=t0, price_fetcher=lambda mint, pair: 1.0)
    assert r1["cohort_size"] == 1
    assert r1["phase"] == "COLLECTING_24H"
    state1 = m._load(m.STATE, {})
    assert state1["cohort"][0]["identity"] == "solana|MINT|PAIR"
    first_marker = state1["cohort"][0]["first_research_accumulation_marker_at"]

    # Later evidence cannot change the locked identity/cohort; it only appends an observation.
    evidence["generated_at"] = "2026-09-13T00:00:01Z"
    evidence["selection_policy"]["wallet_insight_priority_bridge"]["selected_tokens"] = ["OTHER"]
    m._write(m.EVIDENCE, evidence)
    r2 = m.run(now=t0 + timedelta(hours=24, seconds=1), price_fetcher=lambda mint, pair: 1.2)
    state2 = m._load(m.STATE, {})
    assert r2["phase"] == "COMPLETE_24H"
    assert state2["cohort"][0]["identity"] == "solana|MINT|PAIR"
    assert state2["cohort"][0]["first_research_accumulation_marker_at"] == first_marker
    assert r2["tokens"][0]["latest_return_pct"] > 19.9


def test_missing_price_is_not_guessed(monkeypatch, tmp_path):
    evidence = {
        "generated_at": "2026-09-12T00:00:00Z",
        "selection_policy": {"wallet_insight_priority_bridge": {"selected_tokens": ["M"]}},
        "tokens": [{"token_address": "M", "exact_pair": "P", "windows": {}}],
    }
    monkeypatch.setattr(m, "EVIDENCE", tmp_path / "e.json")
    monkeypatch.setattr(m, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(m, "REPORT", tmp_path / "r.json")
    m._write(m.EVIDENCE, evidence)
    report = m.run(now=datetime(2026, 9, 12, tzinfo=timezone.utc), price_fetcher=lambda mint, pair: None)
    assert report["tokens"][0]["baseline_price_usd"] is None
    assert report["tokens"][0]["latest_return_pct"] is None
