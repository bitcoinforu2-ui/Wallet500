from __future__ import annotations

from pathlib import Path
import re

AGE_DAYS = 90
MIN_LIQUIDITY_USD = 15_000.0

# Only policy-bearing identifiers are migrated. Historical data files are never rewritten.
AGE_LINE_TOKENS = (
    "MIN_MARKET_AGE_DAYS",
    "MIN_VETERAN_AGE_DAYS",
    "PROJECT_SCOPE_MIN_AGE_DAYS",
    "APPROVED_PRODUCTION_MIN_AGE_DAYS",
    "PRODUCTION_MIN_AGE_DAYS",
    "VETERAN_MIN_DAYS",
    "MIN_AGE_DAYS",
    "minimum_market_age_days",
    "minimum_verified_market_age_days",
    "market_age_min_days",
    "veteran_scope_days",
    "market_age_days>=",
    "market_age_min_days>=",
)

LIQ_LINE_TOKENS = (
    "MIN_LIQUIDITY_USD",
    "MIN_LIQUIDITY=",
    "MIN_LIQUIDITY =",
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

AGE_OLD = re.compile(r"(?<!\d)(?:60|180)(?:\.0)?(?!\d)")
LIQ_OLD = re.compile(r"(?<!\d)(?:50_000(?:\.0)?|50000(?:\.0)?)(?!\d)")


def _age90(match: re.Match[str]) -> str:
    return "90.0" if match.group(0).endswith(".0") else "90"


def _liq15k(match: re.Match[str]) -> str:
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
        if any(token in new for token in AGE_LINE_TOKENS):
            new = AGE_OLD.sub(_age90, new)
        if any(token in new for token in LIQ_LINE_TOKENS):
            new = LIQ_OLD.sub(_liq15k, new)
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


def iter_runtime_policy_files() -> list[Path]:
    files: list[Path] = []
    for base in (Path("src/wallet500"), Path("tests"), Path(".github/workflows")):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".yml", ".yaml"}:
                continue
            # Preserve the historical 60d migration artifacts as an audit trail.
            if "policy-threshold-migration-60d-15k" in path.name:
                continue
            files.append(path)
    return files


