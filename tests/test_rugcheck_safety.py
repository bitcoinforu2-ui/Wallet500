from wallet500.rugcheck_safety import interpret_summary


def test_locked_lp_without_blocking_risk_passes():
    result = interpret_summary({
        "lpLockedPct": 99.5,
        "score": 42,
        "score_normalised": 12,
        "risks": [{"name": "Mutable metadata", "level": "warn", "score": 10}],
    })
    assert result["verified"] is True
    assert result["lp_integrity_safe"] is True
    assert result["status"] == "RUGCHECK_LP_VERIFIED"


def test_low_locked_lp_is_hard_failure():
    result = interpret_summary({"lpLockedPct": 80.0, "risks": []})
    assert result["lp_integrity_safe"] is False
    assert result["status"] == "RUGCHECK_LP_BELOW_THRESHOLD"


def test_danger_risk_blocks_even_when_lp_locked():
    result = interpret_summary({
        "lpLockedPct": 100.0,
        "risks": [{"name": "Rugged", "level": "danger", "score": 900}],
    })
    assert result["lp_integrity_safe"] is False
    assert result["status"] == "RUGCHECK_BLOCKING_RISK"


def test_missing_lp_truth_stays_unknown():
    result = interpret_summary({"score": 10, "risks": []})
    assert result["verified"] is False
    assert result["lp_integrity_safe"] is None
    assert result["status"] == "RUGCHECK_LP_UNKNOWN"
