from wallet500.kol_forward_experiment import _dt, _is_original_call, _source_numbers, _template_hash


def test_original_call_rejects_retrospective_update():
    assert _is_original_call("$ABC CA: 7TdDuWRJACtjqWWbUR5JEiUyhG2UyV4LJTnfWPoPX3iu MC: $71k") is True
    assert _is_original_call("$ABC just hit 2x from our call entry MC $71k") is False


def test_source_numbers_parse_compact_amounts():
    values = _source_numbers("MC: $2.58M · Liq: $136k")
    assert values["source_stated_market_cap_usd"] == 2_580_000
    assert values["source_stated_liquidity_usd"] == 136_000


def test_template_hash_ignores_ca_and_numbers():
    a = _template_hash("CALL CA: 7TdDuWRJACtjqWWbUR5JEiUyhG2UyV4LJTnfWPoPX3iu MC: $71k")
    b = _template_hash("CALL CA: BRZ5aeJCDuruA42V1CntqKvofa2G7DS3yyxx1pZEpump MC: $99k")
    assert a == b


def test_datetime_normalization_accepts_unix_and_iso():
    assert _dt(1_700_000_000) is not None
    assert _dt("2026-08-31T20:00:00Z").tzinfo is not None
