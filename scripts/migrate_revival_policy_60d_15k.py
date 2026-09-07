from __future__ import annotations

from pathlib import Path
import re

AGE_DAYS = 60
MIN_LIQUIDITY_USD = 15_000

AGE_TOKENS = (
    "MIN_MARKET_AGE_DAYS",
    "PROJECT_SCOPE_MIN_AGE_DAYS",
    "APPROVED_PRODUCTION_MIN_AGE_DAYS",
    "VETERAN_MIN_DAYS",
    "MIN_AGE_DAYS",
    "minimum_market_age_days",
    "market_age_min_days",
    "veteran_scope_days",
    "market_age_days>=",
    "market_age_min_days>=",
)

LIQ_TOKENS = (
    "MIN_LIQUIDITY_USD",
    "MIN_LIVE_LIQUIDITY_USD",
    "MIN_TRADABLE_LIQUIDITY_USD",
    "MIN_EXECUTION_LIQUIDITY_USD",
    "MIN_EXECUTION_POOL_LIQUIDITY_USD",
    "MIN_LIQ=",
    "MIN_LIQ =",
    "verified_min_liquidity_usd",
    "qualification_min_liquidity_usd",
    "minimum_liquidity_usd",
    "min_live_liquidity_usd",
    "min_execution_liquidity_usd",
    "liquidity_floor_usd",
    "execution_pool_liquidity_usd>=",
    "ACTIVE_LIQUIDITY_USD",
)

AGE_NUM = re.compile(r"(?<!\d)180(?:\.0)?(?!\d)")
LIQ_NUM = re.compile(r"(?<!\d)(?:50_000(?:\.0)?|50000(?:\.0)?)(?!\d)")


def _replace_age_number(match: re.Match[str]) -> str:
    return "60.0" if match.group(0).endswith(".0") else "60"


def _replace_liq_number(match: re.Match[str]) -> str:
    value = match.group(0)
    if "_" in value:
        return "15_000.0" if value.endswith(".0") else "15_000"
    return "15000.0" if value.endswith(".0") else "15000"


