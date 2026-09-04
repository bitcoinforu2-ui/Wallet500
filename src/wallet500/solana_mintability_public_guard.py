from __future__ import annotations

import json
from pathlib import Path

from .solana_mintability_gate import DATA, _chain, _is_safe, _load, _token, _write, resolve

LIST_KEYS = ("alerts", "verified_watch", "evidence_ready", "identity_pending")


def sanitize_real_alerts(data_dir: Path = DATA) -> dict:
    path = data_dir / "real-alerts.json"
    payload = _load(path, {})
    if not isinstance(payload, dict):
        return {"status": "NO_REAL_ALERT_PAYLOAD", "removed": 0}

    rows = []
    for key in LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(x for x in value if isinstance(x, dict))
    mints = [_token(x) for x in rows if _chain(x) == "solana" and _token(x)]
    state_path = data_dir / "solana-mintability-state.json"
    state = _load(state_path, {})
    truth, next_state = resolve(mints, state)
    truth_all = next_state.get("tokens") if isinstance(next_state.get("tokens"), dict) else {}

    removed = []
    for key in LIST_KEYS:
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        kept = []
        for row in value:
            if not isinstance(row, dict) or _chain(row) != "solana":
                kept.append(row)
                continue
            token = _token(row)
            t = truth.get(token) or truth_all.get(token) or {}
            if _is_safe(t):
                kept.append({
                    **row,
                    "mintability_verified": True,
                    "mintable": False,
                    "mint_authority": None,
                    "mintability_status": "NON_MINTABLE_VERIFIED",
                })
            else:
                removed.append({
                    "surface": key,
                    "symbol": row.get("symbol"),
                    "token_address": token,
                    "status": t.get("status") or "UNVERIFIED_BLOCKED",
                    "mintable": t.get("mintable"),
                    "mint_authority": t.get("mint_authority"),
                    "reason": t.get("reason") or "SOLANA_MINTABILITY_NOT_VERIFIED_SAFE",
                })
        payload[key] = kept

    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    counts["real_alerts"] = len(payload.get("alerts") or [])
    counts["verified_watch_not_real"] = len(payload.get("verified_watch") or [])
    counts["evidence_ready_research"] = len(payload.get("evidence_ready") or [])
    counts["identity_pending_not_actionable"] = len(payload.get("identity_pending") or [])
    counts["mintability_rejected_not_visible"] = len(removed)
    payload["counts"] = counts
    truth_contract = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth_contract["solana_mint_authority_must_be_revoked_null"] = True
    truth_contract["solana_mintable_tokens_allowed"] = False
    truth_contract["solana_unknown_mintability_allowed"] = False
    payload["truth_contract"] = truth_contract
    payload["mintability_public_guard"] = {
        "version": 1,
        "status": "ENFORCED_FAIL_CLOSED",
        "rule": "SOLANA_MINT_AUTHORITY_MUST_BE_REVOKED_NULL",
        "removed_not_visible": len(removed),
        "rejections": removed[:100],
    }
    _write(path, payload)
    _write(state_path, next_state)
    return payload["mintability_public_guard"]


def main() -> None:
    print(json.dumps(sanitize_real_alerts(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
