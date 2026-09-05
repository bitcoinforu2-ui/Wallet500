from __future__ import annotations

import inspect

from wallet500 import main as live_main


def test_live_qualification_contract_uses_actual_anomaly_policy() -> None:
    """Prevent strict validation from reintroducing a legacy gate-score qualification rule.

    Production qualification in main.qualify_token is anomaly-score based.  Gate-score
    components are evidence/diagnostic inputs and must not be treated as an independent
    qualification threshold unless production policy itself is explicitly changed.
    """
    source = inspect.getsource(live_main.qualify_token)
    compact = " ".join(source.split())

    assert "anomaly_score >= 80.0" in compact
    assert "gate_min" not in source
    assert "total_gate" not in source
