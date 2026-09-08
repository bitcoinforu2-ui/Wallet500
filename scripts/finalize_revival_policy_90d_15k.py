from __future__ import annotations

from pathlib import Path


def replace(path: str, pairs: list[tuple[str, str]]) -> None:
    p = Path(path)
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    new = text
    for old, value in pairs:
        new = new.replace(old, value)
    if new != text:
        p.write_text(new, encoding="utf-8")


def main() -> None:
    # Decision guard: research and production now share the same project-universe boundary.
    replace("src/wallet500/decision_snapshot_guard.py", [
        ("RESEARCH_MIN_AGE_DAYS = 60", "RESEARCH_MIN_AGE_DAYS = 90"),
        ("market_age_verified_60d_plus", "market_age_verified_90d_plus"),
        ("enforce 60d scope", "enforce 90d scope"),
        ("enforce 180d", "enforce 90d"),
        ("remain 180d", "remain 90d"),
        ("production 180d scope", "production 90d scope"),
        ("$50K execution pool liquidity", "$15K execution pool liquidity"),
        ("report 180d scope", "report 90d scope"),
    ])

    # Telegram had an inline 50K gate outside the canonical constants.
    replace("src/wallet500/telegram_alerts.py", [
        ("MIN_MARKET_AGE_DAYS = 90\n", "MIN_MARKET_AGE_DAYS = 90\nMIN_LIQUIDITY_USD = 15_000.0\n"),
        ("if liquidity < 50_000 or volume < 15_000 or activity < 50:",
         "if liquidity < MIN_LIQUIDITY_USD or volume < 15_000 or activity < 50:"),
    ])

    # Survivor wave watch is an active Revival watch lane, not a historical scoring study.
    replace("src/wallet500/survivor_wave_watch.py", [
        ("LIQ_FLOOR = 50_000.0", "LIQ_FLOOR = 15_000.0"),
    ])

    # Survivor veteran bridge had semantic strings hard-coded to 60d.
    replace("src/wallet500/survivor_veteran_gate.py", [
        ("UNDER_60D_MARKET_AGE", "UNDER_90D_MARKET_AGE"),
        ("VERIFIED_60D_PLUS", "VERIFIED_90D_PLUS"),
        ("UNDER_60D_BLOCKED", "UNDER_90D_BLOCKED"),
        ("verified market age >=60 days", "verified market age >=90 days"),
    ])

    # Operator-facing contracts must describe the same values the code enforces.
    replace("src/wallet500/orchestrator.py", [
        ("180d veteran, exact-token/pair, $50k liquidity", "90d veteran, exact-token/pair, $15k liquidity"),
    ])
    replace("src/wallet500/production_age_governance.py", [
        ("VETERAN_ONLY_SCOPE_MUST_BE_180D_EVERYWHERE", "VETERAN_ONLY_SCOPE_MUST_BE_90D_EVERYWHERE"),
        ("VETERAN_ONLY_SCOPE_MUST_BE_60D_EVERYWHERE", "VETERAN_ONLY_SCOPE_MUST_BE_90D_EVERYWHERE"),
    ])
    replace("src/wallet500/cex_fast_lane.py", [
        ("VETERAN_ONLY_SCOPE_MUST_BE_60D_EVERYWHERE", "VETERAN_ONLY_SCOPE_MUST_BE_90D_EVERYWHERE"),
        ("VETERAN_ONLY_SCOPE_MUST_BE_180D_EVERYWHERE", "VETERAN_ONLY_SCOPE_MUST_BE_90D_EVERYWHERE"),
    ])
    replace("src/wallet500/revival_funnel_diagnostics.py", [
        ('_num(age_gate.get("minimum_market_age_days")) or 60', '_num(age_gate.get("minimum_market_age_days")) or 90'),
        ("VETERAN_180D_IS_PROJECT_SCOPE_NOT_ALPHA_THRESHOLD", "VETERAN_90D_IS_PROJECT_SCOPE_NOT_ALPHA_THRESHOLD"),
        ("VETERAN_60D_IS_PROJECT_SCOPE_NOT_ALPHA_THRESHOLD", "VETERAN_90D_IS_PROJECT_SCOPE_NOT_ALPHA_THRESHOLD"),
    ])

    # Boundary fixtures: 89d / $14,999 are now the immediately-below-floor cases.
    replace("tests/test_decision_snapshot_guard.py", [
        ('"research_scope_days"] == 60', '"research_scope_days"] == 90'),
        ('"production_scope_days"] == 180', '"production_scope_days"] == 90'),
        ('"production_minimum_execution_pool_liquidity_usd"] == 50_000', '"production_minimum_execution_pool_liquidity_usd"] == 15_000'),
        ("test_guard_rejects_production_alert_under_180d_or_50k", "test_guard_rejects_production_alert_under_90d_or_15k"),
        ('"market_age_days": 179', '"market_age_days": 89'),
        ('"execution_pool_liquidity_usd": 49_999', '"execution_pool_liquidity_usd": 14_999'),
    ])
    replace("tests/test_multichain_veteran_revival.py", [
        ("market_age_pair_days\"] < 180", "market_age_pair_days\"] < 90"),
        ("market_age_registry_days\"] > 180", "market_age_registry_days\"] > 90"),
    ])

    # A narrow invariant scan catches the exact kind of hidden gate that caused this incident.
    critical = {
        "src/wallet500/decision_snapshot_guard.py": ["RESEARCH_MIN_AGE_DAYS = 90", "PRODUCTION_MIN_AGE_DAYS = 90", "PRODUCTION_MIN_LIQUIDITY_USD = 15_000.0"],
        "src/wallet500/telegram_alerts.py": ["MIN_MARKET_AGE_DAYS = 90", "MIN_LIQUIDITY_USD = 15_000.0", "liquidity < MIN_LIQUIDITY_USD"],
        "src/wallet500/survivor_wave_watch.py": ["LIQ_FLOOR = 15_000.0"],
        "src/wallet500/reawakening_shadow.py": ["MIN_MARKET_AGE_DAYS = 90", "MIN_LIQUIDITY_USD = 15_000.0"],
        "src/wallet500/multichain_veteran_revival.py": ["MIN_VETERAN_AGE_DAYS = 90", "MIN_LIQUIDITY_USD = 15_000.0"],
        "src/wallet500/arbitrum_revival_universe.py": ["MIN_AGE_DAYS=90", "MIN_LIQUIDITY=15000.0"],
    }
    for filename, required in critical.items():
        text = Path(filename).read_text(encoding="utf-8")
        missing = [marker for marker in required if marker not in text]
        if missing:
            raise SystemExit(f"REVIVAL_POLICY_FINALIZER_MISSING:{filename}:{missing}")

    telegram = Path("src/wallet500/telegram_alerts.py").read_text(encoding="utf-8")
    if "liquidity < 50_000" in telegram or "liquidity < 50000" in telegram:
        raise SystemExit("TELEGRAM_50K_HIDDEN_GATE_REMAINS")

    decision = Path("src/wallet500/decision_snapshot_guard.py").read_text(encoding="utf-8")
    for stale in ("enforce 60d scope", "production 180d scope", "$50K execution pool liquidity", "market_age_verified_60d_plus"):
        if stale in decision:
            raise SystemExit(f"DECISION_GUARD_STALE_POLICY_TEXT:{stale}")

    print("REVIVAL_POLICY_90D_15K_FINALIZER_OK")


if __name__ == "__main__":
    main()
