from wallet500 import revival_prewaking_wallet_evidence_v2 as m


def _insight(rows):
    return {
        "version": "WALLET500_WALLET_INSIGHT_REVIEW_V1",
        "mode": "RESEARCH_ONLY_EXACT_PAIR_WALLET_BOTTLENECK_REVIEW",
        "generated_at": "2026-09-11T20:00:00Z",
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "truth_contract": {"exact_pair_required": True, "coverage_probe_never_counts_as_accumulation_alpha": True, "historical_coverage_never_counts_as_current_positive": True, "promotion_allowed": False},
        "rows": rows,
    }


def _row(i):
    return {"identity": f"solana|T{i}|P{i}", "symbol": f"T{i}", "candidate_status": "EVIDENCE_READY", "classification": "DATA_PIPELINE_BOTTLENECK", "metrics": {"current_probe_verified": True, "coverage_degraded": False}}


def test_bridge_requires_current_verified_exact_pair(monkeypatch):
    rows = [
        {"identity": "solana|GOOD|PAIR1", "symbol": "GOOD", "candidate_status": "EVIDENCE_READY", "classification": "DATA_PIPELINE_BOTTLENECK", "metrics": {"current_probe_verified": True, "coverage_degraded": False}},
        {"identity": "solana|OLD|PAIR2", "symbol": "OLD", "candidate_status": "EVIDENCE_READY", "classification": "DATA_PIPELINE_BOTTLENECK", "metrics": {"current_probe_verified": False, "historical_probe_verified": True, "coverage_degraded": True}},
        {"identity": "solana|NOPAIR|", "symbol": "NOPAIR", "candidate_status": "VERIFIED_WATCH", "classification": "DATA_PIPELINE_BOTTLENECK", "metrics": {"current_probe_verified": True, "coverage_degraded": False}},
    ]
    monkeypatch.setattr(m, "_load_json", lambda _p: _insight(rows))
    out = m._insight_priority_candidates({}, slots=8)
    assert [r["token_address"] for r in out] == ["GOOD"]
    assert out[0]["pair_address"] == "PAIR1"
    assert out[0]["reason"] == "PRE_WAKING_DEEP_WATCH"
    assert out[0]["scheduling_only"] is True


def test_bridge_rotates_previous_cycle_without_hindsight(monkeypatch):
    monkeypatch.setattr(m, "_load_json", lambda _p: _insight([_row(i) for i in range(4)]))
    previous = {"tokens": [
        {"token_address": "T0", "wallet_insight_bridge": {"scheduling_only": True}},
        {"token_address": "T1", "wallet_insight_bridge": {"scheduling_only": True}},
    ]}
    out = m._insight_priority_candidates(previous, slots=2)
    assert {r["token_address"] for r in out} == {"T2", "T3"}


def test_bridge_rejects_non_research_or_promotion_capable_source(monkeypatch):
    bad = _insight([])
    bad["truth_contract"]["promotion_allowed"] = True
    monkeypatch.setattr(m, "_load_json", lambda _p: bad)
    assert m._insight_priority_candidates({}, slots=8) == []
