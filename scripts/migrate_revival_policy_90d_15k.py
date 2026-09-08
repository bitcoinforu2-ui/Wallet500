from __future__ import annotations

from pathlib import Path
import re

AGE_DAYS = 90
MIN_LIQUIDITY_USD = 15_000.0

AGE_LINE_TOKENS = (
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

AGE_60 = re.compile(r"(?<!\d)60(?:\.0)?(?!\d)")


def _age90(match: re.Match[str]) -> str:
    return "90.0" if match.group(0).endswith(".0") else "90"


def replace_policy_age_lines(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    out: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        new = line
        if any(token in new for token in AGE_LINE_TOKENS):
            new = AGE_60.sub(_age90, new)
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

    # 1) Numeric policy constants/metadata: only lines explicitly describing age policy.
    for path in iter_runtime_policy_files():
        if replace_policy_age_lines(path):
            changed.add(str(path))

    # 2) Semantic labels that encode the old 60-day contract.
    semantic_swaps = [
        ("UNDER_60_DAYS", "UNDER_90_DAYS"),
        ("GTE_60_DAYS", "GTE_90_DAYS"),
        ("60D_PLUS", "90D_PLUS"),
        ("60d_plus", "90d_plus"),
        ("AT_LEAST_60_DAYS", "AT_LEAST_90_DAYS"),
        ("at least 60 days", "at least 90 days"),
        ("60-day", "90-day"),
        ("60 day", "90 day"),
        ("age_verified_60d_plus", "age_verified_90d_plus"),
        ("veteran_age_verified_60d_plus", "veteran_age_verified_90d_plus"),
        ("VERIFIED_MARKET_AGE_GTE_60_DAYS_ONLY", "VERIFIED_MARKET_AGE_GTE_90_DAYS_ONLY"),
        ("ONLY_POSITIVE_EXACT_ID_60D_PLUS_EVIDENCE_IS_CACHED", "ONLY_POSITIVE_EXACT_ID_90D_PLUS_EVIDENCE_IS_CACHED"),
    ]
    for path in iter_runtime_policy_files():
        if replace_text(path, semantic_swaps):
            changed.add(str(path))

    # 3) Reawakening is the recovery lane that exposed the drift. Keep legacy 50K
    # rejection reasons readable, but make the live V2 contract explicitly 90d + 15K.
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

    # 4) The workflow truth validator was still hard-coded to the former $50K floor.
    workflow = Path(".github/workflows/reawakening-shadow.yml")
    wf = workflow.read_text(encoding="utf-8")
    wf = wf.replace(
        "if float(recovery.get('liquidity_gte_usd') or 0) != 50000.0: raise SystemExit('LIQUIDITY_HARD_FLOOR_CHANGED')",
        "if float(recovery.get('liquidity_gte_usd') or 0) != 15000.0: raise SystemExit('REVIVAL_LIQUIDITY_POLICY_DRIFT')",
    )
    age_guard = "if int((d.get('selection_rule') or {}).get('minimum_market_age_days') or 0) != 90: raise SystemExit('REVIVAL_AGE_POLICY_DRIFT')"
    anchor = "recovery=d.get('recovery_rule') or {}\n"
    if age_guard not in wf:
        if anchor not in wf:
            raise SystemExit("REAWAKENING_WORKFLOW_RECOVERY_ANCHOR_MISSING")
        wf = wf.replace(anchor, anchor + "          " + age_guard + "\n", 1)
    workflow.write_text(wf, encoding="utf-8")
    changed.add(str(workflow))

    # 5) Explicit boundary test: 89 days must fail; 90 days must pass.
    boundary_test = Path("tests/test_reawakening_shadow.py")
    bt = boundary_test.read_text(encoding="utf-8")
    bt = bt.replace("test_reawakening_age_gate_is_fail_closed_at_60_days", "test_reawakening_age_gate_is_fail_closed_at_90_days")
    bt = bt.replace('young["first_reject_snapshot"]["market_age_min_days"] = 59', 'young["first_reject_snapshot"]["market_age_min_days"] = 89')
    bt = bt.replace('boundary["first_reject_snapshot"]["market_age_min_days"] = 60', 'boundary["first_reject_snapshot"]["market_age_min_days"] = 90')
    boundary_test.write_text(bt, encoding="utf-8")
    changed.add(str(boundary_test))

    # 6) Policy documentation reflects the current research-universe boundary only.
    policy = Path("docs/OLD_COIN_REVIVAL_POLICY.md")
    if policy.exists():
        p = policy.read_text(encoding="utf-8")
        p2 = p.replace("60 days", "90 days").replace("60-day", "90-day").replace("60D", "90D")
        p2 = re.sub(r"(?<!\d)>=\s*60(?!\d)", ">= 90", p2)
        if p2 != p:
            policy.write_text(p2, encoding="utf-8")
            changed.add(str(policy))

    # 7) Fail the migration if the critical live contract is not exactly aligned.
    shadow_now = shadow.read_text(encoding="utf-8")
    mature_now = Path("src/wallet500/mature_age_gate.py").read_text(encoding="utf-8")
    workflow_now = workflow.read_text(encoding="utf-8")
    assert "MIN_MARKET_AGE_DAYS = 90" in shadow_now
    assert "MIN_LIQUIDITY_USD = 15_000.0" in shadow_now
    assert '"minimum_market_age_days": MIN_MARKET_AGE_DAYS' in shadow_now
    assert "MIN_MARKET_AGE_DAYS = 90" in mature_now
    assert "REVIVAL_LIQUIDITY_POLICY_DRIFT" in workflow_now
    assert "REVIVAL_AGE_POLICY_DRIFT" in workflow_now
    assert "!= 15000.0" in workflow_now

    forbidden_live_markers = []
    for path in iter_runtime_policy_files():
        text = path.read_text(encoding="utf-8")
        if "age_verified_60d_plus" in text or "veteran_age_verified_60d_plus" in text:
            forbidden_live_markers.append(str(path))
    if forbidden_live_markers:
        raise SystemExit("LEGACY_60D_RUNTIME_MARKERS_REMAIN:" + ",".join(forbidden_live_markers))

    print("REVIVAL_POLICY_90D_15K_MIGRATION_OK")
    print("CHANGED_PATHS")
    for name in sorted(changed):
        print(name)


if __name__ == "__main__":
    main()
