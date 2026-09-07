from __future__ import annotations

import json

from wallet500 import catalyst_wire as cw
from wallet500.binance_event_intelligence import DATA, enrich_event, format_binance_lines

_BASE_DECORATE = cw._decorate
_BASE_MESSAGE = cw._message


def _decorate(event: dict) -> dict:
    return enrich_event(_BASE_DECORATE(event), DATA)


def _message(event: dict) -> str:
    base = _BASE_MESSAGE(event).splitlines()
    extra = format_binance_lines(event)
    if not extra:
        return "\n".join(base)
    # Put Binance priority directly under the alert title so it cannot be missed on mobile.
    return "\n".join(base[:2] + extra + base[2:])


def install() -> None:
    cw._decorate = _decorate
    cw._message = _message


def run() -> dict:
    install()
    return cw.run()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
