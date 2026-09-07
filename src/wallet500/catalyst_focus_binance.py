from __future__ import annotations

import json

from wallet500 import catalyst_focus as cf
from wallet500.binance_event_intelligence import DATA, enrich_event, format_binance_lines

_BASE_SCORE_EVENT = cf.score_event
_BASE_STARTMSG = cf.startmsg
_BASE_UPDATEMSG = cf.updatemsg
_BASE_FINALMSG = cf.finalmsg

NEGATIVE_MACHINE_STATES = {
    "delisted", "disabled", "offline", "suspended", "halted", "closed",
    "cancelled", "canceled", "removed", "terminated", "deactivated",
}


def _negative_machine_state(event: dict) -> str | None:
    machine = event.get("machine_state") if isinstance(event.get("machine_state"), dict) else {}
    state = str(machine.get("state") or "").strip().lower()
    if state in NEGATIVE_MACHINE_STATES:
        return state

    # Fail closed on explicit negative state text from official machine-state feeds.
    # This protects against producer/classifier mistakes such as a delisted product
    # being mislabeled SPOT_LISTING_EXPECTED.
    if str(event.get("source_kind") or "").upper() == "OFFICIAL_MACHINE_STATE":
        text = " ".join(
            str(x or "")
            for x in (event.get("excerpt"), event.get("title"), event.get("description"))
        ).lower()
        for value in NEGATIVE_MACHINE_STATES:
            if f"state={value}" in text or f" state {value}" in text:
                return value
    return None


def score_event(event: dict) -> dict:
    # Binance intelligence remains context-only. The safety veto below is generic
    # for every exchange event passing through the production Focus wrapper.
    scored = _BASE_SCORE_EVENT(event)
    negative_state = _negative_machine_state(event)
    if negative_state:
        blockers = list(scored.get("blockers") or [])
        if "NEGATIVE_EXCHANGE_MACHINE_STATE" not in blockers:
            blockers.append("NEGATIVE_EXCHANGE_MACHINE_STATE")
        scored.update(
            focus_eligible=False,
            decision="WATCH_SILENT_NEGATIVE_MACHINE_STATE",
            blockers=blockers,
            machine_state_verdict="NEGATIVE_FAIL_CLOSED",
            negative_machine_state=negative_state,
        )
    else:
        scored["machine_state_verdict"] = "NO_NEGATIVE_STATE_DETECTED"
    return enrich_event(scored, DATA)


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
