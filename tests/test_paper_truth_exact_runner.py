from __future__ import annotations

from wallet500 import paper_truth_exact_runner as runner


def test_runner_dispatches_solana_to_fail_closed_exact_pair_verifier(monkeypatch) -> None:
    expected = {
        "status": "VERIFIED",
        "exact_pair_constrained": True,
        "quoted_pair_address": "PAIR",
    }
    called = {}

    def fake_entry(row, size):
        called["row"] = row
        called["size"] = size
        return expected, None

    monkeypatch.setattr(runner.seq, "entry_quote", fake_entry)
    out, err = runner._entry_quote({"chain": "solana", "token": "TOKEN", "pair_address": "PAIR"})

    assert err is None
    assert out == expected
    assert called["size"] == runner.ptp.POSITION_SIZE


def test_runner_keeps_unknown_chain_unverified() -> None:
    out, err = runner._entry_quote({"chain": "unknown", "token": "TOKEN", "pair_address": "PAIR"})
    assert out is None
    assert err == "EXACT_PAIR_EXECUTION_VERIFIER_NOT_IMPLEMENTED_FOR_CHAIN"
