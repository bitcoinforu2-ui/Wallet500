from __future__ import annotations

from typing import Any

ZERO_ADDRESSES = {
    "",
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}

CRITICAL_DIRECT_FIELDS = (
    "is_honeypot",
    "owner_change_balance",
    "selfdestruct",
    "can_take_back_ownership",
)

RISK_WEIGHTS = {
    "is_honeypot": 100,
    "owner_change_balance": 45,
    "selfdestruct": 40,
    "can_take_back_ownership": 35,
    "hidden_owner": 24,
    "transfer_pausable": 20,
    "is_mintable": 18,
    "slippage_modifiable": 16,
    "personal_slippage_modifiable": 18,
    "is_blacklisted": 14,
    "anti_whale_modifiable": 12,
    "is_open_source_false": 12,
    "external_call": 8,
    "is_proxy": 4,
}

def tri_flag(value: Any) -> bool | None:
    if value is True or value == 1:
        return True
    if value is False or value == 0:
        return False
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return None

def _owner_active(raw: dict) -> bool | None:
    owner = str(raw.get("owner_address") or "").strip().lower()
    if owner:
        return owner not in ZERO_ADDRESSES
    owner_pct = raw.get("owner_percent")
    if owner_pct not in (None, ""):
        try:
            return float(owner_pct) > 0
        except (TypeError, ValueError):
            return None
    return None

def _age_bucket(age_minutes: float | None) -> tuple[str, float, float]:
    if age_minutes is None or age_minutes < 0:
        return "UNKNOWN", 1.0, 40.0
    if age_minutes <= 24 * 60:
        return "NEW_24H", 1.35, 35.0
    if age_minutes <= 7 * 24 * 60:
        return "YOUNG_7D", 1.20, 45.0
    if age_minutes <= 30 * 24 * 60:
        return "YOUNG_30D", 1.05, 55.0
    return "MATURE_30D_PLUS", 0.65, 65.0

def evaluate_security(
    raw: dict,
    *,
    age_minutes: float | None,
    previous: dict | None = None,
) -> dict:
    previous = previous if isinstance(previous, dict) else {}
    flags = {
        "is_honeypot": tri_flag(raw.get("is_honeypot")),
        "hidden_owner": tri_flag(raw.get("hidden_owner")),
        "transfer_pausable": tri_flag(raw.get("transfer_pausable")),
        "is_mintable": tri_flag(raw.get("is_mintable")),
        "owner_change_balance": tri_flag(raw.get("owner_change_balance")),
        "selfdestruct": tri_flag(raw.get("selfdestruct")),
        "external_call": tri_flag(raw.get("external_call")),
        "is_proxy": tri_flag(raw.get("is_proxy")),
        "is_blacklisted": tri_flag(raw.get("is_blacklisted")),
        "is_whitelisted": tri_flag(raw.get("is_whitelisted")),
        "trading_cooldown": tri_flag(raw.get("trading_cooldown")),
        "cannot_sell_all": tri_flag(raw.get("cannot_sell_all")),
        "slippage_modifiable": tri_flag(raw.get("slippage_modifiable")),
        "personal_slippage_modifiable": tri_flag(raw.get("personal_slippage_modifiable")),
        "anti_whale_modifiable": tri_flag(raw.get("anti_whale_modifiable")),
        "can_take_back_ownership": tri_flag(raw.get("can_take_back_ownership")),
        "is_open_source": tri_flag(raw.get("is_open_source")),
    }
    owner_active = _owner_active(raw)
    bucket, age_multiplier, buy_threshold = _age_bucket(age_minutes)
    young = bucket in {"NEW_24H", "YOUNG_7D"}

    score = 0.0
    reasons: list[str] = []
    for field, weight in RISK_WEIGHTS.items():
        if field == "is_open_source_false":
            if flags["is_open_source"] is False:
                score += weight
                reasons.append("CONTRACT_NOT_OPEN_SOURCE")
            continue
        if flags.get(field) is True:
            score += weight
            reasons.append(field.upper())

    if owner_active is True and bucket != "MATURE_30D_PLUS":
        score += 5
        reasons.append("ACTIVE_OWNER_YOUNG_TOKEN")

    combos = []
    if flags["hidden_owner"] is True and flags["transfer_pausable"] is True:
        score += 20
        combos.append("HIDDEN_OWNER_PLUS_TRANSFER_PAUSE")
    if flags["is_mintable"] is True and owner_active is True:
        score += 15
        combos.append("ACTIVE_OWNER_PLUS_MINTABLE")
    if flags["is_blacklisted"] is True and owner_active is True:
        score += 12
        combos.append("ACTIVE_OWNER_PLUS_BLACKLIST")
    if flags["slippage_modifiable"] is True and owner_active is True:
        score += 12
        combos.append("ACTIVE_OWNER_PLUS_TAX_MODIFICATION")
    if flags["cannot_sell_all"] is True:
        score += 20
        combos.append("SELL_RESTRICTION")

    reasons.extend(combos)
    score = min(100.0, round(score * age_multiplier, 1))

    direct_critical = [
        field for field in CRITICAL_DIRECT_FIELDS if flags.get(field) is True
    ]
    composite_danger = bool(
        score >= 60
        or "HIDDEN_OWNER_PLUS_TRANSFER_PAUSE" in combos
        or "ACTIVE_OWNER_PLUS_MINTABLE" in combos
        or "SELL_RESTRICTION" in combos
    )
    consecutive_composite = bool(
        composite_danger and previous.get("composite_danger") is True
    )

    hard_risk = bool(direct_critical or (young and consecutive_composite))
    if direct_critical:
        hard_reason = "DIRECT_CRITICAL_CAPABILITY"
    elif young and consecutive_composite:
        hard_reason = "YOUNG_TOKEN_DANGEROUS_AUTHORITY_CONFIRMED_CONSECUTIVELY"
    else:
        hard_reason = None

    source_coverage_ok = flags["is_open_source"] is not False
    buy_eligible = bool(
        not hard_risk
        and source_coverage_ok
        and score < buy_threshold
    )

    if hard_risk:
        tier = "HARD_BLOCK"
    elif score >= 60:
        tier = "CRITICAL_PENDING_RECHECK"
    elif score >= 35:
        tier = "HIGH"
    elif score >= 15:
        tier = "CAUTION"
    else:
        tier = "CLEAR"

    return {
        "provider": "GoPlus Token Security",
        "security_verified": True,
        "age_minutes": round(age_minutes, 2) if age_minutes is not None else None,
        "age_bucket": bucket,
        "age_multiplier": age_multiplier,
        "owner_address": raw.get("owner_address"),
        "creator_address": raw.get("creator_address"),
        "owner_active": owner_active,
        "ownership_renounced_or_no_owner_detected": owner_active is False,
        "flags": flags,
        "risk_score": score,
        "risk_tier": tier,
        "risk_reasons": list(dict.fromkeys(reasons)),
        "dangerous_combinations": combos,
        "direct_critical_capabilities": direct_critical,
        "composite_danger": composite_danger,
        "consecutive_composite_confirmation": consecutive_composite,
        "hard_risk": hard_risk,
        "hard_risk_reason": hard_reason,
        "source_coverage_ok": source_coverage_ok,
        "buy_eligible": buy_eligible,
        "buy_eligibility_threshold": buy_threshold,
        "young_token_policy_applied": young,
    }
