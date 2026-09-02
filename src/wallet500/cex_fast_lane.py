from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .cex_identity import run as resolve_identity
from .cex_identity_preflight import run as verify_age_and_identity
from .cex_revival import run_cex_revival
from .real_alerts import run as build_real_alerts

DATA = Path("data")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _retry(fn, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < attempts - 1:
                time.sleep(1.5 * (i + 1))
    raise last


def run(data_dir: Path = DATA) -> dict:
    """Refresh veteran CEX identity before slower research stages.

    A provider outage may delay a *new* identity, but it must never erase the
    last verified identity feed or crash the rest of Wallet500. All actionable
    semantics remain fail-closed.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    radar_path = data_dir / "cex-revival-radar.json"
    previous_verified = _load(radar_path, {})
    now = datetime.now(timezone.utc).isoformat()
    raw = run_cex_revival(data_dir, now)

    try:
        age = _retry(lambda: verify_age_and_identity(radar_path), attempts=3)
    except Exception as e:
        # The raw CEX scan has no verified identity yet. Restore the previous
        # verified snapshot rather than exposing raw symbol-only rows as truth.
        if previous_verified and previous_verified.get("age_gate"):
            previous_verified["fast_lane_degraded"] = {
                "at": now,
                "reason": f"AGE_IDENTITY_PROVIDER_TRANSIENT:{type(e).__name__}",
                "policy": "LAST_VERIFIED_SNAPSHOT_PRESERVED_FAIL_CLOSED",
            }
            _write(radar_path, previous_verified)
            real = build_real_alerts(data_dir)
            return {
                "status": "DEGRADED_LAST_VERIFIED_PRESERVED",
                "generated_at": now,
                "raw_cex_alerts_observed": raw.get("alerts_count", 0),
                "error": f"{type(e).__name__}: {e}"[:500],
                "real_alert_feed": real,
            }
        # No prior verified truth exists. Publish no CEX identity rather than a
        # symbol-only pseudo-result, but keep the workflow alive.
        safe = {
            "version": 10,
            "generated_at": now,
            "alerts_count": 0,
            "alerts": [],
            "age_gate": {
                "status": "DEGRADED_FAIL_CLOSED",
                "minimum_market_age_days": 180,
                "accepted": 0,
                "rejected": raw.get("alerts_count", 0),
                "unknown_or_unresolved_identity": "REJECT",
            },
            "identity_counts": {"dex_verified": 0, "pair_pending": 0, "identity_pending": 0},
            "fast_lane_degraded": {
                "at": now,
                "reason": f"AGE_IDENTITY_PROVIDER_TRANSIENT:{type(e).__name__}",
                "policy": "NO_UNVERIFIED_CEX_ALERT_EXPOSED",
            },
        }
        _write(radar_path, safe)
        real = build_real_alerts(data_dir)
        return {
            "status": "DEGRADED_FAIL_CLOSED",
            "generated_at": now,
            "raw_cex_alerts_observed": raw.get("alerts_count", 0),
            "error": f"{type(e).__name__}: {e}"[:500],
            "real_alert_feed": real,
        }

    identity = _retry(lambda: resolve_identity(radar_path), attempts=3)
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
