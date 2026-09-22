from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CRITICAL_TESTS = (
    "tests/test_accuracy_contracts.py",
    "tests/test_social_precursor.py",
    "tests/test_price_identity_contract.py",
    "tests/test_signal_alert_guard.py",
    "tests/test_safe_json.py",
    "tests/test_decision_snapshot_guard.py",
    "tests/test_decision_replay_lab.py",
    "tests/test_decision_replay_path_metrics.py",
    "tests/test_time_machine_timestamp_truth.py",
    "tests/test_truth_contract.py",
    "tests/test_truth_input_preflight.py",
    "tests/test_truth_verification.py",
    "tests/test_provider_redundancy.py",
    "tests/test_cex_spot_revival.py",
    "tests/test_cex_spot_identity.py",
    "tests/test_cex_early_revival_pending.py",
    "tests/test_cex_fast_current_bypass.py",
    "tests/test_unified_candidate_bridge_recency.py",
    "tests/test_waking_fallbacks.py",
    "tests/test_solana_mintability_gate.py",
    "tests/test_production_risk_gate.py",
    "tests/test_system_integrity_audit.py",
)


def _run(label: str, command: list[str]) -> None:
    print(f"\n=== {label} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(f"FULL GUARD FAILED: {label} (exit {completed.returncode})")


def _verify_contract_files() -> None:
    missing = [path for path in CRITICAL_TESTS if not (ROOT / path).is_file()]
    if missing:
        joined = "\n  - ".join(missing)
        raise SystemExit(
            "FULL GUARD FAILED: critical contract tests are missing:\n  - " + joined
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Wallet500's fast fail-closed code and decision-integrity guard."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="After the critical guard, also run the complete pytest suite.",
    )
    args = parser.parse_args()

    _verify_contract_files()

    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if not tracked:
        raise SystemExit("FULL GUARD FAILED: no tracked Python files found")
    _run(
        "All tracked Python syntax compilation",
        [sys.executable, "-m", "py_compile", *tracked],
    )
    _run(
        "Fatal static defects",
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            ".",
            "--select=E9,F63,F7,F82",
        ],
    )
    _run(
        "Critical truth/alert/replay/provider/accuracy/social contracts",
        [sys.executable, "-m", "pytest", "-q", *CRITICAL_TESTS],
    )

    if args.full:
        _run("Complete regression suite", [sys.executable, "-m", "pytest", "-q"])

    print("\nFULL GUARD PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
