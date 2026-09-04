from __future__ import annotations

import math
from datetime import datetime, timezone

PRICE_IDENTITY_CONTRACT_VERSION = 2
PRICE_IDENTITY_V2_ACTIVATED_AT = datetime(2026, 9, 4, 9, 4, 37, tzinfo=timezone.utc)
MIN_EXECUTABLE_LIQUIDITY_USD = 50_000.0
MIN_EXECUTABLE_VOLUME_H1_USD = 15_000.0
MIN_EXECUTABLE_TXNS_H1 = 50
EVM_CHAINS = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "polygon", "optimism", "avalanche"}


def norm_chain(chain) -> str:
    return str(chain or "").lower()


def norm_id(chain, value) -> str:
    value = str(value or "")
    return value.lower() if norm_chain(chain) in EVM_CHAINS else value


def same_id(chain, left, right) -> bool:
    return bool(left and right) and norm_id(chain, left) == norm_id(chain, right)


def parse_dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def finite_positive(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def finite_nonnegative(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def identity_verified_for_target(chain, token, row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("token_identity_verified") is not True:
        # Backward-safe upgrade is permitted only when DexScreener base identity
        # is explicit. Legacy quote-side priceUsd was unsafe.
        return same_id(chain, token, row.get("base_token_address"))
    side = str(row.get("target_token_side") or "").upper()
    if side == "BASE":
        return same_id(chain, token, row.get("base_token_address"))
    if side == "QUOTE":
        return same_id(chain, token, row.get("quote_token_address"))
    return False


def execution_gate(row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    try:
        liquidity = float(row.get("liquidity_usd") or row.get("current_liquidity_usd") or 0)
        volume_h1 = float(row.get("volume_h1") or row.get("current_volume_h1") or 0)
        buys = int(row.get("buys_h1") or 0)
        sells = int(row.get("sells_h1") or 0)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(liquidity)
        and math.isfinite(volume_h1)
        and liquidity >= MIN_EXECUTABLE_LIQUIDITY_USD
        and volume_h1 >= MIN_EXECUTABLE_VOLUME_H1_USD
        and buys + sells >= MIN_EXECUTABLE_TXNS_H1
    )


def entry_identity_proven(*, entry_at, target_side, explicit_v2=False) -> tuple[bool, str]:
    """Prove that a historical entry price was for the tracked token.

    Before V2, Wallet500 copied DexScreener priceUsd. That is valid for a BASE
    tracked token but unsafe for a QUOTE tracked token. Pair side is immutable,
    so a later V2 BASE proof safely validates the historical base-side entry.
    Quote-side legacy entries remain quarantined unless their entry timestamp is
    after V2 activation or explicit V2 entry evidence exists.
    """
    if explicit_v2:
        return True, "EXPLICIT_V2_ENTRY_IDENTITY"
    side = str(target_side or "").upper()
    if side == "BASE":
        return True, "LEGACY_BASE_SIDE_IDENTITY_PROVEN"
    dt = parse_dt(entry_at)
    if dt and dt >= PRICE_IDENTITY_V2_ACTIVATED_AT:
        return True, "POST_V2_ENTRY_IDENTITY"
    return False, "LEGACY_ENTRY_TOKEN_SIDE_UNVERIFIED"


def pct(current, entry):
    current = finite_positive(current)
    entry = finite_positive(entry)
    return ((current / entry) - 1.0) * 100.0 if current is not None and entry is not None else None
