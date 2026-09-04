from __future__ import annotations

from typing import Any

from . import cash_verified as cv

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(raw: bytes) -> str:
    if not raw:
        return ""
    n = int.from_bytes(raw, "big")
    chars: list[str] = []
    while n:
        n, rem = divmod(n, 58)
        chars.append(BASE58_ALPHABET[rem])
    leading = len(raw) - len(raw.lstrip(b"\x00"))
    body = "".join(reversed(chars)) if chars else ""
    return "1" * leading + body


def _b58decode(value: str) -> bytes | None:
    try:
        n = 0
        for ch in str(value or ""):
            n = n * 58 + BASE58_ALPHABET.index(ch)
        body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
        leading = len(value) - len(value.lstrip("1"))
        raw = b"\x00" * leading + body
        return raw if len(raw) == 32 else None
    except Exception:
        return None


def _wire_pubkey(value: Any) -> str | None:
    if isinstance(value, str):
        return value if _b58decode(value) is not None else None
    if isinstance(value, list) and len(value) == 32:
        try:
            raw = bytes(int(x) for x in value)
        except Exception:
            return None
        return _b58encode(raw)
    return None


def _instruction_accounts(quote: dict[str, Any]) -> set[str]:
    accounts: set[str] = set()
    for instruction in quote.get("instructions") or []:
        if not isinstance(instruction, dict):
            continue
        for account in instruction.get("accounts") or []:
            if not isinstance(account, dict):
                continue
            pubkey = _wire_pubkey(account.get("pubkey"))
            if pubkey:
                accounts.add(pubkey)
    return accounts


def _route_proves_exact_pair(
    quote: dict[str, Any],
    *,
    pair: str,
    token_in: str,
    token_out: str,
) -> tuple[bool, str | None]:
    if _b58decode(pair) is None:
        return False, "SOLANA_LOCKED_PAIR_INVALID"
    route = quote.get("route_plan")
    if not isinstance(route, list) or len(route) != 1:
        return False, "SOLANA_ROUTE_NOT_SINGLE_LEG"
    leg = route[0]
    if not isinstance(leg, dict):
        return False, "SOLANA_ROUTE_LEG_INVALID"
    if str(leg.get("token_in") or "") != token_in or str(leg.get("token_out") or "") != token_out:
        return False, "SOLANA_ROUTE_TOKEN_DIRECTION_MISMATCH"
    if str(leg.get("dex_address") or "") != pair:
        return False, "SOLANA_ROUTE_DEX_ADDRESS_NOT_LOCKED_PAIR"
    if pair not in _instruction_accounts(quote):
        return False, "SOLANA_LOCKED_PAIR_NOT_IN_INSTRUCTION_ACCOUNTS"
    try:
        if int(quote.get("amount_out") or 0) <= 0 or int(quote.get("min_amount_out") or 0) <= 0:
            return False, "SOLANA_EXACT_PAIR_ZERO_OUTPUT"
    except Exception:
        return False, "SOLANA_EXACT_PAIR_OUTPUT_INVALID"
    return True, None


def _quote(token_in: str, token_out: str, amount_in: int) -> tuple[dict[str, Any] | None, str | None]:
    if not cv.KEY:
        return None, "ZEROX_API_KEY_MISSING"
    payload = {
        "token_in": token_in,
        "token_out": token_out,
        "amount_in": int(amount_in),
        "taker": cv.SOLANA_TAKER,
        "slippage_bps": 50,
    }
    try:
        q = cv._post_json(cv.SOLANA_API, payload, {"0x-api-key": cv.KEY})
    except Exception as exc:
        return None, "SOLANA_EXACT_PAIR_QUOTE_ERROR:" + type(exc).__name__
    if not isinstance(q, dict):
        return None, "SOLANA_EXACT_PAIR_QUOTE_EMPTY"
    return q, None


def entry_quote(
    row: dict[str, Any],
    position_size_usd: float = 1.0,
) -> tuple[dict[str, Any] | None, str | None]:
    token = str(row.get("token") or row.get("mint") or "")
    pair = str(row.get("pair_address") or row.get("locked_pair_address") or "")
    if not token:
        return None, "TOKEN_MISSING"
    if not pair:
        return None, "PAIR_MISSING"
    amount_in = int(round(float(position_size_usd) * (10 ** cv.SOLANA_USDC_DECIMALS)))
    if amount_in <= 0:
        return None, "POSITION_SIZE_INVALID"

    q, err = _quote(cv.SOLANA_USDC, token, amount_in)
    if err or not q:
        return None, err or "SOLANA_EXACT_PAIR_QUOTE_EMPTY"
    proven, proof_err = _route_proves_exact_pair(
        q,
        pair=pair,
        token_in=cv.SOLANA_USDC,
        token_out=token,
    )
    if not proven:
        return None, proof_err or "SOLANA_EXACT_PAIR_ROUTE_UNPROVEN"

    raw = int(q.get("amount_out") or 0)
    dec, dec_err = cv.solana_token_decimals(token)
    if dec is None:
        return None, dec_err or "TOKEN_DECIMALS_UNVERIFIED"
    quantity = raw / (10 ** int(dec))
    if quantity <= 0:
        return None, "SOLANA_EXACT_PAIR_ENTRY_QUANTITY_INVALID"

    return {
        "status": "VERIFIED",
        "token_amount_base_units": raw,
        "token_decimals": int(dec),
        "quantity": quantity,
        "cost_usd": float(position_size_usd),
        "effective_entry_price_usd": float(position_size_usd) / quantity,
        "stable_symbol": "USDC",
        "exact_pair_constrained": True,
        "quoted_pair_address": pair,
        "proof_level": "SOLANA_0X_SINGLE_LEG_LOCKED_PAIR_ACCOUNT_PROOF_NOT_EXECUTED_V1",
        "route_plan": q.get("route_plan"),
        "zid": q.get("zid"),
    }, None


def exit_quote(position: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    token = str(position.get("token") or "")
    pair = str(position.get("pair_address") or position.get("locked_pair_address") or "")
    try:
        amount = int(position.get("token_amount_base_units") or 0)
    except Exception:
        amount = 0
    if not token or amount <= 0:
        return None, "TOKEN_OR_ENTRY_AMOUNT_MISSING"
    if not pair:
        return None, "PAIR_MISSING"

    q, err = _quote(token, cv.SOLANA_USDC, amount)
    if err or not q:
        return None, err or "SOLANA_EXACT_PAIR_QUOTE_EMPTY"
    proven, proof_err = _route_proves_exact_pair(
        q,
        pair=pair,
        token_in=token,
        token_out=cv.SOLANA_USDC,
    )
    if not proven:
        return None, proof_err or "SOLANA_EXACT_PAIR_ROUTE_UNPROVEN"

    raw = int(q.get("amount_out") or 0)
    value = raw / (10 ** cv.SOLANA_USDC_DECIMALS)
    if value <= 0:
        return None, "SOLANA_EXACT_PAIR_EXIT_VALUE_INVALID"
    return {
        "status": "VERIFIED",
        "quoted_exit_value_usd": value,
        "stable_symbol": "USDC",
        "exact_pair_constrained": True,
        "quoted_pair_address": pair,
        "proof_level": "SOLANA_0X_SINGLE_LEG_LOCKED_PAIR_ACCOUNT_PROOF_NOT_EXECUTED_V1",
        "route_plan": q.get("route_plan"),
        "zid": q.get("zid"),
    }, None
