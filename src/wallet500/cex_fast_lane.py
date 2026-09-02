from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .cex_identity import run as resolve_identity
from .cex_identity_preflight import run as verify_age_and_identity
from .cex_revival import run_cex_revival
from .real_alerts import run as build_real_alerts

DATA = Path("data")


def run(data_dir: Path = DATA) -> dict:
    """Refresh the CEX veteran-revival lane before slower research stages.

    This lane exists so a CEX anomaly does not wait behind historical/DNA work
    before its exact identity and DEX status can reach the dashboard. It does
    not bypass any REAL ALERT gate and it never makes a CEX-only signal actionable.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    raw = run_cex_revival(data_dir, now)
    age = verify_age_and_identity(data_dir / "cex-revival-radar.json")
    identity = resolve_identity(data_dir / "cex-revival-radar.json")
    real = build_real_alerts(data_dir)
    return {
        "status": "OK",
        "generated_at": now,
        "raw_cex_alerts": raw.get("alerts_count", 0),
        "age_identity_preflight": age,
        "dex_identity": identity,
        "real_alert_feed": real,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