def main() -> None:
    changed: set[str] = set()

    # 1) Numeric policy constants/metadata: 60/180 -> 90 and 50K -> 15K only
    # on lines that explicitly carry a policy identifier.
    for path in iter_runtime_policy_files():
        if replace_policy_lines(path):
            changed.add(str(path))

    # 2) Semantic labels that encode old age/liquidity contracts.
    semantic_swaps = [
        ("UNDER_60_DAYS", "UNDER_90_DAYS"),
        ("UNDER_180_DAYS", "UNDER_90_DAYS"),
        ("GTE_60_DAYS", "GTE_90_DAYS"),
        ("GTE_180_DAYS", "GTE_90_DAYS"),
        ("60D_PLUS", "90D_PLUS"),
        ("180D_PLUS", "90D_PLUS"),
        ("60d_plus", "90d_plus"),
        ("180d_plus", "90d_plus"),
        ("AT_LEAST_60_DAYS", "AT_LEAST_90_DAYS"),
        ("AT_LEAST_180_DAYS", "AT_LEAST_90_DAYS"),
        ("at least 60 days", "at least 90 days"),
        ("at least 180 days", "at least 90 days"),
        ("60-day", "90-day"),
        ("180-day", "90-day"),
        ("60 day", "90 day"),
        ("180 day", "90 day"),
        ("PAIR_AGE_LT_60D_OR_UNKNOWN", "PAIR_AGE_LT_90D_OR_UNKNOWN"),
        ("PAIR_AGE_LT_180D_OR_UNKNOWN", "PAIR_AGE_LT_90D_OR_UNKNOWN"),
        ("age_verified_60d_plus", "age_verified_90d_plus"),
        ("age_verified_180d_plus", "age_verified_90d_plus"),
        ("veteran_age_verified_60d_plus", "veteran_age_verified_90d_plus"),
        ("veteran_age_verified_180d_plus", "veteran_age_verified_90d_plus"),
        ("VERIFIED_MARKET_AGE_GTE_60_DAYS_ONLY", "VERIFIED_MARKET_AGE_GTE_90_DAYS_ONLY"),
        ("VERIFIED_MARKET_AGE_GTE_180_DAYS_ONLY", "VERIFIED_MARKET_AGE_GTE_90_DAYS_ONLY"),
        ("ONLY_POSITIVE_EXACT_ID_60D_PLUS_EVIDENCE_IS_CACHED", "ONLY_POSITIVE_EXACT_ID_90D_PLUS_EVIDENCE_IS_CACHED"),
        ("ONLY_POSITIVE_EXACT_ID_180D_PLUS_EVIDENCE_IS_CACHED", "ONLY_POSITIVE_EXACT_ID_90D_PLUS_EVIDENCE_IS_CACHED"),
        ("VETERAN_COIN_REVIVAL_ONLY_180D_MIN", "VETERAN_COIN_REVIVAL_ONLY_90D_MIN"),
        ("VETERAN_COIN_REVIVAL_ONLY_60D_MIN", "VETERAN_COIN_REVIVAL_ONLY_90D_MIN"),
    ]
    for path in iter_runtime_policy_files():
        if replace_text(path, semantic_swaps):
            changed.add(str(path))

    # 3) Compact/bare liquidity forms and test boundaries that do not carry a
    # standard policy identifier on the same line.
    explicit_fixups: dict[str, list[tuple[str, str]]] = {
        "src/wallet500/quality_shadow.py": [
            ('and _f(mark.get("liquidity_usd")) >= 50000', 'and _f(mark.get("liquidity_usd")) >= 15000'),
        ],
        "src/wallet500/external_only_paper.py": [
            ("snap['liquidity_usd']<50000", "snap['liquidity_usd']<15000"),
        ],
        "src/wallet500/revival_prewaking_wallet_evidence.py": [
            ('REVIVAL_PREWAKING_ACTIVE_LIQUIDITY_USD", "50000"', 'REVIVAL_PREWAKING_ACTIVE_LIQUIDITY_USD", "15000"'),
        ],
        "src/wallet500/config.py": [
            ('WALLET500_VERIFIED_MIN_LIQUIDITY_USD", "50000"', 'WALLET500_VERIFIED_MIN_LIQUIDITY_USD", "15000"'),
        ],
        "tests/test_arbitrum_revival_universe.py": [
            ("test_under_180_fails_closed", "test_under_90_fails_closed"),
            ("test_under_60_fails_closed", "test_under_90_fails_closed"),
            ("snap(liq=49999)", "snap(liq=14999)"),
        ],
        "tests/test_multichain_veteran_revival.py": [
            ("test_unknown_or_under_180d_age_fails_closed", "test_unknown_or_under_90d_age_fails_closed"),
        ],
    }
    for name, replacements in explicit_fixups.items():
        path = Path(name)
        if path.exists() and replace_text(path, replacements):
            changed.add(str(path))

    # 4) Reawakening is the recovery lane that exposed the drift. Keep legacy 50K
    # rejection reason *names* readable for immutable history, while the live V2
    # eligibility/recovery contract becomes explicitly 90d + 15K.
    shadow = Path("src/wallet500/reawakening_shadow.py")
    shadow_text = shadow.read_text(encoding="utf-8")
    shadow_text = shadow_text.replace(
        '            "first_reject_source": ELIGIBLE_SOURCE,\n            "required_reasons": sorted(REQUIRED_REASONS),',
        '            "first_reject_source": ELIGIBLE_SOURCE,\n            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,\n            "required_reasons": sorted(REQUIRED_REASONS),',
    )
    shadow_text = shadow_text.replace(
        '            "the exact pair must remain identical and liquidity must be back above the unchanged $50K hard floor",',
        '            "the exact pair must remain identical and liquidity must be back above the $15K Revival floor",',
    )
    shadow.write_text(shadow_text, encoding="utf-8")
    changed.add(str(shadow))

    # 5) The Reawakening truth validator was the observed failure point.
    workflow = Path(".github/workflows/reawakening-shadow.yml")
    wf = workflow.read_text(encoding="utf-8")
    wf = wf.replace(
        "if float(recovery.get('liquidity_gte_usd') or 0) != 50000.0: raise SystemExit('LIQUIDITY_HARD_FLOOR_CHANGED')",
        "if float(recovery.get('liquidity_gte_usd') or 0) != 15000.0: raise SystemExit('REVIVAL_LIQUIDITY_POLICY_DRIFT')",
    )
    # If generic policy replacement already changed the number but not the stale name.
    wf = wf.replace("raise SystemExit('LIQUIDITY_HARD_FLOOR_CHANGED')", "raise SystemExit('REVIVAL_LIQUIDITY_POLICY_DRIFT')")
    age_guard = "if int((d.get('selection_rule') or {}).get('minimum_market_age_days') or 0) != 90: raise SystemExit('REVIVAL_AGE_POLICY_DRIFT')"
    anchor = "recovery=d.get('recovery_rule') or {}\n"
    if age_guard not in wf:
        if anchor not in wf:
            raise SystemExit("REAWAKENING_WORKFLOW_RECOVERY_ANCHOR_MISSING")
        wf = wf.replace(anchor, anchor + "          " + age_guard + "\n", 1)
    workflow.write_text(wf, encoding="utf-8")
    changed.add(str(workflow))

    # 6) Explicit Reawakening boundary: 89 days fails; 90 passes.
    boundary_test = Path("tests/test_reawakening_shadow.py")
    bt = boundary_test.read_text(encoding="utf-8")
    bt = bt.replace("test_reawakening_age_gate_is_fail_closed_at_60_days", "test_reawakening_age_gate_is_fail_closed_at_90_days")
    bt = bt.replace("test_reawakening_age_gate_is_fail_closed_at_180_days", "test_reawakening_age_gate_is_fail_closed_at_90_days")
    bt = bt.replace('young["first_reject_snapshot"]["market_age_min_days"] = 59', 'young["first_reject_snapshot"]["market_age_min_days"] = 89')
    bt = bt.replace('young["first_reject_snapshot"]["market_age_min_days"] = 179', 'young["first_reject_snapshot"]["market_age_min_days"] = 89')
    bt = bt.replace('boundary["first_reject_snapshot"]["market_age_min_days"] = 60', 'boundary["first_reject_snapshot"]["market_age_min_days"] = 90')
    bt = bt.replace('boundary["first_reject_snapshot"]["market_age_min_days"] = 180', 'boundary["first_reject_snapshot"]["market_age_min_days"] = 90')
    boundary_test.write_text(bt, encoding="utf-8")
    changed.add(str(boundary_test))

    # 7) Policy documentation reflects the current project universe contract.
    policy = Path("docs/OLD_COIN_REVIVAL_POLICY.md")
    if policy.exists():
        p = policy.read_text(encoding="utf-8")
        p2 = p
        for old in ("60 days", "180 days"):
            p2 = p2.replace(old, "90 days")
        for old in ("60-day", "180-day"):
            p2 = p2.replace(old, "90-day")
        p2 = p2.replace("60D", "90D").replace("180D", "90D")
        p2 = re.sub(r"(?<!\d)>=\s*(?:60|180)(?!\d)", ">= 90", p2)
        if p2 != p:
            policy.write_text(p2, encoding="utf-8")
            changed.add(str(policy))

    # 8) Fail migration if critical live contracts are not exactly aligned.
    shadow_now = shadow.read_text(encoding="utf-8")
    mature_now = Path("src/wallet500/mature_age_gate.py").read_text(encoding="utf-8")
    workflow_now = workflow.read_text(encoding="utf-8")
    arbitrum_now = Path("src/wallet500/arbitrum_revival_universe.py").read_text(encoding="utf-8")
    multichain_now = Path("src/wallet500/multichain_veteran_revival.py").read_text(encoding="utf-8")
    production_now = Path("src/wallet500/production_status.py").read_text(encoding="utf-8")
    guard_now = Path("src/wallet500/decision_snapshot_guard.py").read_text(encoding="utf-8")

    assert "MIN_MARKET_AGE_DAYS = 90" in shadow_now
    assert "MIN_LIQUIDITY_USD = 15_000.0" in shadow_now
    assert '"minimum_market_age_days": MIN_MARKET_AGE_DAYS' in shadow_now
    assert "MIN_MARKET_AGE_DAYS = 90" in mature_now
    assert "MIN_AGE_DAYS=90" in arbitrum_now or "MIN_AGE_DAYS = 90" in arbitrum_now
    assert "MIN_LIQUIDITY=15000.0" in arbitrum_now or "MIN_LIQUIDITY = 15000.0" in arbitrum_now
    assert "MIN_VETERAN_AGE_DAYS = 90" in multichain_now
    assert "MIN_LIQUIDITY_USD = 15_000.0" in multichain_now
    assert "MIN_MARKET_AGE_DAYS = 90" in production_now
    assert "MIN_LIQUIDITY_USD = 15_000.0" in production_now
    assert "PRODUCTION_MIN_AGE_DAYS = 90" in guard_now
    assert "PRODUCTION_MIN_LIQUIDITY_USD = 15_000.0" in guard_now
    assert "REVIVAL_LIQUIDITY_POLICY_DRIFT" in workflow_now
    assert "REVIVAL_AGE_POLICY_DRIFT" in workflow_now
    assert "!= 15000.0" in workflow_now

    forbidden_live_markers = []
    for path in iter_runtime_policy_files():
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in (
            "age_verified_60d_plus",
            "age_verified_180d_plus",
            "veteran_age_verified_60d_plus",
            "veteran_age_verified_180d_plus",
            "PAIR_AGE_LT_60D_OR_UNKNOWN",
            "PAIR_AGE_LT_180D_OR_UNKNOWN",
        )):
            forbidden_live_markers.append(str(path))
    if forbidden_live_markers:
        raise SystemExit("LEGACY_AGE_RUNTIME_MARKERS_REMAIN:" + ",".join(forbidden_live_markers))

    print("REVIVAL_POLICY_90D_15K_MIGRATION_OK")
    print("CHANGED_PATHS")
    for name in sorted(changed):
        print(name)


if __name__ == "__main__":
    main()
