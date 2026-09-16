from __future__ import annotations

import json
from pathlib import Path

from wallet500.rag_intelligence import RAGConfig, Wallet500RAG
from wallet500.rag_shadow import run as run_rag_shadow


AS_OF = "2026-09-16T12:00:00+00:00"
BASE_SCORES = {
    "opportunity": 75.0,
    "survival": 80.0,
    "execution": 70.0,
    "timing": 72.0,
    "composite": 75.0,
}


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _event(key: str, at: str, offset: float = 0.0) -> dict:
    scores = {k: v + offset for k, v in BASE_SCORES.items()}
    return {"at": at, "key": key, "scores": scores, "action": "WATCH"}


def _outcome(chain: str, token: str, pair: str, ret: float, captured_at: str) -> dict:
    return {
        "chain": chain,
        "token": token,
        "entry_pair_address": pair,
        "current_pair_address": pair,
        "updated_at": captured_at,
        "age_minutes": 400,
        "current_return_pct": ret,
        "checkpoints": {
            "4h": {
                "return_pct": ret,
                "captured_at": captured_at,
                "pair_address": pair,
            }
        },
    }


def test_future_outcome_is_never_retrieved(tmp_path: Path) -> None:
    key = "solana:oldtoken:oldpair"
    _write(tmp_path / "decision-engine-v1-ledger.json", {"events": [_event(key, "2026-09-16T08:00:00+00:00")]})
    _write(
        tmp_path / "signal-outcomes.json",
        [_outcome("solana", "oldtoken", "oldpair", 80.0, "2026-09-16T13:00:00+00:00")],
    )
    rag = Wallet500RAG(tmp_path)
    result = rag.retrieve(
        {"chain": "solana", "token": "newtoken", "pair_address": "newpair"},
        BASE_SCORES,
        as_of=AS_OF,
    )
    assert result["status"] == "EMPTY"
    assert result["score_delta"] == 0.0


def test_cross_chain_history_is_excluded(tmp_path: Path) -> None:
    eth_key = "ethereum:ethold:ethpair"
    sol_key = "solana:solold:solpair"
    _write(
        tmp_path / "decision-engine-v1-ledger.json",
        {
            "events": [
                _event(eth_key, "2026-09-15T08:00:00+00:00"),
                _event(sol_key, "2026-09-15T09:00:00+00:00"),
            ]
        },
    )
    _write(
        tmp_path / "signal-outcomes.json",
        [
            _outcome("ethereum", "ethold", "ethpair", 900.0, "2026-09-15T12:00:00+00:00"),
            _outcome("solana", "solold", "solpair", 10.0, "2026-09-15T13:00:00+00:00"),
        ],
    )
    rag = Wallet500RAG(tmp_path)
    result = rag.retrieve(
        {"chain": "solana", "token": "newtoken", "pair_address": "newpair"},
        BASE_SCORES,
        as_of=AS_OF,
    )
    assert result["status"] == "READY"
    assert result["sample_count"] == 1
    assert all(case["key"].startswith("solana:") for case in result["top_cases"])


def test_same_candidate_history_is_excluded(tmp_path: Path) -> None:
    same_key = "solana:newtoken:newpair"
    other_key = "solana:oldtoken:oldpair"
    _write(
        tmp_path / "decision-engine-v1-ledger.json",
        {
            "events": [
                _event(same_key, "2026-09-15T08:00:00+00:00"),
                _event(other_key, "2026-09-15T09:00:00+00:00"),
            ]
        },
    )
    _write(
        tmp_path / "signal-outcomes.json",
        [
            _outcome("solana", "newtoken", "newpair", 500.0, "2026-09-15T12:00:00+00:00"),
            _outcome("solana", "oldtoken", "oldpair", 5.0, "2026-09-15T13:00:00+00:00"),
        ],
    )
    rag = Wallet500RAG(tmp_path)
    result = rag.retrieve(
        {"chain": "solana", "token": "newtoken", "pair_address": "newpair"},
        BASE_SCORES,
        as_of=AS_OF,
    )
    assert result["sample_count"] == 1
    assert result["top_cases"][0]["key"] == other_key


def test_score_delta_requires_sample_and_is_bounded(tmp_path: Path) -> None:
    events = []
    outcomes = []
    for i in range(8):
        token = f"old{i}"
        pair = f"pair{i}"
        key = f"solana:{token}:{pair}"
        events.append(_event(key, f"2026-09-15T0{i}:00:00+00:00", offset=float(i % 2)))
        outcomes.append(_outcome("solana", token, pair, 120.0, "2026-09-15T11:00:00+00:00"))
    _write(tmp_path / "decision-engine-v1-ledger.json", {"events": events})
    _write(tmp_path / "signal-outcomes.json", outcomes)
    rag = Wallet500RAG(tmp_path, RAGConfig(max_score_delta=5.0))
    result = rag.retrieve(
        {"chain": "solana", "token": "newtoken", "pair_address": "newpair"},
        BASE_SCORES,
        as_of=AS_OF,
    )
    assert result["sample_count"] >= 5
    assert 0.0 < result["score_delta"] <= 5.0


def test_missing_or_malformed_inputs_fail_open(tmp_path: Path) -> None:
    rag = Wallet500RAG(tmp_path)
    result = rag.retrieve({"chain": "solana"}, BASE_SCORES, as_of=AS_OF)
    assert result["status"] == "EMPTY"
    assert result["score_delta"] == 0.0

    (tmp_path / "decision-engine-v1-ledger.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "signal-outcomes.json").write_text("[broken", encoding="utf-8")
    rag2 = Wallet500RAG(tmp_path)
    result2 = rag2.retrieve({"chain": "solana"}, BASE_SCORES, as_of=AS_OF)
    assert result2["status"] == "EMPTY"
    assert result2["score_delta"] == 0.0


def test_shadow_runner_never_changes_production_action(tmp_path: Path) -> None:
    decision = {
        "key": "solana:newtoken:newpair",
        "chain": "solana",
        "token": "newtoken",
        "pair_address": "newpair",
        "recommended_action": "RESEARCH",
        "scores": BASE_SCORES,
    }
    _write(
        tmp_path / "decision-engine-v1.json",
        {"generated_at": AS_OF, "decisions": [decision]},
    )
    events = []
    outcomes = []
    for i in range(6):
        token = f"old{i}"
        pair = f"pair{i}"
        key = f"solana:{token}:{pair}"
        events.append(_event(key, f"2026-09-15T0{i}:00:00+00:00"))
        outcomes.append(_outcome("solana", token, pair, 150.0, "2026-09-15T11:00:00+00:00"))
    _write(tmp_path / "decision-engine-v1-ledger.json", {"events": events})
    _write(tmp_path / "signal-outcomes.json", outcomes)

    payload = run_rag_shadow(str(tmp_path))
    assert payload["production_change"] is False
    assert payload["automatic_buy"] is False
    assert payload["rows"][0]["production_action_unchanged"] == "RESEARCH"
    assert payload["rows"][0]["rag_shadow_composite"] > BASE_SCORES["composite"]
