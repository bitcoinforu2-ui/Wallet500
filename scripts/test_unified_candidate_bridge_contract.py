from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unified_candidate_bridge as bridge


def main() -> None:
    # Regression: explicit 0 liquidity is real evidence and must never be treated
    # as "missing" and replaced by a later fallback source.
    assert bridge.first_present(0, 25000, 50000) == 0
    assert bridge.first_present(0.0, 25000.0) == 0.0

    # Only None means "missing" and is allowed to fall through.
    assert bridge.first_present(None, 25000, 50000) == 25000
    assert bridge.first_present(None, None, 50000) == 50000
    assert bridge.first_present(None, None, None) is None

    print("UNIFIED_CANDIDATE_BRIDGE_ZERO_VS_NONE_REGRESSION_OK")


if __name__ == "__main__":
    main()
