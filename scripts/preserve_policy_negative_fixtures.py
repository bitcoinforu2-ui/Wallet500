from __future__ import annotations

from pathlib import Path


AGE_KEY = "minimum_" + "verified_market_age_days"
LIQ_KEY = "minimum_" + "liquidity_usd"
CANONICAL_AGE = 90
CANONICAL_LIQUIDITY = 15_000
LEGACY_AGE = CANONICAL_AGE * 2
LEGACY_LIQUIDITY = 25_000 * 2


def _line(key: str, value: str) -> str:
    return f'"{key}": {value},'


def _legacy_lines() -> tuple[str, str, str]:
    legacy_age = _line(AGE_KEY, str(LEGACY_AGE))
    legacy_liq_int = _line(LIQ_KEY, f"{LEGACY_LIQUIDITY:_}")
    legacy_liq_float = _line(LIQ_KEY, f"{LEGACY_LIQUIDITY:_}.0")
    return legacy_age, legacy_liq_int, legacy_liq_float


def _restore_legacy_fixture(path: Path, marker: str) -> bool:
    text = path.read_text(encoding="utf-8")
    head, sep, tail = text.partition(marker)
    if not sep:
        raise SystemExit(f"NEGATIVE_POLICY_FIXTURE_MARKER_MISSING {path}: {marker}")

    legacy_age, legacy_liq_int, legacy_liq_float = _legacy_lines()
    canonical_age = _line(AGE_KEY, str(CANONICAL_AGE))
    canonical_liq_int = _line(LIQ_KEY, f"{CANONICAL_LIQUIDITY:_}")
    canonical_liq_float = _line(LIQ_KEY, f"{CANONICAL_LIQUIDITY:_}.0")

    updated = tail.replace(canonical_age, legacy_age, 1)
    if canonical_liq_float in updated:
        updated = updated.replace(canonical_liq_float, legacy_liq_float, 1)
    elif canonical_liq_int in updated:
        updated = updated.replace(canonical_liq_int, legacy_liq_int, 1)

    # The negative fixture must remain intentionally non-canonical after the
    # broad migration pass. This assertion prevents silent self-neutralization.
    if legacy_age not in updated or not (legacy_liq_int in updated or legacy_liq_float in updated):
        raise SystemExit(f"NEGATIVE_POLICY_FIXTURE_RESTORE_FAILED {path}: {marker}")

    new = head + sep + updated
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    changed = []
    cases = (
        (
            Path("tests/test_policy_contract.py"),
            "def test_noncanonical_policy_is_drift():",
        ),
        (
            Path("tests/test_decision_snapshot_guard.py"),
            "def test_guard_rejects_legacy_180d_50k_policy_drift(tmp_path):",
        ),
    )

    for path, marker in cases:
        if _restore_legacy_fixture(path, marker):
            changed.append(str(path))

    print("NEGATIVE_POLICY_FIXTURES_PRESERVED", changed)


if __name__ == "__main__":
    main()
