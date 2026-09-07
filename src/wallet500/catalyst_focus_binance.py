from __future__ import annotations

import json

from wallet500 import catalyst_focus as cf
from wallet500.binance_event_intelligence import DATA, enrich_event, format_binance_lines

_BASE_SCORE_EVENT = cf.score_event
_BASE_STARTMSG = cf.startmsg
_BASE_UPDATEMSG = cf.updatemsg
_BASE_FINALMSG = cf.finalmsg


def score_event(event: dict) -> dict:
    # Binance intelligence is context-only. It never changes Focus score, thresholds,
    # exact-pair, liquidity, risk or eligibility decisions.
    return enrich_event(_BASE_SCORE_EVENT(event), DATA)


def _inject(base_text: str, event: dict) -> str:
    extra = format_binance_lines(event)
    if not extra:
        return base_text
    lines = base_text.splitlines()
    return "\n".join(lines[:1] + extra + lines[1:])


def startmsg(event: dict) -> str:
    return _inject(_BASE_STARTMSG(event), event)


def updatemsg(event: dict, reason: str, previous: dict) -> str:
    return _inject(_BASE_UPDATEMSG(event, reason, previous), event)


def finalmsg(event: dict, reason: str) -> str:
    return _inject(_BASE_FINALMSG(event, reason), event)


def install() -> None:
    cf.score_event = score_event
    cf.startmsg = startmsg
    cf.updatemsg = updatemsg
    cf.finalmsg = finalmsg


def run() -> dict:
    install()
    return cf.run()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
