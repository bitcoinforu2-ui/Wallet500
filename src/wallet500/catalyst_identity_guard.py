from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA = Path("data")
REGISTRY = DATA / "cex-identity-registry.json"
WIRE = DATA / "catalyst-wire-live.json"
LEDGER = DATA / "catalyst-wire-ledger.json"
FOCUS_STATE = DATA / "catalyst-focus-state.json"

EVM_CHAINS = {"ethereum", "bsc", "arbitrum", "base", "polygon", "optimism", "avalanche"}
CHAIN_ALIASES = {
    "eth": "ethereum",
    "ethereum-mainnet": "ethereum",
    "bnb": "bsc",
    "bnb-chain": "bsc",
    "binance-smart-chain": "bsc",
    "arbitrum-one": "arbitrum",
    "sol": "solana",
}
EXCHANGE_OWNERS = {
    "binance", "coinbase", "kraken", "bybit", "okx", "kucoin", "bitget",
    "gate", "mexc", "bithumb", "coinex", "htx", "lbank", "bingx",
    "bitmart", "weex", "crypto.com", "upbit",
}
BLOCKER = "SYMBOL_TO_CONTRACT_NOT_CANONICALLY_VERIFIED"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm_symbol(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum())


def _norm_chain(value: object) -> str:
    chain = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(chain, chain)


def _norm_token(value: object, chain: object) -> str:
    token = str(value or "").strip()
    return token.lower() if _norm_chain(chain) in EVM_CHAINS or token.startswith("0x") else token


def _asset_key(chain: object, token: object) -> str | None:
    c = _norm_chain(chain)
    t = _norm_token(token, c)
    return f"{c}:{t}" if c and t else None


def _registry_symbols(payload: Any) -> dict[str, dict]:
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("symbols")
    if not isinstance(rows, dict):
        return {}
    return {_norm_symbol(k): v for k, v in rows.items() if isinstance(v, dict)}


def _is_exchange_event(event: dict) -> bool:
    owner = str(event.get("source_owner") or "").strip().lower()
    source_id = str(event.get("source_id") or "").upper()
    return owner in EXCHANGE_OWNERS or any(
        source_id.startswith(prefix)
        for prefix in (
            "BINANCE_", "COINBASE_", "KRAKEN_", "BYBIT_", "OKX_", "KUCOIN_",
            "BITGET_", "GATE_", "MEXC_", "BITHUMB_", "COINEX_", "HTX_",
            "LBANK_", "BINGX_", "BITMART_", "WEEX_", "CRYPTOCOM_", "UPBIT_",
        )
    )


def _registry_match(event: dict, symbols: dict[str, dict]) -> tuple[bool, str]:
    if not _is_exchange_event(event):
        return True, "NOT_EXCHANGE_SYMBOL_LINK_SCOPE"
    symbol = _norm_symbol(event.get("symbol"))
    chain = _norm_chain(event.get("chain"))
    token = _norm_token(event.get("contract") or event.get("token") or event.get("mint"), chain)
    if not symbol or not chain or not token:
        return False, "MISSING_SYMBOL_CHAIN_OR_CONTRACT"
    row = symbols.get(symbol)
    if not isinstance(row, dict):
        return False, "SYMBOL_NOT_IN_EXACT_CEX_IDENTITY_REGISTRY"
    expected_chain = _norm_chain(row.get("chain") or row.get("network"))
    expected_token = _norm_token(row.get("token_address") or row.get("token") or row.get("contract") or row.get("mint"), expected_chain)
    if not expected_chain or not expected_token:
        return False, "REGISTRY_ENTRY_MISSING_EXACT_CHAIN_CONTRACT"
    if chain != expected_chain or token != expected_token:
        return False, "REGISTRY_CHAIN_CONTRACT_MISMATCH"
    return True, "EXACT_CEX_REGISTRY_MATCH"


def sanitize_event(event: dict, symbols: dict[str, dict]) -> tuple[dict, bool, str]:
    out = dict(event)
    ok, reason = _registry_match(out, symbols)
    if not _is_exchange_event(out):
        out.setdefault("symbol_contract_link_verified", None)
        out.setdefault("identity_guard_status", reason)
        return out, True, reason
    out["symbol_contract_link_verified"] = bool(ok)
    out["symbol_contract_link_source"] = "cex-identity-registry.json"
    out["identity_guard_fail_closed"] = True
    out["identity_guard_status"] = "PASS" if ok else "BLOCKED"
    out["identity_guard_reason"] = reason
    if not ok:
        out["identity_guard_blocker"] = BLOCKER
        out["preliminary_filter_pass"] = False
        out["alert_eligible"] = False
        out["focus_eligible"] = False
    elif out.get("identity_guard_blocker") == BLOCKER:
        out.pop("identity_guard_blocker", None)
    return out, ok, reason


def _event_from_focus_record(rec: dict) -> dict:
    if not isinstance(rec, dict):
        return {}
    for key in ("event", "last_snapshot", "last_alert_snapshot"):
        value = rec.get(key)
        if isinstance(value, dict) and value:
            return value
    return {}


