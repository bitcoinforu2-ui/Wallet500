from __future__ import annotations

import json
import os
from pathlib import Path

from wallet500 import telegram_alerts as core

NEW_MARKER = "🆕🆕🆕 NEW COIN — זוהה לראשונה ע״י המנוע 🆕🆕🆕"
LEGACY_ALWAYS_NEW_MARKER = "🆕 NEW REAL ALERT"

_seen_tokens_cache: set[str] | None = None
_claimed_this_run: set[str] = set()


def _canonical_chain(value: object) -> str:
    chain = str(value or "unknown").strip().lower()
    if chain == "bnb":
        return "bsc"
    if chain == "eth":
        return "ethereum"
    return chain


def _token_identity(chain: object, token: object) -> str:
    chain_name = _canonical_chain(chain)
    token_text = str(token or "").strip()
    if chain_name in core.EVM_CHAINS:
        token_text = token_text.lower()
    return f"{chain_name}:{token_text}"


def _row_identity(row: dict) -> str:
    return _token_identity(
        row.get("chain"),
        row.get("token") or row.get("mint") or row.get("token_address"),
    )


def _state_path() -> Path:
    output_dir = Path(os.environ.get("WALLET500_OUTPUT_DIR", "data"))
    return output_dir / "telegram-alert-state.json"


def _identity_from_sent_key(key: object) -> str | None:
    parts = str(key or "").split(":")
    if not parts:
        return None
    if parts[0] == "PRE_WAVE":
        if len(parts) < 4:
            return None
        chain, token = parts[1], parts[2]
    else:
        if len(parts) < 3:
            return None
        chain, token = parts[0], parts[1]
    identity = _token_identity(chain, token)
    return identity if not identity.endswith(":") else None


def _load_historically_seen_tokens() -> set[str]:
    path = _state_path()
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    sent = payload.get("sent") if isinstance(payload, dict) else None
    if not isinstance(sent, dict):
        return set()
    seen: set[str] = set()
    for key in sent:
        identity = _identity_from_sent_key(key)
        if identity:
            seen.add(identity)
    return seen


def _seen_tokens() -> set[str]:
    global _seen_tokens_cache
    if _seen_tokens_cache is None:
        _seen_tokens_cache = _load_historically_seen_tokens()
    return _seen_tokens_cache


def _strip_legacy_new_marker(text: str) -> str:
    return text.replace(f"\n{LEGACY_ALWAYS_NEW_MARKER}", "").replace(LEGACY_ALWAYS_NEW_MARKER, "")


def _mark_first_seen(text: str, row: dict) -> str:
    """Show NEW once per token across PRE_WAVE/REAL_ALERT and future reruns.

    Existing Telegram delivery state is the durable source of truth. Historical
    tokens are backfilled automatically from prior sent keys, while a token claimed
    in the current process is protected from receiving a second NEW marker if two
    alert stages are emitted in the same run.
    """
    identity = _row_identity(row)
    cleaned = _strip_legacy_new_marker(text)
    if not identity or identity.endswith(":"):
        return cleaned
    if identity in _seen_tokens() or identity in _claimed_this_run:
        return cleaned

    _claimed_this_run.add(identity)
    lines = cleaned.splitlines()
    if not lines:
        return NEW_MARKER
    return "\n".join([lines[0], NEW_MARKER, *lines[1:]])


_original_message = core._message
_original_pre_wave_message = core._pre_wave_message


def _message(row: dict, tier: str, sent_at: str | None = None, alert_event_id: str | None = None) -> str:
    text = _original_message(row, tier, sent_at=sent_at, alert_event_id=alert_event_id)
    return _mark_first_seen(text, row)


def _pre_wave_message(row: dict, sent_at: str | None = None, alert_event_id: str | None = None) -> str:
    text = _original_pre_wave_message(row, sent_at=sent_at, alert_event_id=alert_event_id)
    return _mark_first_seen(text, row)


def run():
    # Patch only presentation. All canonical validation, dedupe, delivery and
    # persistence remain owned by wallet500.telegram_alerts.
    core._message = _message
    core._pre_wave_message = _pre_wave_message
    return core.run()


if __name__ == "__main__":
    run()
