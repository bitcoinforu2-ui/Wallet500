from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
STATE_PATH = Path(os.getenv("YEEZUS_STATE_PATH", str(DATA_DIR / "cryptoyeezus-live-state.json")))
CALLS_PATH = Path(os.getenv("YEEZUS_CALLS_PATH", str(DATA_DIR / "cryptoyeezus-calls.json")))
LATEST_PATH = Path(os.getenv("YEEZUS_LATEST_PATH", str(DATA_DIR / "cryptoyeezus-live-latest.json")))
PRIORITY_STATE_PATH = Path(os.getenv("YEEZUS_PRIORITY_STATE_PATH", str(DATA_DIR / "cryptoyeezus-priority-state.json")))
CORRECTIONS_PATH = Path(os.getenv("YEEZUS_IDENTITY_CORRECTIONS_PATH", str(DATA_DIR / "cryptoyeezus-identity-corrections.json")))

# Canonical infrastructure/native mints must never become a caller token identity
# merely because their base58 address appeared somewhere in social post text.
# This list is deliberately tiny and truth-oriented, not a token blacklist.
RESERVED_IDENTITIES = {
    "so11111111111111111111111111111111111111112": {
        "chain": "solana",
        "canonical_symbols": {"SOL", "WSOL"},
        "reason": "SOLANA_WRAPPED_SOL_NATIVE_MINT",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _symbol(value: object) -> str:
    return str(value or "").strip().upper().lstrip("$")


def _candidate_address(event: dict) -> str:
    market = event.get("market_snapshot") or {}
    return str(market.get("token_address") or event.get("explicit_contract") or "").strip().lower()


def _invalid_reserved_identity(address: str, symbol: str) -> dict | None:
    rule = RESERVED_IDENTITIES.get(address.lower())
    if not rule:
        return None
    return rule if _symbol(symbol) not in rule["canonical_symbols"] else None


def _correction_key(source: str, event_id: str, address: str) -> str:
    return f"{source}:{event_id}:{address}".lower()


def run() -> dict:
    now = _now_iso()
    live = _load(STATE_PATH, {"tokens": {}})
    calls = _load(CALLS_PATH, {"events": []})
    latest = _load(LATEST_PATH, {"latest_events": []})
    priority = _load(PRIORITY_STATE_PATH, {"sent_event_ids": [], "token_alerts": {}})
    corrections = _load(CORRECTIONS_PATH, {
        "version": 1,
        "mode": "FORWARD_ONLY_IDENTITY_CORRECTIONS",
        "corrections": [],
    })

    existing = {
        str(row.get("correction_key") or "")
        for row in corrections.get("corrections") or []
        if isinstance(row, dict)
    }
    new_corrections: list[dict] = []

    def quarantine_event(event: dict, scope: str) -> None:
        if not isinstance(event, dict):
            return
        address = _candidate_address(event)
        symbol = _symbol(event.get("symbol") or (event.get("market_snapshot") or {}).get("symbol"))
        rule = _invalid_reserved_identity(address, symbol)
        if not rule:
            return
        key = _correction_key(scope, str(event.get("event_id") or event.get("source_post_id") or "unknown"), address)
        if key not in existing:
            existing.add(key)
            new_corrections.append({
                "correction_key": key,
                "corrected_at": now,
                "event_id": event.get("event_id"),
                "source": event.get("source"),
                "source_post_id": event.get("source_post_id"),
                "post_url": event.get("url"),
                "symbol": symbol or None,
                "quarantined_contract_candidate": address,
                "reason": rule["reason"],
                "action": "DOWNGRADE_TO_TICKER_ONLY_PRESERVE_RAW_EVENT",
            })
        event["quarantined_contract_candidate"] = address
        event["identity_status"] = "QUARANTINED_FALSE_EXACT_IDENTITY"
        event["explicit_contract"] = None
        market = event.get("market_snapshot") or {}
        if str(market.get("token_address") or "").lower() == address:
            event["market_snapshot"] = None
        event["pair_identity_locked"] = False
        flags = list(event.get("risk_flags") or [])
        for flag in ("FALSE_EXACT_IDENTITY_QUARANTINED", rule["reason"], "TICKER_ONLY_IDENTITY_UNRESOLVED"):
            if flag not in flags:
                flags.append(flag)
        event["risk_flags"] = flags

    for event in calls.get("events") or []:
        quarantine_event(event, "calls")
    for event in latest.get("latest_events") or []:
        quarantine_event(event, "latest")

    tokens = live.setdefault("tokens", {})
    for key in list(tokens):
        if not str(key).startswith("ca:"):
            continue
        address = str(key)[3:].lower()
        row = tokens.get(key)
        if not isinstance(row, dict):
            continue
        symbol = _symbol(row.get("symbol"))
        rule = _invalid_reserved_identity(address, symbol)
        if not rule:
            continue
        target = f"symbol:{symbol}" if symbol else None
        row = dict(row)
        row["quarantined_contract_candidate"] = address
        row["token_address"] = None
        row["first_market_snapshot"] = None
        row["identity_status"] = "TICKER_ONLY_IDENTITY_UNRESOLVED"
        row["identity_correction"] = {"corrected_at": now, "reason": rule["reason"]}
        if target:
            existing_row = tokens.get(target)
            if isinstance(existing_row, dict):
                # Preserve the earliest immutable first-seen record while adding
                # the correction evidence from the polluted CA-keyed record.
                existing_row.setdefault("identity_corrections", []).append(row["identity_correction"])
                existing_row.setdefault("quarantined_contract_candidates", []).append(address)
            else:
                tokens[target] = row
        del tokens[key]

    token_alerts = priority.setdefault("token_alerts", {})
    quarantined_alerts = priority.setdefault("quarantined_token_alerts", {})
    for key in list(token_alerts):
        if not str(key).startswith("ca:"):
            continue
        address = str(key)[3:].lower()
        rule = RESERVED_IDENTITIES.get(address)
        if not rule:
            continue
        alert = token_alerts[key]
        event_id = str((alert or {}).get("last_event_id") or "")
        # Only quarantine when the persisted canonical event was itself repaired.
        repaired = any(
            isinstance(e, dict)
            and str(e.get("event_id") or "") == event_id
            and e.get("identity_status") == "QUARANTINED_FALSE_EXACT_IDENTITY"
            for e in calls.get("events") or []
        )
        if not repaired:
            continue
        quarantined_alerts[key] = {
            **(alert or {}),
            "quarantined_at": now,
            "reason": rule["reason"],
            "audit_note": "Historical delivery retained; exact identity revoked and must not be inherited.",
        }
        del token_alerts[key]

    corrections.setdefault("corrections", []).extend(new_corrections)
    corrections["updated_at"] = now
    corrections["correction_count"] = len(corrections.get("corrections") or [])
    corrections["truth_contract"] = {
        "history_retained": True,
        "false_exact_identity_never_inherited": True,
        "correction_does_not_create_buy_signal": True,
        "automatic_buy": False,
    }

    _write(STATE_PATH, live)
    _write(CALLS_PATH, calls)
    _write(LATEST_PATH, latest)
    _write(PRIORITY_STATE_PATH, priority)
    _write(CORRECTIONS_PATH, corrections)
    return {
        "status": "OK",
        "new_corrections": len(new_corrections),
        "correction_count": corrections["correction_count"],
        "automatic_buy": False,
    }


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
