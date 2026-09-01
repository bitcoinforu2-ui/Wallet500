from wallet500.reawakening_shadow import first_forward_trigger, observation_passes


PAIR = "0x9793a9cBb04f781433254e4530398107E6a8dcee"


def row(at, ret, price, liquidity, volume, buys, sells):
    return {
        "observed_at": at,
        "return_pct": ret,
        "price_usd": price,
        "liquidity_usd": liquidity,
        "volume_h1": volume,
        "buys_h1": buys,
        "sells_h1": sells,
        "pair_address": PAIR,
    }


def test_flork_shape_triggers_only_after_two_recovery_observations():
    history = [
        row("t0", -75, .00014, 41_000, 8_000, 40, 42),
        row("t1", 45, .0008, 100_000, 2_500_000, 6300, 5200),  # turnover too extreme
        row("t2", 64, .000895, 112_000, 143_000, 498, 312),
        row("t3", 101, .001097, 124_000, 208_000, 590, 460),
    ]
    trigger = first_forward_trigger({"history": history})
    assert trigger is not None
    assert trigger["triggered_at"] == "t3"
    assert trigger["first_confirmation_at"] == "t2"


def test_single_spike_never_triggers():
    history = [
        row("t0", -80, .0001, 40_000, 5_000, 20, 25),
        row("t1", 10, .0005, 80_000, 100_000, 200, 150),
        row("t2", -30, .0003, 45_000, 90_000, 150, 200),
    ]
    assert first_forward_trigger({"history": history}) is None


def test_missing_pair_or_liquidity_is_blocked():
    current = row("t1", 5, .0005, 80_000, 100_000, 200, 150)
    current["pair_address"] = None
    passed, _, _ = observation_passes(current, row("t0", -70, .0004, 70_000, 20_000, 50, 50), -70)
    assert passed is False


def test_future_rows_cannot_create_an_earlier_trigger():
    base = [
        row("t0", -75, .00014, 41_000, 8_000, 40, 42),
        row("t1", 5, .0005, 80_000, 100_000, 200, 150),
    ]
    assert first_forward_trigger({"history": base}) is None
    later = base + [row("t2", 15, .0006, 85_000, 110_000, 220, 160)]
    assert first_forward_trigger({"history": later})["triggered_at"] == "t2"
