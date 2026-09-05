from __future__ import annotations

import inspect

from wallet500 import main as live_main


def test_live_qualification_contract_uses_actual_anomaly_policy() -> None:
    """Prevent strict validation from reintroducing a legacy gate-score qualification rule.

    Production qualification in main._qualify is anomaly-score based. Gate-score
    components are evidence/diagnostic inputs and must not be treated as an independent
    qualification threshold unless production policy itself is explicitly changed.
    """
    source = inspect.getsource(live_main._qualify)
    compact = " ".join(source.split())

    assert "x.get('anomaly_score')" in compact
    assert "score<80" in compact or "score < 80" in compact
    assert "ANOMALY_SCORE_LT_80" in source
    assert "gate_min" not in source
    assert "total_gate" not in source
