from wallet500.research_decision_engine import build, _recommend


def test_case_study_never_auto_promotes():
    case={"asset":{"symbol":"DOGE-1"},"lookahead_policy":"NO_HINDSIGHT_FORWARD_ONLY","entity_flow_features":["CEX_NET_OUTFLOW"]}
    out=build({}, {}, [case]); p=out["proposals"][0]
    assert p["recommendation"]=="MORE_DATA" and p["hard_rule_change_allowed"] is False
    assert out["production_change_allowed"] is False


def test_measured_recommendation_thresholds():
    assert _recommend(50,30,40,True)=="MORE_DATA"
    assert _recommend(150,15,10,True)=="SHADOW_TEST"
    assert _recommend(350,25,35,True)=="APPROVED_CANDIDATE"
    assert _recommend(350,25,35,False)=="REJECT"
    assert _recommend(350,-1,35,True)=="REJECT"


def _ray_like(pair="PAIR_CURRENT"):
    near={"closest_to_real_alert":[{"symbol":"RAY","chain":"solana","token_address":"RAY_MINT","pair_address":"PAIR_CURRENT","readiness_passed":6,"readiness_total":7,"missing_gates":["STRONG_DECISION_LANE"],"blockers":["NO_STRONG_DECISION_LANE"],"evidence_positive_lanes":["HOLDER_GROWTH","VERIFIED_SOCIAL"],"exact_pair_verified":True,"exact_identity_verified":True,"market_age_verified":True,"execution_pool_liquidity_usd":5_000_000}]}
    cex={"alerts":[{"symbol":"RAYUSDT","chain":"solana","token_address":"RAY_MINT","pair_address":pair,"identity_verified":True,"cex_revival_score":45,"coherent_confirmations":7}]}
    return near,cex


def test_composite_strong_decision_enters_shadow_only():
    near,cex=_ray_like(); out=build({}, {}, [], near, cex)
    assert out["decision_states"]["SHADOW_TEST"]==1
    p=out["next_human_decision"][0]
    assert p["feature_or_rule"]=="COMPOSITE_STRONG_DECISION_SHADOW"
    assert p["recommendation"]=="SHADOW_TEST" and p["pair_reconciled"] is True
    assert p["production_effect"] is False and p["hard_rule_change_allowed"] is False
    assert out["production_change_allowed"] is False and out["production_thresholds_modified"] is False


def test_alternate_pair_cex_evidence_cannot_earn_shadow_credit():
    near,cex=_ray_like(pair="PAIR_HISTORICAL"); out=build({}, {}, [], near, cex)
    assert out["decision_states"]["SHADOW_TEST"]==0 and out["next_human_decision"]==[]


def test_extra_risk_blocker_prevents_composite_shadow():
    near,cex=_ray_like(); near["closest_to_real_alert"][0]["blockers"].append("EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL")
    assert build({}, {}, [], near, cex)["decision_states"]["SHADOW_TEST"]==0


def test_liquidity_recovery_v3_enters_shadow_without_changing_production():
    recovery={
        "mode":"RESEARCH_ONLY_LIQUIDITY_RECOVERY_SHADOW_V3","production_gate_changed":False,"no_hindsight":True,
        "targets":[{"status":"LIQUIDITY_RECOVERY_SHADOW","production_effect":False,"chain":"bsc","token":"0xAbC","pair_address":"0xPAIR","triggered_at":"2026-09-10T10:00:00+00:00","first_reject_liquidity_usd":30000,"metrics":{"liquidity_usd":39000},"age_proof_mode":"CURRENT_EXACT_TOKEN_OVERLAY","age_proof":{"market_age_verified":True,"market_age_min_days":200}}]
    }
    out=build({}, {}, [], {}, {}, recovery)
    assert out["decision_states"]["SHADOW_TEST"]==1
    p=out["next_human_decision"][0]
    assert p["feature_or_rule"]=="LIQUIDITY_RECOVERY_SHADOW_V3"
    assert p["production_effect"] is False and p["hard_rule_change_allowed"] is False
    assert out["production_thresholds_modified"] is False


def test_liquidity_recovery_v3_rejects_unknown_age_or_bad_contract():
    base={"mode":"RESEARCH_ONLY_LIQUIDITY_RECOVERY_SHADOW_V3","production_gate_changed":False,"no_hindsight":True,"targets":[{"status":"LIQUIDITY_RECOVERY_SHADOW","production_effect":False,"chain":"bsc","token":"0xabc","pair_address":"0xpair","age_proof":{"market_age_verified":False,"market_age_min_days":0}}]}
    assert build({}, {}, [], {}, {}, base)["decision_states"]["SHADOW_TEST"]==0
    base["production_gate_changed"]=True
    assert build({}, {}, [], {}, {}, base)["decision_states"]["SHADOW_TEST"]==0
