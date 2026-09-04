from wallet500.reawakening_shadow import (
    eligible_reject,
    first_forward_trigger,
    observation_passes,
)

PAIR = "0x9793a9cBb04f781433254e4530398107E6a8dcee"


def reject_record(source="LIVE_SURVIVAL_FAILED", extra_reasons=None, rejected_at="2026-09-01T10:00:00+00:00"):
    reasons = [
        "CURRENT_LIQUIDITY_BELOW_50K",
        "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION",
    ]
    if extra_reasons:
        reasons.extend(extra_reasons)
    return {
        "first_reject_source": source,
        "first_rejected_at": rejected_at,
        "identity": {"chain": "bsc", "token": "0xabc", "pair_address": PAIR.lower()},
        "first_reject_snapshot": {
            "observed_at": rejected_at,
            "chain": "bsc",
            "token": "0xabc",
            "pair_address": PAIR.lower(),
            "price_usd": 0.001,
            "liquidity_usd": 42_000,
            "live_survival_reasons": reasons,
        },
    }


def row(at, price, liquidity=70_000, volume=50_000, buys=220, sells=160, pair=PAIR):
    return {
        "observed_at": at,
        "price_usd": price,
        "liquidity_usd": liquidity,
        "volume_h1": volume,
        "buys_h1": buys,
        "sells_h1": sells,
        "pair_address": pair,
    }


def test_only_liquidity_only_survival_reject_is_eligible():
    ok, reasons = eligible_reject(reject_record())
    assert ok is True
    assert "LIQUIDITY_ONLY_FAILURE_PRESENT" in reasons

    assert eligible_reject(reject_record(source="HOLDER_CLUSTER_REVIEW"))[0] is False
    assert eligible_reject(reject_record(extra_reasons=["PUMP_THEN_FAST_REVERSAL"]))[0] is False
    assert eligible_reject(reject_record(extra_reasons=["VERIFIED_RETURN_BELOW_MINUS_25PCT"]))[0] is False


def test_activity_separator_requires_three_available_checks_to_pass():
    passed, _, metrics = observation_passes(row("2026-09-01T10:05:00+00:00", 0.0011), 0.001)
    assert passed is True
    assert metrics["activity_checks_available"] == 4
    assert metrics["activity_checks_passed"] == 4

    weak = row("2026-09-01T10:05:00+00:00", 0.0011, volume=15_000, buys=90, sells=100)
    assert observation_passes(weak, 0.001)[0] is False

    missing = row("2026-09-01T10:05:00+00:00", 0.0011)
    missing["buys_h1"] = None
    missing["sells_h1"] = None
    assert observation_passes(missing, 0.001)[0] is False


def test_two_forward_confirmations_need_15m_same_pair_and_anti_chase():
    record = reject_record()
    history = [
        row("2026-09-01T10:05:00+00:00", 0.00110, liquidity=70_000),
        row("2026-09-01T10:12:00+00:00", 0.00112, liquidity=69_000),
    ]
    assert first_forward_trigger(record, history) is None

    history.append(row("2026-09-01T10:20:00+00:00", 0.00115, liquidity=72_000))
    trigger = first_forward_trigger(record, history)
    assert trigger is not None
    assert trigger["triggered_at"] == "2026-09-01T10:20:00+00:00"
    assert trigger["first_confirmation_at"] == "2026-09-01T10:05:00+00:00"
    assert trigger["confirmation_span_minutes"] == 15.0

    chase = [
        row("2026-09-01T10:05:00+00:00", 0.00160),
        row("2026-09-01T10:25:00+00:00", 0.00170),
    ]
    assert first_forward_trigger(record, chase) is None


def test_liquidity_drain_or_pair_change_breaks_confirmation_streak():
    record = reject_record()
    draining = [
        row("2026-09-01T10:05:00+00:00", 0.00110, liquidity=80_000),
        row("2026-09-01T10:25:00+00:00", 0.00112, liquidity=70_000),
    ]
    assert first_forward_trigger(record, draining) is None

    wrong_pair = [
        row("2026-09-01T10:05:00+00:00", 0.00110),
        row("2026-09-01T10:25:00+00:00", 0.00112, pair="0xdeadbeef"),
    ]
    assert first_forward_trigger(record, wrong_pair) is None


def test_pre_reject_rows_cannot_create_trigger():
    record = reject_record(rejected_at="2026-09-01T10:00:00+00:00")
    history = [
        row("2026-09-01T09:20:00+00:00", 0.00105),
        row("2026-09-01T09:40:00+00:00", 0.00108),
        row("2026-09-01T10:05:00+00:00", 0.00110),
    ]
    assert first_forward_trigger(record, history) is None
