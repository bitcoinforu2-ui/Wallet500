from __future__ import annotations

from pathlib import Path
import re

AGE_DAYS = 90
MIN_LIQUIDITY_USD = 15_000
MIN_VOLUME_H1_USD = 15_000
MIN_TXNS_H1 = 30

AGE_TOKENS = (
    "MIN_MARKET_AGE_DAYS", "PROJECT_SCOPE_MIN_AGE_DAYS",
    "APPROVED_PRODUCTION_MIN_AGE_DAYS", "PRODUCTION_MIN_AGE_DAYS",
    "PRODUCTION_MIN_MARKET_AGE_DAYS",
    "RESEARCH_MIN_AGE_DAYS", "VETERAN_MIN_DAYS", "MIN_AGE_DAYS",
    "minimum_market_age_days", "minimum_verified_market_age_days",
    "market_age_min_days", "veteran_scope_days",
)
LIQ_TOKENS = (
    "MIN_LIQUIDITY_USD", "MIN_LIVE_LIQUIDITY_USD",
    "MIN_TRADABLE_LIQUIDITY_USD", "MIN_EXECUTION_LIQUIDITY_USD",
    "MIN_EXECUTION_POOL_LIQUIDITY_USD", "PRODUCTION_MIN_LIQUIDITY_USD",
    "PRODUCTION_MIN_EXECUTION_LIQUIDITY_USD",
    "MIN_LIQ=", "MIN_LIQ =", "verified_min_liquidity_usd",
    "qualification_min_liquidity_usd", "minimum_liquidity_usd",
    "minimum_live_liquidity_usd", "minimum_execution_pool_liquidity_usd",
    "min_live_liquidity_usd", "min_execution_liquidity_usd",
    "liquidity_floor_usd", "ACTIVE_LIQUIDITY_USD",
)
TXN_TOKENS = ("MIN_TXNS_H1", "minimum_txns_h1", "min_txns_h1")

AGE_NUM = re.compile(r"(?<!\d)(?:60|180)(?:\.0)?(?!\d)")
LIQ_NUM = re.compile(r"(?<!\d)(?:50_000|50000)(?:\.0)?(?!\d)")
TXN_NUM = re.compile(r"(?<!\d)50(?!\d)")

SKIP = {
    ".github/workflows/reconcile-revival-policy-90d-15k.yml",
    ".github/workflows/reconcile-revival-policy-90d-15k-fast.yml",
    ".github/workflows/policy-threshold-migration-60d-15k.yml",
    "scripts/migrate_revival_policy_60d_15k.py",
    "scripts/migrate_revival_policy_60d_15k_fixups.py",
    "scripts/reconcile_revival_policy_90d_15k.py",
}
BASES = (Path("src/wallet500"), Path("tests"), Path("scripts"), Path(".github/workflows"))


def _age_repl(match: re.Match[str]) -> str:
    return "90.0" if match.group(0).endswith(".0") else "90"


def _liq_repl(match: re.Match[str]) -> str:
    raw = match.group(0)
    if "_" in raw:
        return "15_000.0" if raw.endswith(".0") else "15_000"
    return "15000.0" if raw.endswith(".0") else "15000"


