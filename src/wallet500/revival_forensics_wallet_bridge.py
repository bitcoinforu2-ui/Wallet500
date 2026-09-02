from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data")
WALLET = DATA / "revival-wallet-evidence.json"
FORENSICS_STATE = DATA / "revival-forensics-state.json"
FORENSICS_LATEST = DATA / "revival-forensics-latest.json"
FORENSICS_DASHBOARD = DATA / "revival-forensics-dashboard.json"

BRIDGE_STATUS = "RAW_VERIFIED_EXACT_PAIR_CONNECTED_SMART_MONEY_TIERS_PENDING"
BRIDGE_VERSION = "REVIVAL_FORENSICS_WALLET_BRIDGE_V1"


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_wallet(payload: dict) -> None:
    if payload.get("version") != "REVIVAL_WALLET_EVIDENCE_V1":
        raise SystemExit("REVIVAL_WALLET_BRIDGE_VERSION_INVALID")
    if payload.get("network") != "solana":
        raise SystemExit("REVIVAL_WALLET_BRIDGE_NETWORK_INVALID")
    if payload.get("production_portfolio_impact") != "NONE":
        raise SystemExit("REVIVAL_WALLET_BRIDGE_PRODUCTION_IMPACT_INVALID")
    if payload.get("automatic_buy") is not False:
        raise SystemExit("REVIVAL_WALLET_BRIDGE_AUTOMATIC_BUY_INVALID")
    truth = payload.get("truth_contract") or {}
    if truth.get("exact_pair_only") is not True:
        raise SystemExit("REVIVAL_WALLET_BRIDGE_EXACT_PAIR_INVALID")
    if truth.get("signed_token_owner_delta_only") is not True:
        raise SystemExit("REVIVAL_WALLET_BRIDGE_WALLET_IDENTITY_INVALID")
    if truth.get("unresolved_not_guessed") is not True:
        raise SystemExit("REVIVAL_WALLET_BRIDGE_UNRESOLVED_POLICY_INVALID")
    if truth.get("forward_only") is not True:
        raise SystemExit("REVIVAL_WALLET_BRIDGE_FORWARD_ONLY_INVALID")


def evidence_map(payload: dict) -> dict[str, dict]:
    out = {}
    for row in payload.get("tokens") or []:
        mint = str(row.get("token_address") or "").strip()
        if not mint:
            continue
        out[mint] = row
    return out


def sanitized_evidence(row: dict | None, event: dict) -> dict:
    if not row:
        return {
            "status": "NO_WALLET_EVIDENCE_ROW",
            "connected": False,
            "eligible_as_t0_wallet_evidence": False,
            "role": "MISSING",
            "smart_money_tiers_status": "NOT_SCORED_NO_VERIFIED_WALLET_DATA",
        }
    event_pair = str((event.get("t0") or {}).get("pair_address") or "")
    evidence_pair = str(row.get("exact_pair") or "")
    if not event_pair or evidence_pair != event_pair:
        return {
            "status": "PAIR_IDENTITY_MISMATCH_FAIL_CLOSED",
            "connected": False,
            "eligible_as_t0_wallet_evidence": False,
            "role": "REJECTED",
            "smart_money_tiers_status": "NOT_SCORED_PAIR_MISMATCH",
        }

    coverage = dict(row.get("coverage") or {})
    eligible = coverage.get("eligible_as_forensics_t0_wallet_evidence") is True
    tiers = row.get("smart_money_tiers") or {}
    top_wallets = []
    for wallet in row.get("top_wallets_raw_verified") or []:
        top_wallets.append(
            {
                "wallet": wallet.get("wallet"),
                "buys": wallet.get("buys"),
                "sells": wallet.get("sells"),
                "net_token_delta": wallet.get("net_token_delta"),
                "first_seen_at": wallet.get("first_seen_at"),
                "last_seen_at": wallet.get("last_seen_at"),
                "tier": "UNSCORED_RAW_VERIFIED",
            }
        )

    return {
        "status": row.get("status"),
        "connected": True,
        "source": "REVIVAL_WALLET_EVIDENCE_V1",
        "exact_pair": evidence_pair,
        "monitor_started_at": row.get("monitor_started_at"),
        "forensics_t0": row.get("forensics_t0"),
        "eligible_as_t0_wallet_evidence": eligible,
        "role": "T0_ELIGIBLE_RAW_VERIFIED" if eligible else "POST_T0_CONFIRMATION_ONLY",
        "coverage": coverage,
        "windows": row.get("windows") or {},
        "top_wallets_raw_verified": top_wallets,
        "smart_money_tiers_status": tiers.get("status") or "NOT_SCORED",
        "elite": 0,
        "strong": 0,
        "watch": 0,
        "truth_note": (
            "Raw wallet identities are verified by signed target-token owner delta. "
            "No wallet is called ELITE/STRONG until cross-token historical scoring exists."
        ),
    }


def bridge() -> dict:
    wallet = load(WALLET, {})
    validate_wallet(wallet)
    by_mint = evidence_map(wallet)

    state = load(FORENSICS_STATE, {})
    latest = load(FORENSICS_LATEST, {})
    dashboard = load(FORENSICS_DASHBOARD, {})
    if latest.get("mode") != "RESEARCH_ONLY_REVIVAL_FORENSICS_V2":
        raise SystemExit("REVIVAL_WALLET_BRIDGE_FORENSICS_MODE_INVALID")

    events_by_id = state.get("events") or {}
    connected = 0
    t0_eligible = 0
    confirmation_only = 0
    missing = 0

    for event in events_by_id.values():
        if not isinstance(event, dict):
            continue
        mint = str(event.get("token_address") or "")
        ev = sanitized_evidence(by_mint.get(mint), event)
        event["wallet500_evidence"] = ev
        if ev.get("connected"):
            connected += 1
            if ev.get("eligible_as_t0_wallet_evidence"):
                t0_eligible += 1
            else:
                confirmation_only += 1
        else:
            missing += 1

    state["wallet_evidence_bridge"] = {
        "version": BRIDGE_VERSION,
        "status": BRIDGE_STATUS,
        "wallet_source_generated_at": wallet.get("generated_at"),
        "connected_events": connected,
        "t0_eligible_events": t0_eligible,
        "post_t0_confirmation_only_events": confirmation_only,
        "missing_or_rejected_events": missing,
        "smart_money_tiers_connected": False,
    }
    write(FORENSICS_STATE, state)

    # State is canonical. Rebuild corresponding event payloads by event_id.
    for event in latest.get("events") or []:
        event_id = event.get("event_id")
        canonical = events_by_id.get(event_id)
        if canonical:
            event["wallet500_evidence"] = canonical.get("wallet500_evidence")

    latest["wallet500_status"] = BRIDGE_STATUS
    latest["wallet500_bridge"] = state["wallet_evidence_bridge"]
    write(FORENSICS_LATEST, latest)

    active_by_id = {
        row.get("event_id"): row
        for row in dashboard.get("active") or []
        if row.get("event_id")
    }
    for event_id, row in active_by_id.items():
        canonical = events_by_id.get(event_id)
        if canonical:
            row["wallet500_evidence"] = canonical.get("wallet500_evidence")
    dashboard["wallet500_status"] = BRIDGE_STATUS
    dashboard["wallet500_bridge"] = state["wallet_evidence_bridge"]
    write(FORENSICS_DASHBOARD, dashboard)

    return state["wallet_evidence_bridge"]


def main() -> None:
    result = bridge()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
