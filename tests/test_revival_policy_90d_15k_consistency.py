from pathlib import Path
import re


AGE_FILES = {
    "src/wallet500/mature_age_gate.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/reawakening_shadow.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/hot_healthy_radar.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/hot_email_alerts.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/telegram_alerts.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/telegram_real_alerts_v2.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/candidate_evidence_envelope.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/cex_identity_preflight.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/cex_spot_watch_telegram.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/survivor_veteran_gate.py": "VETERAN_MIN_DAYS",
    "src/wallet500/system_integrity_audit.py": "VETERAN_MIN_DAYS",
    "src/wallet500/production_age_governance.py": "PROJECT_SCOPE_MIN_AGE_DAYS",
    "src/wallet500/cex_fast_lane.py": "PROJECT_SCOPE_MIN_AGE_DAYS",
    "src/wallet500/arbitrum_revival_universe.py": "MIN_AGE_DAYS",
    "src/wallet500/multichain_veteran_revival.py": "MIN_VETERAN_AGE_DAYS",
    "src/wallet500/catalyst_wire.py": "MIN_VETERAN_AGE_DAYS",
    "src/wallet500/production_status.py": "MIN_MARKET_AGE_DAYS",
    "src/wallet500/decision_snapshot_guard.py": "PRODUCTION_MIN_AGE_DAYS",
    "src/wallet500/liquidity_truth_guard.py": "PRODUCTION_MIN_MARKET_AGE_DAYS",
}

LIQUIDITY_FILES = {
    "src/wallet500/reawakening_shadow.py": "MIN_LIQUIDITY_USD",
    "src/wallet500/multichain_veteran_revival.py": "MIN_LIQUIDITY_USD",
    "src/wallet500/arbitrum_revival_universe.py": "MIN_LIQUIDITY",
    "src/wallet500/production_status.py": "MIN_LIQUIDITY_USD",
    "src/wallet500/decision_snapshot_guard.py": "PRODUCTION_MIN_LIQUIDITY_USD",
    "src/wallet500/candidate_evidence_envelope.py": "MIN_EXECUTION_LIQUIDITY_USD",
    "src/wallet500/telegram_real_alerts_v2.py": "MIN_LIQUIDITY_USD",
    "src/wallet500/hot_email_alerts.py": "MIN_LIQUIDITY_USD",
    "src/wallet500/hot_healthy_radar.py": "MIN_LIQ",
    "src/wallet500/production_risk_gate.py": "MIN_TRADABLE_LIQUIDITY_USD",
}


def _text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _numeric_assignment(text: str, name: str) -> float:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*([0-9_]+(?:\.[0-9]+)?)", text)
    assert match, f"missing numeric assignment for {name}"
    return float(match.group(1).replace("_", ""))


def test_all_live_revival_age_gates_share_90_day_floor() -> None:
    drift = {}
    for path, constant in AGE_FILES.items():
        value = _numeric_assignment(_text(path), constant)
        if value != 90.0:
            drift[path] = value
    assert drift == {}


def test_all_live_revival_liquidity_gates_share_15k_floor() -> None:
    drift = {}
    for path, constant in LIQUIDITY_FILES.items():
        value = _numeric_assignment(_text(path), constant)
        if value != 15000.0:
            drift[path] = value
    assert drift == {}


def test_reawakening_contract_is_exactly_90d_15k() -> None:
    text = _text("src/wallet500/reawakening_shadow.py")
    assert _numeric_assignment(text, "MIN_MARKET_AGE_DAYS") == 90.0
    assert _numeric_assignment(text, "MIN_LIQUIDITY_USD") == 15000.0
    assert '"minimum_market_age_days": MIN_MARKET_AGE_DAYS' in text
    assert "veteran_age_verified_90d_plus" in text
    assert "$15K Revival floor" in text


def test_cross_chain_revival_uses_same_floor() -> None:
    arbitrum = _text("src/wallet500/arbitrum_revival_universe.py")
    assert _numeric_assignment(arbitrum, "MIN_AGE_DAYS") == 90.0
    assert _numeric_assignment(arbitrum, "MIN_LIQUIDITY") == 15000.0

    multichain = _text("src/wallet500/multichain_veteran_revival.py")
    assert _numeric_assignment(multichain, "MIN_VETERAN_AGE_DAYS") == 90.0
    assert _numeric_assignment(multichain, "MIN_LIQUIDITY_USD") == 15000.0
    assert "PAIR_AGE_LT_90D_OR_UNKNOWN" in multichain


def test_production_truth_guards_match_revival_scope() -> None:
    production = _text("src/wallet500/production_status.py")
    assert _numeric_assignment(production, "MIN_MARKET_AGE_DAYS") == 90.0
    assert _numeric_assignment(production, "MIN_LIQUIDITY_USD") == 15000.0

    guard = _text("src/wallet500/decision_snapshot_guard.py")
    assert _numeric_assignment(guard, "PRODUCTION_MIN_AGE_DAYS") == 90.0
    assert _numeric_assignment(guard, "PRODUCTION_MIN_LIQUIDITY_USD") == 15000.0


def test_reawakening_workflow_validator_matches_runtime_policy() -> None:
    text = _text(".github/workflows/reawakening-shadow.yml")
    assert "REVIVAL_AGE_POLICY_DRIFT" in text
    assert "REVIVAL_LIQUIDITY_POLICY_DRIFT" in text
    assert "!= 15000.0" in text
    assert "minimum_market_age_days" in text
    assert "LIQUIDITY_HARD_FLOOR_CHANGED" not in text


def test_legacy_age_semantic_keys_are_not_live_runtime_contracts() -> None:
    # Build legacy tokens from fragments so the one-off migration cannot mutate
    # the test itself while it rewrites old runtime semantics.
    old_60 = "6" + "0d_plus"
    old_180 = "18" + "0d_plus"
    markers = (
        "age_verified_" + old_60,
        "age_verified_" + old_180,
        "veteran_age_verified_" + old_60,
        "veteran_age_verified_" + old_180,
        "PAIR_AGE_LT_" + "6" + "0D_OR_UNKNOWN",
        "PAIR_AGE_LT_" + "18" + "0D_OR_UNKNOWN",
    )
    forbidden = []
    for path in list(Path("src/wallet500").rglob("*.py")) + list(Path("tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in markers):
            forbidden.append(str(path))
    assert forbidden == []
