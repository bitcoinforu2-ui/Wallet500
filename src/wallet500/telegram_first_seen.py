from __future__ import annotations

import json
import os
from pathlib import Path

from wallet500 import telegram_alerts as core

NEW_TO_ENGINE_MARKER = "🆕🆕🆕 NEW TO ENGINE — זוהה לראשונה ע״י המנוע 🆕🆕🆕"
NEWLY_LAUNCHED_MARKER = "🚀 NEWLY LAUNCHED — מטבע חדש בשוק (≤7 ימים)"
EXISTING_MARKET_MARKER = "♻️ EXISTING MARKET — חדש למנוע, לא השקה חדשה"
NEW_LAUNCH_MAX_AGE_DAYS = 7.0
# Backward-compatible export for tests/importers that used the old constant.
NEW_MARKER = NEW_TO_ENGINE_MARKER
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


def _verified_market_age_days(row: dict) -> float | None:
    """Return verified token market age; never infer token launch age from pair age."""
    if row.get("market_age_verified") is not True:
        return None
    raw = row.get("market_age_days")
    if raw is None:
        raw = row.get("market_age_min_days")
    try:
        age = float(raw)
    except (TypeError, ValueError):
        return None
    return age if age >= 0 else None


def _first_seen_labels(row: dict) -> list[str]:
    labels = [NEW_TO_ENGINE_MARKER]
    age = _verified_market_age_days(row)
    if age is None:
        return labels
    if age <= NEW_LAUNCH_MAX_AGE_DAYS:
        labels.append(f"{NEWLY_LAUNCHED_MARKER} — verified age {age:g}d")
    else:
        labels.append(f"{EXISTING_MARKET_MARKER} — verified age {age:g}d")
    return labels


def _mark_first_seen(text: str, row: dict) -> str:
    """Show first-engine-seen once and separately classify actual market age.

    NEW TO ENGINE means this chain+contract has never been delivered by Wallet500.
    NEWLY LAUNCHED is a separate, stricter label and is emitted only when verified
    token market age is <=7 days. Pair age is deliberately ignored because an old
    token can open a new liquidity pool and must not be mislabelled as a new launch.
    """
    identity = _row_identity(row)
    cleaned = _strip_legacy_new_marker(text)
    if not identity or identity.endswith(":"):
        return cleaned
    if identity in _seen_tokens() or identity in _claimed_this_run:
        return cleaned

    _claimed_this_run.add(identity)
    labels = _first_seen_labels(row)
    lines = cleaned.splitlines()
    if not lines:
        return "\n".join(labels)
    return "\n".join([lines[0], *labels, *lines[1:]])


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
