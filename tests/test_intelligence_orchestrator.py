from wallet500.intelligence_orchestrator import (
    ProviderCapability, ProviderObservation, ProviderRegistry, ProviderState,
    acceleration, build_research_bundle, classify_freshness, convergence_score,
)


def test_missing_never_becomes_zero():
    assert acceleration(None, 10) is None
    c=convergence_score({"volume":1.0,"social":None})
    assert c["missing_signals"]==["social"]


def test_freshness_fail_closed_and_future_rejected():
    assert classify_freshness("2026-09-19T10:00:00Z",now="2026-09-19T10:01:00Z",max_age_seconds=120)==ProviderState.OK
    assert classify_freshness("2026-09-19T09:00:00Z",now="2026-09-19T10:01:00Z",max_age_seconds=120)==ProviderState.STALE
    try:
        classify_freshness("2026-09-19T11:00:00Z",now="2026-09-19T10:01:00Z",max_age_seconds=120)
        assert False
    except ValueError as e:
        assert str(e)=="FUTURE_EVIDENCE_REJECTED"


def test_registry_capability_negotiation():
    r=ProviderRegistry()
    r.register(ProviderCapability("dex",frozenset({"market"}),frozenset({"solana"}),120,True))
    assert [x.provider_id for x in r.eligible(kind="market",chain="solana")]==["dex"]
    assert r.eligible(kind="holders",chain="solana")==[]


def test_bundle_cannot_promote():
    o={"market":ProviderObservation("market",ProviderState.OK,"2026-09-19T10:00:00Z",{"volume":100})}
    b=build_research_bundle(identity_key="solana:token:pair",observed_at="2026-09-19T10:00:00Z",
                            observations=o,signal_velocities={"volume":1.0,"buyers":None})
    assert b["production_promotion_allowed"] is False
    assert b["may_weaken_truth_contract"] is False
    assert b["missing_is_zero"] is False
    assert b["retroactive_t0_allowed"] is False
