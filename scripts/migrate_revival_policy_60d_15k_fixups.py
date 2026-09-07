from __future__ import annotations

from pathlib import Path
import re


def replace(path: Path, replacements: list[tuple[str, str]]) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new = text
    for old, rep in replacements:
        new = new.replace(old, rep)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    changed: set[str] = set()

    # Normalize machine-readable reason labels that encode the policy boundary.
    label_swaps = [
        ("LT_50K", "LT_15K"),
        ("BROKE_50K", "BROKE_15K"),
        ("UNDER_180D", "UNDER_60D"),
        ("LT_180D", "LT_60D"),
    ]
    for base in (Path("src/wallet500"), Path("tests"), Path(".github/workflows")):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".yml", ".yaml"}:
                continue
            if replace(path, label_swaps):
                changed.add(str(path))

    # One policy metadata key contains an extra word and is not caught by the first pass.
    for base in (Path("src/wallet500"), Path("tests"), Path(".github/workflows")):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".yml", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8")
            lines = []
            touched = False
            for line in text.splitlines(keepends=True):
                new = line
                if "minimum_verified_market_age_days" in line:
                    new = re.sub(r"(?<!\d)180(?:\.0)?(?!\d)", lambda m: "60.0" if m.group(0).endswith(".0") else "60", line)
                touched |= new != line
                lines.append(new)
            if touched:
                path.write_text("".join(lines), encoding="utf-8")
                changed.add(str(path))

    # Historical 50K-era rejection labels remain in persisted ledgers. Eligibility under
    # the new policy must be decided by the captured numeric liquidity, not by renaming history.
    shadow = Path("src/wallet500/reawakening_shadow.py")
    old = '''    snap = record.get("first_reject_snapshot") if isinstance(record.get("first_reject_snapshot"), dict) else {}\n    age_verified = snap.get("market_age_verified") is True or record.get("market_age_verified") is True\n    age_days = _f(snap.get("market_age_min_days") or record.get("market_age_min_days"))\n    checks = {\n        "source_live_survival_failed": str(record.get("first_reject_source") or "") == ELIGIBLE_SOURCE,\n        "veteran_age_verified_60d_plus": age_verified and age_days >= MIN_MARKET_AGE_DAYS,\n        "liquidity_only_failure_present": "CURRENT_LIQUIDITY_BELOW_15K" in reasons,\n        "other_quality_checks_passed": "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION" in reasons,\n        "no_hard_reversal_reason": not bool(reasons & HARD_EXCLUDED_REASONS),\n    }'''
    new = '''    snap = record.get("first_reject_snapshot") if isinstance(record.get("first_reject_snapshot"), dict) else {}\n    age_verified = snap.get("market_age_verified") is True or record.get("market_age_verified") is True\n    age_days = _f(snap.get("market_age_min_days") or record.get("market_age_min_days"))\n    first_liquidity = _f(snap.get("liquidity_usd"))\n    had_liquidity_floor_reason = bool(\n        {"CURRENT_LIQUIDITY_BELOW_15K", "CURRENT_LIQUIDITY_BELOW_50K"} & reasons\n    )\n    liquidity_failed_current_policy = (\n        first_liquidity > 0\n        and first_liquidity < MIN_LIQUIDITY_USD\n        and had_liquidity_floor_reason\n    )\n    checks = {\n        "source_live_survival_failed": str(record.get("first_reject_source") or "") == ELIGIBLE_SOURCE,\n        "veteran_age_verified_60d_plus": age_verified and age_days >= MIN_MARKET_AGE_DAYS,\n        "liquidity_only_failure_present": liquidity_failed_current_policy,\n        "other_quality_checks_passed": "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION" in reasons,\n        "no_hard_reversal_reason": not bool(reasons & HARD_EXCLUDED_REASONS),\n    }'''
    if old not in shadow.read_text(encoding="utf-8"):
        raise SystemExit("REAWAKENING_CURRENT_POLICY_ELIGIBILITY_BLOCK_MISSING")
    if replace(shadow, [(old, new)]):
        changed.add(str(shadow))

    # Tests that intentionally exercise the policy boundary must move with the policy.
    test_replacements: dict[str, list[tuple[str, str]]] = {
        "tests/test_arbitrum_revival_universe.py": [
            ("PAIR_AGE_LT_180D_OR_UNKNOWN", "PAIR_AGE_LT_60D_OR_UNKNOWN"),
        ],
        "tests/test_candidate_evidence_envelope.py": [
            ('coin["dex_pair_liquidity_usd"] = 42000', 'coin["dex_pair_liquidity_usd"] = 14000'),
        ],
        "tests/test_catalyst_focus.py": [
            ("market(liquidity_usd=49000)", "market(liquidity_usd=14999)"),
            ("market(price_usd=1,liquidity_usd=40000)", "market(price_usd=1,liquidity_usd=14000)"),
            ("LIQUIDITY_BROKE_50K", "LIQUIDITY_BROKE_15K"),
        ],
        "tests/test_cex_spot_watch_telegram.py": [
            ('bad["market_age_min_days"] = 100', 'bad["market_age_min_days"] = 59'),
        ],
        "tests/test_decision_engine_v1.py": [
            ('row["production_live_liquidity_usd"] = 20_000', 'row["production_live_liquidity_usd"] = 10_000'),
        ],
        "tests/test_fresh_solana_gate.py": [
            ('"liquidity_usd": 33580.75', '"liquidity_usd": 13580.75'),
            ('"liquidity_usd": 36804.34', '"liquidity_usd": 13804.34'),
            ('"liquidity_usd": 42000', '"liquidity_usd": 14000'),
            ('"liquidity_usd": 40000', '"liquidity_usd": 13000'),
        ],
        "tests/test_hot_email_alerts.py": [
            ("market_age_days=179", "market_age_days=59"),
            ("liquidity_usd=49999", "liquidity_usd=14999"),
        ],
        "tests/test_hot_healthy_radar.py": [
            ("UNDER_180D_MARKET_AGE", "UNDER_60D_MARKET_AGE"),
        ],
        "tests/test_lifecycle_strategy.py": [
            ("liq=49999", "liq=14999"),
        ],
        "tests/test_multichain_veteran_revival.py": [
            ("liq=49999", "liq=14999"),
            ("LIVE_LIQUIDITY_LT_50K", "LIVE_LIQUIDITY_LT_15K"),
        ],
        "tests/test_paper_portfolio.py": [
            ("liquidity=49999.99", "liquidity=14999.99"),
        ],
        "tests/test_production_risk_gate.py": [
            ("'liquidity_usd':49999", "'liquidity_usd':14999"),
        ],
        "tests/test_production_status.py": [
            ('["minimum_verified_market_age_days"] == 180', '["minimum_verified_market_age_days"] == 60'),
        ],
        "tests/test_real_alerts.py": [
            ("EXECUTION_POOL_LIQUIDITY_LT_50K", "EXECUTION_POOL_LIQUIDITY_LT_15K"),
        ],
        "tests/test_revival_forensics_v2.py": [
            ('"market_age_min_days": 179', '"market_age_min_days": 59'),
        ],
        "tests/test_system_health.py": [
            ('payload["qualification_min_liquidity_usd"] = 20000', 'payload["qualification_min_liquidity_usd"] = 10000'),
        ],
        "tests/test_system_integrity_audit.py": [
            ('"market_age_days": 179', '"market_age_days": 59'),
        ],
        "tests/test_telegram_exact_pair.py": [
            ('row["market_age_min_days"] = 179', 'row["market_age_min_days"] = 59'),
        ],
    }
    for name, reps in test_replacements.items():
        path = Path(name)
        if replace(path, reps):
            changed.add(str(path))

    # Reawakening test records now model a real 60d+ token that failed the new 15K floor.
    for name in ("tests/test_reawakening_shadow.py", "tests/test_reawakening_forward_tracker.py"):
        path = Path(name)
        text = path.read_text(encoding="utf-8")
        text = text.replace('"liquidity_usd": 42_000,', '"liquidity_usd": 12_000,')
        marker = '            "price_usd": 0.001,\n'
        addition = (
            '            "market_age_verified": True,\n'
            '            "market_age_min_days": 90,\n'
        )
        if addition not in text:
            if marker not in text:
                raise SystemExit(f"REAWAKENING_TEST_FIXTURE_MARKER_MISSING:{name}")
            text = text.replace(marker, marker + addition, 1)
        path.write_text(text, encoding="utf-8")
        changed.add(str(path))

    dashboard_test = Path("tests/test_reawakening_dashboard.py")
    text = dashboard_test.read_text(encoding="utf-8")
    marker = '                        "price_usd": 1.0,\n'
    addition = (
        '                        "market_age_verified": True,\n'
        '                        "market_age_min_days": 90,\n'
    )
    if addition not in text:
        if text.count(marker) < 2:
            raise SystemExit("REAWAKENING_DASHBOARD_TEST_MARKERS_MISSING")
        text = text.replace(marker, marker + addition)
    dashboard_test.write_text(text, encoding="utf-8")
    changed.add(str(dashboard_test))

    # New policy boundary assertions: 59d/14999 reject; 60d/15000 are the minimum.
    shadow_test = Path("tests/test_reawakening_shadow.py")
    text = shadow_test.read_text(encoding="utf-8")
    boundary_test = '''\n\ndef test_reawakening_age_gate_is_fail_closed_at_60_days():\n    young = reject_record()\n    young["first_reject_snapshot"]["market_age_min_days"] = 59\n    assert eligible_reject(young)[0] is False\n\n    unknown = reject_record()\n    unknown["first_reject_snapshot"].pop("market_age_verified", None)\n    assert eligible_reject(unknown)[0] is False\n\n    boundary = reject_record()\n    boundary["first_reject_snapshot"]["market_age_min_days"] = 60\n    assert eligible_reject(boundary)[0] is True\n'''
    if "test_reawakening_age_gate_is_fail_closed_at_60_days" not in text:
        shadow_test.write_text(text.rstrip() + boundary_test + "\n", encoding="utf-8")
        changed.add(str(shadow_test))

    # Keep the migration CI fast: the repository-live-data integrity test requires the
    # intentionally omitted multi-GB data directory and is exercised by normal repo CI.
    workflow = Path(".github/workflows/policy-threshold-migration-fast.yml")
    if replace(workflow, [("python -m pytest -q\n", "python -m pytest -q -k 'not repository_live_data_has_no_critical_integrity_findings'\n")]):
        changed.add(str(workflow))

    print("FIXUP_CHANGED_PATHS")
    for name in sorted(changed):
        print(name)


if __name__ == "__main__":
    main()
