import json

from wallet500.decision_only_shadow import MODE, build, run


def test_clean_six_of_seven_enters_shadow_only():
    near={"near_alert_leaderboard":[{
        "symbol":"GRIFFAIN","chain":"solana","token_address":"TOK","pair_address":"PAIR",
        "readiness_passed":6,"readiness_total":7,
        "missing_gates":["STRONG_DECISION_LANE"],"blockers":["NO_STRONG_DECISION_LANE"],
        "exact_identity_verified":True,"exact_pair_verified":True,"market_age_verified":True,
        "market_activity_verified":True,"execution_pool_liquidity_usd":1_800_000,
        "source_lane_count":2,"evidence_positive_count":1,"evidence_positive_lanes":["CEX_REVIVAL"],
    }]}
    out=build(near,{"records":{}},observed_at="2026-09-12T09:00:00+00:00")
    assert out["mode"]==MODE
    assert out["current_shadow_candidate_count"]==1
    row=out["current_shadow_candidates"][0]
    assert row["symbol"]=="GRIFFAIN"
    assert row["research_state"]=="SHADOW_TEST_ACTIVE"
    assert row["production_effect"] is False
    assert row["automatic_promotion"] is False
    assert out["production_change_allowed"] is False
    assert out["truth_contract"]["real_alert_gate_unchanged"] is True


def test_hard_blocker_or_single_lane_is_excluded():
    base={
        "symbol":"X","chain":"solana","token_address":"TOK","pair_address":"PAIR",
        "readiness_passed":6,"readiness_total":7,"missing_gates":["STRONG_DECISION_LANE"],
        "blockers":["NO_STRONG_DECISION_LANE"],"exact_identity_verified":True,"exact_pair_verified":True,
        "market_age_verified":True,"market_activity_verified":True,"execution_pool_liquidity_usd":100_000,
        "source_lane_count":2,
    }
    hard=dict(base); hard["blockers"]=["NO_STRONG_DECISION_LANE","EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL"]
    one=dict(base); one["source_lane_count"]=1
    out=build({"near_alert_leaderboard":[hard,one]},{"records":{}})
    assert out["current_shadow_candidate_count"]==0


def test_historical_metrics_use_only_exact_decision_only_entries():
    good={
        "decision_snapshot":{"entry":{
            "readiness_passed":6,"readiness_total":7,"missing_gates":["STRONG_DECISION_LANE"],
            "blockers":["NO_STRONG_DECISION_LANE"],"verified_execution_tradable":True,
            "verified_execution_liquidity_usd":100_000,"source_lane_count":2,
        }},
        "checkpoints":{"24h":{"friction_adjusted_return_pct":25.0}},
    }
    bad={
        "decision_snapshot":{"entry":{
            "readiness_passed":5,"readiness_total":7,
            "missing_gates":["STRONG_DECISION_LANE","INDEPENDENT_CONFIRMATION"],
            "blockers":["NO_STRONG_DECISION_LANE","INDEPENDENT_CONFIRMATION_LT_2"],
            "verified_execution_tradable":True,"verified_execution_liquidity_usd":100_000,"source_lane_count":1,
        }},
        "checkpoints":{"24h":{"friction_adjusted_return_pct":-50.0}},
    }
    out=build({}, {"records":{"good":good,"bad":bad}})
    h24=out["horizons"]["24h"]
    assert out["historical_decision_only_records"]==1
    assert h24["n"]==1
    assert h24["winner_count"]==1
    assert h24["loser_count"]==0
    assert h24["mean_friction_adjusted_return_pct"]==25.0


def test_run_writes_research_only_artifact(tmp_path):
    (tmp_path/"near-alert-observatory.json").write_text(json.dumps({"near_alert_leaderboard":[]}),encoding="utf-8")
    (tmp_path/"research-sample-ledger.json").write_text(json.dumps({"records":{}}),encoding="utf-8")
    out=run(tmp_path,observed_at="2026-09-12T09:00:00+00:00")
    saved=json.loads((tmp_path/"decision-only-shadow.json").read_text(encoding="utf-8"))
    assert saved==out
    assert saved["production_thresholds_modified"] is False
