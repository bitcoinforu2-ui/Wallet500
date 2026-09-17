from __future__ import annotations

import importlib.util
from pathlib import Path

# Keep the proven production sender as the canonical implementation.  This
# package intentionally shadows the sibling telegram_alerts.py module so
# `python -m wallet500.telegram_alerts` can add presentation-only first-seen
# semantics without changing any validation, dedupe, retry or persistence logic.
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "telegram_alerts.py"
_SPEC = importlib.util.spec_from_file_location("wallet500._telegram_alerts_core", _LEGACY_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - installation guard
    raise ImportError(f"Cannot load canonical Telegram sender from {_LEGACY_PATH}")
_core = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_core)

# Preserve the public/testing surface of the original module.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

_original_message = _core._message
_original_pre_wave_message = _core._pre_wave_message
_original_run = _core.run

# Import after the compatibility exports exist.  telegram_first_seen imports
# wallet500.telegram_alerts for constants and formatting helpers.
from wallet500 import telegram_first_seen as _first_seen  # noqa: E402


def _delivery_message(row: dict, tier: str, sent_at: str | None = None, alert_event_id: str | None = None) -> str:
    text = _original_message(row, tier, sent_at=sent_at, alert_event_id=alert_event_id)
    return _first_seen._mark_first_seen(text, row)


def _delivery_pre_wave_message(row: dict, sent_at: str | None = None, alert_event_id: str | None = None) -> str:
    text = _original_pre_wave_message(row, sent_at=sent_at, alert_event_id=alert_event_id)
    return _first_seen._mark_first_seen(text, row)


def run() -> dict:
    """Run the canonical sender with one-time NEW coin presentation semantics.

    The package remains monkeypatch-compatible with the historical module API:
    tests/diagnostics that replace wallet500.telegram_alerts._send are mirrored
    into the canonical core only for the duration of this run.
    """
    _first_seen._seen_tokens_cache = None
    _first_seen._claimed_this_run.clear()

    previous_message = _core._message
    previous_pre_wave = _core._pre_wave_message
    previous_send = _core._send

    _core._message = _delivery_message
    _core._pre_wave_message = _delivery_pre_wave_message
    _core._send = globals().get("_send", previous_send)
    try:
        return _original_run()
    finally:
        _core._message = previous_message
        _core._pre_wave_message = previous_pre_wave
        _core._send = previous_send
