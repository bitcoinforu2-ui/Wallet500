from __future__ import annotations

from wallet500 import cash_verified as cv
from wallet500 import solana_exact_pair_quote as seq


def _pair(seed: int) -> str:
    raw = bytes(((seed + i) % 256 for i in range(32)))
    return seq._b58encode(raw)


def _quote(pair: str, token_in: str, token_out: str, amount_out: int = 2_000_000) -> dict:
    pair_bytes = list(seq._b58decode(pair) or b"")
    return {
        "amount_out": amount_out,
        "min_amount_out": max(1, amount_out - 1000),
        "route_plan": [
            {
                "amount_in": "1000000",
                "amount_out": str(amount_out),
                "dex_address": pair,
                "dex_label": "TEST_DEX",
                "dex_program_id": _pair(9),
                "token_in": token_in,
                "token_out": token_out,
            }
        ],
        "instructions": [
            {
                "accounts": [
                    {"pubkey": pair_bytes, "is_signer": False, "is_writable": True},
                ],
                "program_id": list(seq._b58decode(_pair(10)) or b""),
                "data": [1, 2, 3],
            }
        ],
        "zid": "abc",
    }


def test_entry_quote_requires_single_leg_locked_pair_and_instruction_account(monkeypatch) -> None:
    pair = _pair(1)
    token = _pair(2)
    q = _quote(pair, cv.SOLANA_USDC, token, 5_000_000)

    monkeypatch.setattr(cv, "KEY", "test-key")
    monkeypatch.setattr(cv, "_post_json", lambda *args, **kwargs: q)
    monkeypatch.setattr(cv, "solana_token_decimals", lambda _token: (6, None))

    out, err = seq.entry_quote(
        {"chain": "solana", "token": token, "pair_address": pair},
        1.0,
    )

    assert err is None
    assert out is not None
    assert out["status"] == "VERIFIED"
    assert out["exact_pair_constrained"] is True
    assert out["quoted_pair_address"] == pair
    assert out["quantity"] == 5.0
    assert out["proof_level"] == "SOLANA_0X_SINGLE_LEG_LOCKED_PAIR_ACCOUNT_PROOF_NOT_EXECUTED_V1"


def test_route_fails_closed_when_router_uses_another_pair(monkeypatch) -> None:
    pair = _pair(3)
    wrong_pair = _pair(4)
    token = _pair(5)
    q = _quote(wrong_pair, cv.SOLANA_USDC, token)

    monkeypatch.setattr(cv, "KEY", "test-key")
    monkeypatch.setattr(cv, "_post_json", lambda *args, **kwargs: q)

    out, err = seq.entry_quote(
        {"chain": "solana", "token": token, "pair_address": pair},
        1.0,
    )

    assert out is None
    assert err == "SOLANA_ROUTE_DEX_ADDRESS_NOT_LOCKED_PAIR"


def test_route_fails_closed_on_split_or_multileg_route() -> None:
    pair = _pair(6)
    token = _pair(7)
    q = _quote(pair, cv.SOLANA_USDC, token)
    q["route_plan"].append(dict(q["route_plan"][0]))

    proven, err = seq._route_proves_exact_pair(
        q,
        pair=pair,
        token_in=cv.SOLANA_USDC,
        token_out=token,
    )

    assert proven is False
    assert err == "SOLANA_ROUTE_NOT_SINGLE_LEG"