def sanitize_payloads(
    wire: Any,
    ledger: Any,
    focus_state: Any,
    registry: Any,
) -> tuple[dict, dict, dict, dict]:
    symbols = _registry_symbols(registry)
    out_wire = dict(wire) if isinstance(wire, dict) else {}
    out_ledger = dict(ledger) if isinstance(ledger, dict) else {"events": {}}
    out_focus = dict(focus_state) if isinstance(focus_state, dict) else {}

    blocked_event_ids: set[str] = set()
    blocked_asset_keys: set[str] = set()
    blocked_reasons: dict[str, int] = {}
    checked = 0
    passed = 0

    wire_events = []
    for raw in out_wire.get("events") or []:
        if not isinstance(raw, dict):
            continue
        event, ok, reason = sanitize_event(raw, symbols)
        checked += int(_is_exchange_event(event))
        passed += int(_is_exchange_event(event) and ok)
        if _is_exchange_event(event) and not ok:
            eid = str(event.get("event_id") or "")
            if eid:
                blocked_event_ids.add(eid)
            key = _asset_key(event.get("chain"), event.get("contract") or event.get("token") or event.get("mint"))
            if key:
                blocked_asset_keys.add(key)
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
        wire_events.append(event)
    out_wire["events"] = wire_events

    records = out_ledger.get("events") if isinstance(out_ledger.get("events"), dict) else {}
    sanitized_records: dict[str, dict] = {}
    for event_id, raw_rec in records.items():
        rec = dict(raw_rec) if isinstance(raw_rec, dict) else {}
        raw_event = rec.get("event")
        if isinstance(raw_event, dict):
            event, ok, reason = sanitize_event(raw_event, symbols)
            rec["event"] = event
            if _is_exchange_event(event) and not ok:
                blocked_event_ids.add(str(event_id))
                key = _asset_key(event.get("chain"), event.get("contract") or event.get("token") or event.get("mint"))
                if key:
                    blocked_asset_keys.add(key)
                blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
        sanitized_records[str(event_id)] = rec
    out_ledger["events"] = sanitized_records

    focus_removed = 0
    pending_removed = 0
    focus = out_focus.get("focus") if isinstance(out_focus.get("focus"), dict) else {}
    pending = out_focus.get("pending") if isinstance(out_focus.get("pending"), dict) else {}
    safe_focus = {}
    for key, rec in focus.items():
        event = _event_from_focus_record(rec)
        asset = _asset_key(event.get("chain"), event.get("contract") or event.get("token") or event.get("mint"))
        eid = str(event.get("event_id") or "")
        if eid in blocked_event_ids or (asset and asset in blocked_asset_keys):
            focus_removed += 1
            continue
        safe_focus[key] = rec
    safe_pending = {}
    for key, rec in pending.items():
        event = _event_from_focus_record(rec)
        asset = _asset_key(event.get("chain"), event.get("contract") or event.get("token") or event.get("mint"))
        eid = str(event.get("event_id") or key or "")
        if eid in blocked_event_ids or (asset and asset in blocked_asset_keys):
            pending_removed += 1
            continue
        safe_pending[key] = rec
    if focus or "focus" in out_focus:
        out_focus["focus"] = safe_focus
    if pending or "pending" in out_focus:
        out_focus["pending"] = safe_pending

    guard = {
        "fail_closed": True,
        "policy": "CEX symbol-only events never inherit a DEX contract by ticker alone; exact symbol+chain+contract must match cex-identity-registry.json before Focus/Telegram eligibility.",
        "exchange_events_checked": checked,
        "exchange_events_exact_registry_pass": passed,
        "blocked_event_count": len(blocked_event_ids),
        "blocked_asset_count": len(blocked_asset_keys),
        "blocked_event_ids": sorted(blocked_event_ids),
        "blocked_asset_keys": sorted(blocked_asset_keys),
        "blocked_reasons": blocked_reasons,
        "focus_records_removed": focus_removed,
        "pending_records_removed": pending_removed,
    }
    out_wire["identity_link_guard"] = guard
    out_ledger["identity_link_guard"] = guard
    out_focus["identity_link_guard"] = guard
    return out_wire, out_ledger, out_focus, guard


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    wire_path = data / WIRE.name
    ledger_path = data / LEDGER.name
    focus_path = data / FOCUS_STATE.name
    registry_path = data / REGISTRY.name
    wire = _load(wire_path, {})
    ledger = _load(ledger_path, {"events": {}})
    focus = _load(focus_path, {})
    registry = _load(registry_path, {})
    out_wire, out_ledger, out_focus, guard = sanitize_payloads(wire, ledger, focus, registry)
    if wire_path.exists() or out_wire:
        _write(wire_path, out_wire)
    if ledger_path.exists() or out_ledger:
        _write(ledger_path, out_ledger)
    if focus_path.exists() and focus_path.stat().st_size:
        _write(focus_path, out_focus)
    print(json.dumps(guard, ensure_ascii=False, separators=(",", ":")))
    return guard


def main() -> None:
    run()


if __name__ == "__main__":
    main()
