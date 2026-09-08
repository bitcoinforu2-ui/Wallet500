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


def test_reawakening_contract_is_exactly_90d_15k() -> None:
    text = _text("src/wallet500/reawakening_shadow.py")
    assert _numeric_assignment(text, "MIN_MARKET_AGE_DAYS") == 90.0
    assert _numeric_assignment(text, "MIN_LIQUIDITY_USD") == 15000.0
    assert '"minimum_market_age_days": MIN_MARKET_AGE_DAYS' in text
    assert "veteran_age_verified_90d_plus" in text
    assert "$15K Revival floor" in text


def test_cross_chain_arbitrum_revival_uses_same_floor() -> None:
    text = _text("src/wallet500/arbitrum_revival_universe.py")
    assert _numeric_assignment(text, "MIN_AGE_DAYS") == 90.0
    assert _numeric_assignment(text, "MIN_LIQUIDITY") == 15000.0


def test_reawakening_workflow_validator_matches_runtime_policy() -> None:
    text = _text(".github/workflows/reawakening-shadow.yml")
    assert "REVIVAL_AGE_POLICY_DRIFT" in text
    assert "REVIVAL_LIQUIDITY_POLICY_DRIFT" in text
    assert "!= 15000.0" in text
    assert "minimum_market_age_days" in text
    assert "LIQUIDITY_HARD_FLOOR_CHANGED" not in text


def test_legacy_60d_semantic_keys_are_not_live_runtime_contracts() -> None:
    forbidden = []
    for path in list(Path("src/wallet500").rglob("*.py")) + list(Path("tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "age_verified_60d_plus" in text or "veteran_age_verified_60d_plus" in text:
            forbidden.append(str(path))
    assert forbidden == []
