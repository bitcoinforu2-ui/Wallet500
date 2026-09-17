from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_telegram_with_intelligence_shadow.py"
spec = importlib.util.spec_from_file_location("run_telegram_with_intelligence_shadow", MODULE_PATH)
shadow = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(shadow)


def test_shadow_exact_pair_match_and_slogan_replacement():
    row = {
        "chain": "arbitrum",
        "token_address": "0xAa00000000000000000000000000000000000001",
        "pair_address": "0xBb00000000000000000000000000000000000002",
    }
    key = shadow.identity_key(row)
    index = {
        key: {
            **row,
            "score": 72.5,
            "label": "CONFLUENCE",
            "status": "CURRENT",
            "independent_positive_families": 4,
            "evidence_age_minutes": 3.5,
            "hard_risks": [],
        }
    }
    text = shadow.inject("header\nVerified Intelligence. The Pure Truth.\nfooter", row, index)
    assert "Verified Intelligence. The Pure Truth." not in text
    assert "72.5/100 — CONFLUENCE" in text
    assert "independent positive families: 4" in text
    assert "SHADOW" in text


def test_shadow_wrong_pair_never_matches():
    row = {
        "chain": "arbitrum",
        "token_address": "0xAa00000000000000000000000000000000000001",
        "pair_address": "0xBb00000000000000000000000000000000000002",
    }
    wrong = dict(row, pair_address="0xCc00000000000000000000000000000000000003")
    index = {
        shadow.identity_key(wrong): {
            **wrong,
            "score": 99,
            "label": "EXCEPTIONAL_CONFLUENCE",
            "status": "CURRENT",
        }
    }
    text = shadow.inject("Verified Intelligence. The Pure Truth.", row, index)
    assert "NOT AVAILABLE (SHADOW)" in text
    assert "99" not in text


def test_evm_case_insensitive_but_solana_case_sensitive():
    evm_a = {"chain": "ETH", "token_address": "0xAbC", "pair_address": "0xDeF"}
    evm_b = {"chain": "ethereum", "token_address": "0xabc", "pair_address": "0xdef"}
    assert shadow.identity_key(evm_a) == shadow.identity_key(evm_b)

    sol_a = {"chain": "solana", "token_address": "AbCdEf", "pair_address": "XyZ123"}
    sol_b = {"chain": "solana", "token_address": "abcdef", "pair_address": "xyz123"}
    assert shadow.identity_key(sol_a) != shadow.identity_key(sol_b)
