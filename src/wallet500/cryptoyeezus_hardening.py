from __future__ import annotations

import os
import re
import sys
from urllib.parse import quote

from . import cryptoyeezus_live_watch as live

_BASE_REPEAT_IS_MATERIAL = live.repeat_is_material
_BASE_PRIMARY_SYMBOL = live._primary_symbol

# CryptoYeezus often posts conviction/performance updates rather than a fresh
# "buy" sentence. These phrases are meaningful repeat promotions and should
# reach the priority lane when the token identity is already known.
EXTRA_MATERIAL_PHRASES = (
    "bottom on my",
    "bottomed on my",
    "still holding",
    "holding the moon bag",
    "moon bag",
    "reprice",
    "pair runner",
    "runner yet",
)
MULTIPLE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*x\b", re.I)

# When a post contains several cashtags (for example RUFUS + AMZN + AI), use
# explicit ownership/conviction language to identify the actual crypto call.
PRIMARY_CONVICTION_RE = re.compile(
    r"(?:bottom(?:ed|ing)?(?:\s+on)?(?:\s+(?:my|the))?|"
    r"holding(?:\s+(?:my|the))?|still\s+holding|moon\s+bag(?:\s+on)?|"
    r"re-?entry(?:\s+(?:on|in))?)"
    r"[^$\n]{0,55}\$([A-Za-z][A-Za-z0-9_]{1,14})\b",
    re.I,
)


def extended_repeat_is_material(text: str, refs: dict | None = None) -> bool:
    if _BASE_REPEAT_IS_MATERIAL(text, refs):
        return True
    low = str(text or "").lower()
    return any(phrase in low for phrase in EXTRA_MATERIAL_PHRASES) or bool(MULTIPLE_RE.search(low))


def extended_primary_symbol(text: str, refs: dict, market: dict | None) -> str | None:
    symbol = _BASE_PRIMARY_SYMBOL(text, refs, market)
    if symbol:
        return symbol
    match = PRIMARY_CONVICTION_RE.search(str(text or ""))
    if match:
        return live._norm_symbol(match.group(1))
    return None


def install() -> None:
    """Install the hardened classifier into the live module for this process."""
    live.repeat_is_material = extended_repeat_is_material
    live._primary_symbol = extended_primary_symbol


def _fallback_count() -> int:
    try:
        value = int(os.getenv("YEEZUS_X_FALLBACK_COUNT", "50"))
    except ValueError:
        value = 50
    return max(20, min(100, value))


def run_mode(mode: str) -> None:
    install()
    normalized = str(mode or "").strip().lower()

    if normalized == "live":
        live.main()
        return

    if normalized == "fallback":
        # Direct X currently may be degraded. Give the public redundancy a
        # deeper rolling window so a busy account cannot outrun a 20-post poll.
        from . import cryptoyeezus_x_fallback as fallback

        fallback.FXTWITTER_URL = (
            "https://api.fxtwitter.com/2/profile/"
            f"{quote(live.X_HANDLE)}/statuses?count={_fallback_count()}"
        )
        fallback.main()
        return

    if normalized == "priority":
        # Import after install(): priority_alerts imports repeat_is_material by
        # value, so it must see the hardened function at import time.
        from . import cryptoyeezus_priority_alerts as priority

        priority.main()
        return

    raise SystemExit(f"unknown mode: {mode!r}; expected live, fallback, or priority")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "priority"
    run_mode(mode)


if __name__ == "__main__":
    main()