def reconcile() -> list[str]:
    changed: set[str] = set()
    for base in BASES:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".yml", ".yaml"}:
                continue
            name = str(path)
            if name in SKIP:
                continue
            text = path.read_text(encoding="utf-8")
            out: list[str] = []
            touched = False
            for line in text.splitlines(keepends=True):
                new = line
                if any(token in new for token in AGE_TOKENS):
                    new = AGE_NUM.sub(_age_repl, new)
                if any(token in new for token in LIQ_TOKENS):
                    new = LIQ_NUM.sub(_liq_repl, new)
                if any(token in new for token in TXN_TOKENS):
                    new = TXN_NUM.sub(str(MIN_TXNS_H1), new)
                touched |= new != line
                out.append(new)
            if touched:
                path.write_text("".join(out), encoding="utf-8")
                changed.add(name)

    explicit = {
        "src/wallet500/real_alerts.py": [
            ("return age >= 180, age", "return age >= 90, age"),
            ('"VETERAN_AGE_180D"', '"VETERAN_AGE_90D"'),
            ("VERIFIED_MARKET_AGE_180D_REQUIRED", "VERIFIED_MARKET_AGE_90D_REQUIRED"),
        ],
        "src/wallet500/revival_forensics_v2.py": [
            ("AGE_NOT_VERIFIED_60D_PLUS", "AGE_NOT_VERIFIED_90D_PLUS"),
        ],
        "src/wallet500/mature_age_gate.py": [
            ("UNDER_60_DAYS_OR_AGE_UNVERIFIED", "UNDER_90_DAYS_OR_AGE_UNVERIFIED"),
            ("UNDER_60_DAYS", "UNDER_90_DAYS"),
            ("VERIFIED_MARKET_AGE_GTE_60_DAYS_ONLY", "VERIFIED_MARKET_AGE_GTE_90_DAYS_ONLY"),
            ("AT_LEAST_60_DAYS_OF_MARKET_HISTORY", "AT_LEAST_90_DAYS_OF_MARKET_HISTORY"),
        ],
        "src/wallet500/decision_snapshot_guard.py": [
            ("enforce 60d scope", "enforce 90d scope"),
            ("enforce 180d", "enforce 90d"),
            ("remain 180d", "remain 90d"),
            ("production 180d scope", "production 90d scope"),
            ("outside production 180d scope", "outside production 90d scope"),
            ("lacks $50K execution pool liquidity", "lacks $15K execution pool liquidity"),
        ],
        "tests/test_arbitrum_revival_universe.py": [
            ("test_under_180_fails_closed", "test_under_90_fails_closed"),
            ("snap(liq=49999)", "snap(liq=14999)"),
        ],
        "tests/test_hot_healthy_radar.py": [
            ("test_under_180_day_token_is_quarantined", "test_under_90_day_token_is_quarantined"),
        ],
        "tests/test_revival_forensics_v2.py": [
            ("test_build_t0_fails_closed_under_180", "test_build_t0_fails_closed_under_90"),
        ],
    }
    for name, replacements in explicit.items():
        path = Path(name)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for old, replacement in replacements:
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.add(name)

    safe_swaps = {
        "EXECUTION_POOL_LIQUIDITY_LT_50K": "EXECUTION_POOL_LIQUIDITY_LT_15K",
        "CURRENT_LIQUIDITY_BELOW_50K": "CURRENT_LIQUIDITY_BELOW_15K",
        "LIQUIDITY_LT_50K": "LIQUIDITY_LT_15K",
        "VETERAN_AGE_180D": "VETERAN_AGE_90D",
        "VERIFIED_MARKET_AGE_180D_REQUIRED": "VERIFIED_MARKET_AGE_90D_REQUIRED",
        "PAIR_AGE_LT_60D_OR_UNKNOWN": "PAIR_AGE_LT_90D_OR_UNKNOWN",
        "UNDER_60D_MARKET_AGE": "UNDER_90D_MARKET_AGE",
        "AGE_NOT_VERIFIED_60D_PLUS": "AGE_NOT_VERIFIED_90D_PLUS",
    }
    for base in BASES:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".yml", ".yaml"} or str(path) in SKIP:
                continue
            text = path.read_text(encoding="utf-8")
            new = text
            for old, replacement in safe_swaps.items():
                new = new.replace(old, replacement)
            if new != text:
                path.write_text(new, encoding="utf-8")
                changed.add(str(path))

    for name in ("src/wallet500/arbitrum_revival_universe.py", "src/wallet500/realizable_performance.py"):
        path = Path(name)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            new = text.replace("MIN_TXNS_H1=50", "MIN_TXNS_H1=30").replace("MIN_TXNS_H1 = 50", "MIN_TXNS_H1 = 30")
            if new != text:
                path.write_text(new, encoding="utf-8")
                changed.add(name)

    return sorted(changed)


def verify() -> None:
    checks = {
        "src/wallet500/config.py": ['WALLET500_VERIFIED_MIN_LIQUIDITY_USD", "15000"'],
        "src/wallet500/mature_age_gate.py": ["MIN_MARKET_AGE_DAYS = 90"],
        "src/wallet500/candidate_evidence_envelope.py": ["MIN_MARKET_AGE_DAYS = 90", "MIN_EXECUTION_LIQUIDITY_USD = 15_000.0"],
        "src/wallet500/revival_forensics_v2.py": ["MIN_AGE_DAYS = 90"],
        "src/wallet500/real_alerts.py": ["return age >= 90, age", '"minimum_market_age_days": 90'],
        "src/wallet500/decision_snapshot_guard.py": ["RESEARCH_MIN_AGE_DAYS = 90", "PRODUCTION_MIN_AGE_DAYS = 90", "PRODUCTION_MIN_LIQUIDITY_USD = 15_000.0"],
        "src/wallet500/arbitrum_revival_universe.py": ["MIN_AGE_DAYS=90", "MIN_LIQUIDITY=15000.0", "MIN_VOLUME_H1=15000.0", "MIN_TXNS_H1=30"],
        "scripts/publish_verified_snapshot.py": ["PRODUCTION_MIN_MARKET_AGE_DAYS = 90", "PRODUCTION_MIN_EXECUTION_LIQUIDITY_USD = 15000.0"],
        ".github/workflows/telegram-production-alerts.yml": ["minimum_market_age_days') or 0) != 90", "minimum_market_age_days') != 90"],
        ".github/workflows/revival-smart-money-registry.yml": ["market_age_verified_min_days') or 0) < 90"],
        ".github/workflows/revival-90d-telegram.yml": ["minimum_pair_age_days') or 0)!=90.0", "minimum_liquidity_usd') or 0)!=15000.0", "minimum_txns_h1') or 0)!=30"],
    }
    for name, needles in checks.items():
        text = Path(name).read_text(encoding="utf-8")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            raise SystemExit(f"POLICY_RECONCILE_INVARIANT_FAILED {name}: {missing}")


if __name__ == "__main__":
    changed = reconcile()
    verify()
    print("REVIVAL_POLICY_RECONCILED", {"age_days": AGE_DAYS, "liquidity_usd": MIN_LIQUIDITY_USD, "volume_h1_usd": MIN_VOLUME_H1_USD, "txns_h1": MIN_TXNS_H1})
    print("CHANGED_PATHS", len(changed))
    for path in changed:
        print(path)
