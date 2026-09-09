from __future__ import annotations

from pathlib import Path


def _restore_legacy_fixture(path: Path, marker: str) -> bool:
    text = path.read_text(encoding="utf-8")
    head, sep, tail = text.partition(marker)
    if not sep:
        raise SystemExit(f"NEGATIVE_POLICY_FIXTURE_MARKER_MISSING {path}: {marker}")

    updated = tail.replace(
        '"minimum_verified_market_age_days": 90,',
        '"minimum_verified_market_age_days": 180,',
        1,
    ).replace(
        '"minimum_liquidity_usd": 15_000.0,',
        '"minimum_liquidity_usd": 50_000.0,',
        1,
    ).replace(
        '"minimum_liquidity_usd": 15_000,',
        '"minimum_liquidity_usd": 50_000,',
        1,
    )

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
