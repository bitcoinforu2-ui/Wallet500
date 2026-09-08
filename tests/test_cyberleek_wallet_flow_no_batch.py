from wallet500 import cyberleek_wallet_flow_no_batch as nb


def test_rpc_coverage_does_not_treat_decoded_non_swap_as_transport_failure(monkeypatch):
    nb._reset_rpc_metrics()
    values = iter([{"transaction": {}}, None, RuntimeError("boom")])

    def fake_rpc(method, params):
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(nb.flow, "_rpc", fake_rpc)
    out = nb._rpc_individual("getTransaction", [[1], [2], [3]])
    assert len(out) == 3
    assert nb._RPC_FETCH_TOTAL == 3
    assert nb._RPC_FETCH_FAILURES == 1
    assert nb._RPC_FETCH_NULLS == 1

    result = {
        "coverage": {
            "last_run_resolved_swaps": 1,
            "last_run_unresolved": 2,
            "coverage_gap": False,
        }
    }
    c = nb._coverage_metrics(result)
    assert c["rpc_reads_decoded"] == 1
    assert c["rpc_resolution_pct"] == round(1 / 3 * 100, 2)
    assert c["non_attributable_pair_touches"] == 0
    assert c["coverage_quality"] == "PARTIAL"


def test_decoded_non_attributable_touch_is_reported_separately(monkeypatch):
    nb._reset_rpc_metrics()
    monkeypatch.setattr(nb, "_RPC_FETCH_TOTAL", 10)
    monkeypatch.setattr(nb, "_RPC_FETCH_FAILURES", 0)
    monkeypatch.setattr(nb, "_RPC_FETCH_NULLS", 0)
    result = {
        "coverage": {
            "last_run_resolved_swaps": 6,
            "last_run_unresolved": 4,
            "coverage_gap": False,
        }
    }
    c = nb._coverage_metrics(result)
    assert c["rpc_resolution_pct"] == 100.0
    assert c["non_attributable_pair_touches"] == 4
    assert c["trade_attribution_pct"] == 60.0
    assert c["attribution_gap"] is True
    assert c["coverage_gap"] is False
    assert c["coverage_quality"] == "ACCEPTABLE"


def test_all_individual_rpc_failures_still_fail_closed(monkeypatch):
    nb._reset_rpc_metrics()

    def fail(method, params):
        raise RuntimeError("no rpc")

    monkeypatch.setattr(nb.flow, "_rpc", fail)
    try:
        nb._rpc_individual("getTransaction", [[1], [2]])
    except RuntimeError as exc:
        assert "ALL_INDIVIDUAL_READS_FAILED" in str(exc)
    else:
        raise AssertionError("expected fail-closed RuntimeError")
