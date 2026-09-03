from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
REVIVAL_LATEST = DATA / "revival-holder-latest.json"
REVIVAL_STATE = DATA / "revival-holder-state.json"
WAKING_LATEST = DATA / "waking-confirmation-latest.json"
WAKING_STATE = DATA / "waking-confirmation-state.json"
STATUS = DATA / "holder-truth-status.json"

UNSAFE_SOURCES = {
    "RUGCHECK_EXACT_MINT_PUBLIC_REPORT",
}

GROWTH_FIELDS = (
    "holder_growth_count",
    "holder_growth_pct",
    "latest_scan_change_pct",
    "holder_growth_24h_count",
    "holder_growth_24h_pct",
    "holder_24h_base_count",
    "holder_24h_base_observed_at",
    "holder_24h_window_hours",
    "holder_growth_7d_count",
    "holder_growth_7d_pct",
    "holder_7d_base_count",
    "holder_7d_base_observed_at",
    "holder_7d_window_hours",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def quarantine_revival_row(row: dict) -> bool:
    source = str(row.get("source") or "")
    if source not in UNSAFE_SOURCES:
        return False
    raw_count = row.get("holder_count")
    if raw_count is not None:
        row["raw_provider_holder_count"] = raw_count
    row["holder_count"] = None
    row["holder_truth_status"] = "QUARANTINED_PROVIDER_SEMANTICS"
    row["growth_eligible"] = False
    row["holder_growth_24h_ready"] = False
    row["holder_growth_7d_ready"] = False
    for field in GROWTH_FIELDS:
        row[field] = None
    limitations = list(row.get("source_limitations") or [])
    msg = "provider count is not accepted as unique-owner holder truth; growth disabled until a holder-address source with stable semantics is used"
    if msg not in limitations:
        limitations.append(msg)
    row["source_limitations"] = limitations
    return True


def quarantine_waking_holder(holder: dict) -> bool:
    if str(holder.get("source") or "") not in UNSAFE_SOURCES:
        return False
    metrics = holder.setdefault("metrics", {})
    raw_count = metrics.get("holder_count")
    if raw_count is not None:
        metrics["raw_provider_holder_count"] = raw_count
    metrics["holder_count"] = None
    metrics["previous_holder_count"] = None
    metrics["holder_change_pct"] = None
    holder["verified"] = False
    holder["growth_eligible"] = False
    holder["score"] = 0.0
    holder["truth_status"] = "QUARANTINED_PROVIDER_SEMANTICS"
    signals = list(holder.get("signals") or [])
    if "HOLDER_GROWTH_QUARANTINED_UNSAFE_PROVIDER_SEMANTICS" not in signals:
        signals.append("HOLDER_GROWTH_QUARANTINED_UNSAFE_PROVIDER_SEMANTICS")
    holder["signals"] = signals
    return True


def guard_payloads(revival_latest: dict, revival_state: dict, waking_latest: dict, waking_state: dict) -> dict:
    quarantined_revival = 0
    quarantined_waking = 0

    for row in revival_latest.get("coins") or []:
        if isinstance(row, dict) and quarantine_revival_row(row):
            quarantined_revival += 1
    revival_latest["holder_truth_policy"] = "UNIQUE_OWNER_OR_STABLE_HOLDER_ADDRESS_SOURCE_REQUIRED"
    revival_latest["growth_fail_closed"] = True
    revival_latest["provider"] = "MIXED_RAW_EVIDENCE_WITH_TRUTH_GUARD"

    for row in (revival_state.get("coins") or {}).values():
        if isinstance(row, dict):
            quarantine_revival_row(row)
    revival_state["holder_truth_policy"] = "UNIQUE_OWNER_OR_STABLE_HOLDER_ADDRESS_SOURCE_REQUIRED"
    revival_state["growth_fail_closed"] = True

    for target in waking_latest.get("targets") or []:
        holder = ((target.get("channels") or {}).get("holders") if isinstance(target, dict) else None)
        if isinstance(holder, dict) and quarantine_waking_holder(holder):
            quarantined_waking += 1
    waking_latest["holder_growth_truth_guard"] = "FAIL_CLOSED_UNSAFE_PROVIDER_SEMANTICS"

    tokens = waking_state.get("tokens") or {}
    for row in tokens.values() if isinstance(tokens, dict) else []:
        if not isinstance(row, dict):
            continue
        holder = ((row.get("channels") or {}).get("holders"))
        if isinstance(holder, dict):
            quarantine_waking_holder(holder)
        # Old RugCheck baselines must not silently seed a future trusted series.
        if row.get("rugcheck_holder_count") is not None:
            row["rugcheck_holder_count_raw_quarantined"] = row.get("rugcheck_holder_count")
            row["rugcheck_holder_count"] = None

    return {
        "quarantined_revival_rows": quarantined_revival,
        "quarantined_waking_rows": quarantined_waking,
    }


def main() -> None:
    revival_latest = load(REVIVAL_LATEST, {})
    revival_state = load(REVIVAL_STATE, {})
    waking_latest = load(WAKING_LATEST, {})
    waking_state = load(WAKING_STATE, {})
    counts = guard_payloads(revival_latest, revival_state, waking_latest, waking_state)
    if revival_latest:
        write(REVIVAL_LATEST, revival_latest)
    if revival_state:
        write(REVIVAL_STATE, revival_state)
    if waking_latest:
        write(WAKING_LATEST, waking_latest)
    if waking_state:
        write(WAKING_STATE, waking_state)
    status = {
        "version": 1,
        "generated_at": now_iso(),
        "mode": "HOLDER_TRUTH_FAIL_CLOSED_V1",
        "policy": "Holder growth may affect research/scoring only when the count comes from a stable holder-address/unique-owner source. RugCheck exact-mint count is retained only as raw evidence, never as growth truth.",
        "unsafe_sources": sorted(UNSAFE_SOURCES),
        "quarantined": counts,
        "production_safety": "NO_UNVERIFIED_HOLDER_GROWTH_PROMOTION",
    }
    write(STATUS, status)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
