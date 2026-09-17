from __future__ import annotations

"""Production compatibility boundary for Telegram state I/O.

The legacy alert module still owns formatting and dedupe semantics. Production
installs fail-closed reads and atomic replacement before importing the guarded
BUY-only delivery wrapper. Non-production scan lanes never call this launcher.
"""

from wallet500 import telegram_alerts as alerts
from wallet500.safe_json import atomic_write_json, load_json_fail_closed


# Install safe state semantics before importing the guarded delivery wrapper.
# The wrapper and telegram_alerts perform runtime lookups through these functions.
alerts._load = load_json_fail_closed
alerts._write = atomic_write_json

from run_telegram_with_intelligence_shadow import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
