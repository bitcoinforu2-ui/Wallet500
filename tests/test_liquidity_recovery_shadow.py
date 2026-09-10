import json

from wallet500.liquidity_recovery_shadow import eligible_reject, first_forward_trigger, observation_passes, run

PAIR = "0x1111222233334444555566667777888899990000"


def record(liquidity=30000, reasons=None, age=120):
    rs = reasons or ["CURRENT_LIQUIDITY_BELOW_50K", "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION"]
    return {
        "first_reject_source": "LIVE_SURVIVAL_FAILED",
        "first_rejected_at": "2026-09-10T09:00:00+00:00",
        "identity": {"chain": "bsc", "token": "0xabc", "pair_address": PAIR},
        "first_reject_snapshot": {
            "observed_at": "2026-09-10T09:00:00+00:00",
            "chain": "bsc",
            "token": "0xabc",
            "pair_address": PAIR,
            "price_usd": 1.0,
            "liquidity_usd": liquidity,
            "market_age_verified": True,
            "market_age_min_days": age,
            "live_survival_reasons": rs,
        },
    }


def row(at, price=1.05, liquidity=36000, volume=50000, buys=220, sells=160, pair=PAIR):
    return {
        "observed_at": at,
        "pair_address": pair,
        "price_usd": price,
        "liquidity_usd": liquidity,
        "volume_h1": volume,
        "buys_h1": buys,
        "sells_h1": sells,
    }


def test_below_50k_quality_pass_is_eligible_without_lowering_production_gate():
    ok, meta = eligible_reject(record(30000))
    assert ok is True
    assert meta["first_liquidity_usd"] == 30000
    assert eligible_reject(record(50000))[0] is False
    assert eligible_reject(record(14000))[0] is False
    assert eligible_reject(record(30000, ["CURRENT_LIQUIDITY_BELOW_50K"]))[0] is False


def test_hard_failure_and_young_coin_fail_closed():
    bad = record(30000, [
        "CURRENT_LIQUIDITY_BELOW_50K",
        "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION",
        "PUMP_THEN_FAST_REVERSAL",
    ])
    assert eligible_reject(bad)[0] is False
    assert eligible_reject(record(30000, age=89))[0] is False


def test_recovery_can_trigger_before_50k_when_liquidity_and_activity_accelerate():
    passed, metrics = observation_passes(row("2026-09-10T09:05:00+00:00", liquidity=36000), 1.0, 30000)
    assert passed is True
    assert metrics["liquidity_growth_from_reject_pct"] == 20.0

    history = [
        row("2026-09-10T09:05:00+00:00", price=1.04, liquidity=36000),
        row("2026-09-10T09:20:00+00:00", price=1.07, liquidity=38000),
    ]
    trigger = first_forward_trigger(record(30000), history, "2026-09-10T09:01:00+00:00")
    assert trigger is not None
    assert trigger["production_liquidity_gate_met"] is False
    assert trigger["confirmation_span_minutes"] == 15.0


def test_wrong_pair_drain_and_chase_do_not_trigger():
    wrong = [
        row("2026-09-10T09:05:00+00:00", liquidity=36000),
        row("2026-09-10T09:20:00+00:00", liquidity=38000, pair="0xdead"),
    ]
    assert first_forward_trigger(record(), wrong, "2026-09-10T09:01:00+00:00") is None

    drain = [
        row("2026-09-10T09:05:00+00:00", liquidity=42000),
        row("2026-09-10T09:20:00+00:00", liquidity=37000),
    ]
    assert first_forward_trigger(record(), drain, "2026-09-10T09:01:00+00:00") is None

    chase = [
        row("2026-09-10T09:05:00+00:00", price=1.40, liquidity=42000),
        row("2026-09-10T09:20:00+00:00", price=1.45, liquidity=44000),
    ]
    assert first_forward_trigger(record(), chase, "2026-09-10T09:01:00+00:00") is None


def test_run_is_forward_only_and_exact_pair_locked(tmp_path):
    rec = record(30000)
    key = f"bsc|0xabc|{PAIR}"
    (tmp_path / "rejected-candidate-ledger.json").write_text(json.dumps({"records": {key: rec}}))
    (tmp_path / "liquidity-recovery-shadow-state.json").write_text(json.dumps({
        "version": 3,
        "v3_started_at": "2026-09-10T09:01:00+00:00",
        "triggers": {},
    }))
    (tmp_path / "outcome-tracker.json").write_text(json.dumps({"tokens": {
        "x": {
            "chain": "bsc",
            "token": "0xabc",
            "entry_pair_address": PAIR,
            "history": [
                row("2026-09-10T09:00:30+00:00", liquidity=39000),
                row("2026-09-10T09:05:00+00:00", liquidity=36000),
                row("2026-09-10T09:20:00+00:00", liquidity=38000),
            ],
        }
    }}))
    payload = run(str(tmp_path))
    assert payload["production_gate_changed"] is False
    assert payload["production_liquidity_gate_usd"] == 50000
    assert payload["counts"]["eligible_below_50k_rejects"] == 1
    assert payload["counts"]["shadow_triggers"] == 1
    assert payload["targets"][0]["status"] == "LIQUIDITY_RECOVERY_SHADOW"