def replace_policy_lines(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    out: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        new = line
        if any(token in new for token in AGE_TOKENS):
            new = AGE_NUM.sub(_replace_age_number, new)
        if any(token in new for token in LIQ_TOKENS):
            new = LIQ_NUM.sub(_replace_liq_number, new)
        changed |= new != line
        out.append(new)
    if changed:
        path.write_text("".join(out), encoding="utf-8")
    return changed


def replace_text(path: Path, replacements: list[tuple[str, str]]) -> bool:
    text = path.read_text(encoding="utf-8")
    new = text
    for old, replacement in replacements:
        new = new.replace(old, replacement)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    changed: set[str] = set()
    excluded = {
        Path(".github/workflows/policy-threshold-migration-60d-15k.yml"),
        Path(".github/workflows/policy-threshold-migration-fast.yml"),
    }

    for base in (Path("src/wallet500"), Path("tests"), Path(".github/workflows")):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path in excluded or not path.is_file() or path.suffix not in {".py", ".yml", ".yaml"}:
                continue
            if replace_policy_lines(path):
                changed.add(str(path))

    string_swaps = [
        ("UNDER_180_DAYS", "UNDER_60_DAYS"),
        ("GTE_180_DAYS", "GTE_60_DAYS"),
        ("180D_PLUS", "60D_PLUS"),
        ("180d_plus", "60d_plus"),
        ("AT_LEAST_180_DAYS", "AT_LEAST_60_DAYS"),
        ("at least 180 days", "at least 60 days"),
        ("180-day", "60-day"),
        ("180 day", "60 day"),
        ("BELOW_50K", "BELOW_15K"),
        ("SUB_50K", "SUB_15K"),
        ("50K_PLUS", "15K_PLUS"),
        ("ge_50k", "ge_15k"),
        (">=50000", ">=15000"),
        (">= 50000", ">= 15000"),
    ]
    for base in (Path("src/wallet500"), Path("tests"), Path(".github/workflows")):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path in excluded or not path.is_file() or path.suffix not in {".py", ".yml", ".yaml"}:
                continue
            if replace_text(path, string_swaps):
                changed.add(str(path))

    config = Path("src/wallet500/config.py")
    if replace_text(
        config,
        [("os.getenv(\"WALLET500_VERIFIED_MIN_LIQUIDITY_USD\", \"50000\")", "os.getenv(\"WALLET500_VERIFIED_MIN_LIQUIDITY_USD\", \"15000\")")],
    ):
        changed.add(str(config))

    explicit: dict[str, list[tuple[str, str]]] = {
        "src/wallet500/hot_healthy_radar.py": [
            ("MIN_LIQ = 50000.0", "MIN_LIQ = 15000.0"),
            ("MIN_LIQ=50000.0", "MIN_LIQ=15000.0"),
        ],
        "src/wallet500/realizable_performance.py": [("MIN_LIQ=50000.0", "MIN_LIQ=15000.0")],
        "src/wallet500/arbitrum_revival_universe.py": [
            ("MIN_AGE_DAYS=180; MIN_LIQUIDITY=50000.0", "MIN_AGE_DAYS=60; MIN_LIQUIDITY=15000.0")
        ],
        "src/wallet500/quality_shadow.py": [
            ('and _f(mark.get("liquidity_usd")) >= 50000', 'and _f(mark.get("liquidity_usd")) >= 15000')
        ],
        "src/wallet500/external_only_paper.py": [
            ("snap['liquidity_usd']<50000", "snap['liquidity_usd']<15000")
        ],
        "src/wallet500/revival_prewaking_wallet_evidence.py": [
            ('REVIVAL_PREWAKING_ACTIVE_LIQUIDITY_USD", "50000"', 'REVIVAL_PREWAKING_ACTIVE_LIQUIDITY_USD", "15000"')
        ],
    }
    for name, replacements in explicit.items():
        path = Path(name)
        if path.exists() and replace_text(path, replacements):
            changed.add(str(path))

    policy = Path("docs/OLD_COIN_REVIVAL_POLICY.md")
    if policy.exists():
        text = policy.read_text(encoding="utf-8")
        new = re.sub(r"(?<!\d)180(?!\d)", "60", text)
        if new != text:
            policy.write_text(new, encoding="utf-8")
            changed.add(str(policy))

    dash = Path("src/wallet500/reawakening_dashboard.py")
    dash_text = dash.read_text(encoding="utf-8")
    old_import = """from .reawakening_shadow import (\n    MIN_CONFIRMATION_SPAN_MINUTES,\n    MIN_LIQUIDITY_RETENTION,\n    REQUIRED_CONSECUTIVE,\n    observation_passes,\n)"""
    new_import = """from .reawakening_shadow import (\n    MIN_CONFIRMATION_SPAN_MINUTES,\n    MIN_LIQUIDITY_RETENTION,\n    MIN_LIQUIDITY_USD,\n    MIN_MARKET_AGE_DAYS,\n    REQUIRED_CONSECUTIVE,\n    observation_passes,\n)"""
    if old_import in dash_text:
        dash_text = dash_text.replace(old_import, new_import)
    elif "MIN_MARKET_AGE_DAYS," not in dash_text:
        raise SystemExit("REAWAKENING_DASH_IMPORT_PATTERN_MISSING")

    old_block = """        gate_passed = len(reasons)\n        activity_passed = int(metrics.get(\"activity_checks_passed\") or 0)\n        activity_available = int(metrics.get(\"activity_checks_available\") or 0)\n        waiting_confirmation = ("""
    new_block = """        gate_passed = len(reasons)\n        activity_passed = int(metrics.get(\"activity_checks_passed\") or 0)\n        activity_available = int(metrics.get(\"activity_checks_available\") or 0)\n\n        # Near-recovery is a positive recovery surface, not a list of every historical reject.\n        # Fail closed on market age, current liquidity and actual returning activity.\n        market_age_verified = snap.get(\"market_age_verified\") is True or record.get(\"market_age_verified\") is True\n        market_age_days = _f(snap.get(\"market_age_min_days\") or record.get(\"market_age_min_days\"))\n        liquidity_recovered_for_watch = _f(metrics.get(\"liquidity_usd\")) >= MIN_LIQUIDITY_USD\n        activity_returning = activity_passed >= 1\n        if (\n            not market_age_verified\n            or market_age_days < MIN_MARKET_AGE_DAYS\n            or not liquidity_recovered_for_watch\n            or not activity_returning\n        ):\n            continue\n\n        waiting_confirmation = ("""
    if old_block in dash_text:
        dash_text = dash_text.replace(old_block, new_block)
    elif "liquidity_recovered_for_watch" not in dash_text:
        raise SystemExit("REAWAKENING_DASH_FILTER_PATTERN_MISSING")

    dash_text = dash_text.replace(
        '            "liquidity_floor_usd": 50000,\n            "exact_pair_locked": True,',
        '            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,\n            "liquidity_floor_usd": MIN_LIQUIDITY_USD,\n            "near_recovery_requires_positive_activity": True,\n            "exact_pair_locked": True,',
    )
    dash.write_text(dash_text, encoding="utf-8")
    changed.add(str(dash))

    shadow = Path("src/wallet500/reawakening_shadow.py")
    shadow_text = shadow.read_text(encoding="utf-8")
    if "MIN_MARKET_AGE_DAYS = 60" not in shadow_text:
        anchor = "MIN_LIQUIDITY_USD = 15_000.0\n"
        if anchor not in shadow_text:
            raise SystemExit("REAWAKENING_SHADOW_LIQ_ANCHOR_MISSING")
        shadow_text = shadow_text.replace(anchor, anchor + "MIN_MARKET_AGE_DAYS = 60\n", 1)

    old_checks = """    checks = {\n        \"source_live_survival_failed\": str(record.get(\"first_reject_source\") or \"\") == ELIGIBLE_SOURCE,\n        \"liquidity_only_failure_present\": \"CURRENT_LIQUIDITY_BELOW_15K\" in reasons,\n        \"other_quality_checks_passed\": \"PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION\" in reasons,\n        \"no_hard_reversal_reason\": not bool(reasons & HARD_EXCLUDED_REASONS),\n    }"""
    new_checks = """    snap = record.get(\"first_reject_snapshot\") if isinstance(record.get(\"first_reject_snapshot\"), dict) else {}\n    age_verified = snap.get(\"market_age_verified\") is True or record.get(\"market_age_verified\") is True\n    age_days = _f(snap.get(\"market_age_min_days\") or record.get(\"market_age_min_days\"))\n    checks = {\n        \"source_live_survival_failed\": str(record.get(\"first_reject_source\") or \"\") == ELIGIBLE_SOURCE,\n        \"veteran_age_verified_60d_plus\": age_verified and age_days >= MIN_MARKET_AGE_DAYS,\n        \"liquidity_only_failure_present\": \"CURRENT_LIQUIDITY_BELOW_15K\" in reasons,\n        \"other_quality_checks_passed\": \"PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION\" in reasons,\n        \"no_hard_reversal_reason\": not bool(reasons & HARD_EXCLUDED_REASONS),\n    }"""
    if old_checks in shadow_text:
        shadow_text = shadow_text.replace(old_checks, new_checks)
    elif "veteran_age_verified_60d_plus" not in shadow_text:
        raise SystemExit("REAWAKENING_SHADOW_ELIGIBILITY_PATTERN_MISSING")
    shadow.write_text(shadow_text, encoding="utf-8")
    changed.add(str(shadow))

    for path in list(Path("tests").rglob("*.py")) + list(Path(".github/workflows").rglob("*.yml")):
        if path in excluded:
            continue
        if replace_text(path, [("ACTIVE_LIQUIDITY_USD >= 50000", "ACTIVE_LIQUIDITY_USD >= 15000")]):
            changed.add(str(path))

    for path in Path("src/wallet500").rglob("*.py"):
        replacements = [
            (
                "EARLIEST_ATH_OR_ATL_DATE_MUST_PROVE_AT_LEAST_180_DAYS_OF_MARKET_HISTORY",
                "EARLIEST_ATH_OR_ATL_DATE_MUST_PROVE_AT_LEAST_60_DAYS_OF_MARKET_HISTORY",
            ),
            (
                "EXACT_LOCKED_PAIR_OR_OLDEST_CURRENT_EXACT_TOKEN_PAIR_MUST_PROVE_AT_LEAST_180_DAYS",
                "EXACT_LOCKED_PAIR_OR_OLDEST_CURRENT_EXACT_TOKEN_PAIR_MUST_PROVE_AT_LEAST_60_DAYS",
            ),
        ]
        if replace_text(path, replacements):
            changed.add(str(path))

    assert 'WALLET500_VERIFIED_MIN_LIQUIDITY_USD", "15000"' in config.read_text(encoding="utf-8")
    assert "MIN_MARKET_AGE_DAYS = 60" in Path("src/wallet500/mature_age_gate.py").read_text(encoding="utf-8")
    assert "MIN_TRADABLE_LIQUIDITY_USD = 15_000.0" in Path("src/wallet500/production_risk_gate.py").read_text(encoding="utf-8")
    assert "MIN_LIQUIDITY_USD = 15_000.0" in shadow.read_text(encoding="utf-8")
    assert "MIN_MARKET_AGE_DAYS = 60" in shadow.read_text(encoding="utf-8")
    assert "liquidity_recovered_for_watch" in dash.read_text(encoding="utf-8")

    print("CHANGED_PATHS")
    for name in sorted(changed):
        print(name)


if __name__ == "__main__":
    main()
