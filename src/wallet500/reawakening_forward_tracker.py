"""Dedicated forward exact-pair measurements for Reawakening V2.

This lane is research-only. It never promotes a rejected candidate or changes a
production gate. Its only job is to keep measuring the immutable rejected pair
after that candidate disappears from the normal live-candidate files, then feed
those forward observations into the existing Reawakening V2 truth logic.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .market_data import _pair_to_snapshot, pair_lookup
from .reawakening_shadow import (
    _identity,
    _key,
    eligible_reject,
    run as shadow_run,
)

MODE = "RESEARCH_ONLY_REAWAKENING_EXACT_PAIR_FORWARD_V1"
STATE_FILE = "reawakening-forward-state.json"
REPORT_FILE = "reawakening-forward-report.json"
MAX_HOT_OBSERVATIONS = 192
DEFAULT_REQUEST_PAUSE_SECONDS = 0.22


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _same_pair(chain: str, left: Any, right: Any) -> bool:
    left = str(left or "")
    right = str(right or "")
    if not left or not right:
        return False
    if chain in {"ethereum", "bsc"}:
        return left.lower() == right.lower()
    return left == right


def exact_pair_snapshot(chain: str, token: str, pair_address: str) -> dict | None:
    """Fetch exactly the locked pair and prove target-token identity."""
    if not chain or not token or not pair_address:
        return None
    raw = pair_lookup(chain, pair_address)
    if not raw:
        return None
    live = _pair_to_snapshot(chain, token, raw)
    if not live:
        return None
    if live.get("token_identity_verified") is not True:
        return None
    if not _same_pair(chain, live.get("pair_address"), pair_address):
        return None
    return live


def _record_identity(record: dict) -> tuple[str, str, str, str]:
    snap = (
        record.get("first_reject_snapshot")
        if isinstance(record.get("first_reject_snapshot"), dict)
        else {}
    )
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    chain, token, pair = _identity(
        {
            "chain": identity.get("chain") or snap.get("chain"),
            "token": identity.get("token") or snap.get("token"),
            "pair_address": identity.get("pair_address") or snap.get("pair_address"),
        }
    )
    canonical = _key({"chain": chain, "token": token, "pair_address": pair})
    return chain, token, pair, canonical


def _compact_snapshot(
    live: dict,
    *,
    chain: str,
    token: str,
    pair: str,
    observed_at: str,
) -> dict:
    return {
        "observed_at": observed_at,
        "chain": chain,
        "token": token,
        "pair_address": pair,
        "source": "REAWAKENING_DIRECT_EXACT_PAIR_FORWARD",
        "token_identity_verified": live.get("token_identity_verified") is True,
        "target_token_side": live.get("target_token_side"),
        "price_usd": live.get("price_usd"),
        "liquidity_usd": live.get("liquidity_usd"),
        "volume_h1": live.get("volume_h1"),
        "buys_h1": live.get("buys_h1"),
        "sells_h1": live.get("sells_h1"),
    }


def _append_observation(candidate: dict, snapshot: dict) -> bool:
    observations = (
        candidate.get("hot_observations")
        if isinstance(candidate.get("hot_observations"), list)
        else []
    )
    fp = (
        snapshot.get("observed_at"),
        snapshot.get("pair_address"),
        snapshot.get("price_usd"),
        snapshot.get("liquidity_usd"),
    )
    existing = {
        (
            row.get("observed_at"),
            row.get("pair_address"),
            row.get("price_usd"),
            row.get("liquidity_usd"),
        )
        for row in observations
        if isinstance(row, dict)
    }
    if fp in existing:
        return False

    observations.append(snapshot)
    observations.sort(key=lambda x: str(x.get("observed_at") or ""))
    dropped = max(0, len(observations) - MAX_HOT_OBSERVATIONS)
    if dropped:
        candidate["hot_observations_compacted"] = int(
            candidate.get("hot_observations_compacted") or 0
        ) + dropped
    candidate["hot_observations"] = observations[-MAX_HOT_OBSERVATIONS:]
    candidate["observations_total"] = int(candidate.get("observations_total") or 0) + 1
    candidate["first_observed_at"] = (
        candidate.get("first_observed_at") or snapshot.get("observed_at")
    )
    candidate["last_observed_at"] = snapshot.get("observed_at")

    try:
        price = float(snapshot.get("price_usd") or 0)
    except Exception:
        price = 0.0
    try:
        liquidity = float(snapshot.get("liquidity_usd") or 0)
    except Exception:
        liquidity = 0.0

    if price > 0:
        candidate["peak_price_usd"] = max(
            float(candidate.get("peak_price_usd") or price), price
        )
    if liquidity >= 0:
        previous_max = candidate.get("max_liquidity_usd")
        previous_min = candidate.get("min_liquidity_usd")
        candidate["max_liquidity_usd"] = (
            max(float(previous_max), liquidity)
            if previous_max is not None
            else liquidity
        )
        candidate["min_liquidity_usd"] = (
            min(float(previous_min), liquidity)
            if previous_min is not None
            else liquidity
        )
    return True


def collect(
    output_dir: str = "data",
    *,
    now_override: str | None = None,
    pause_seconds: float | None = None,
) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = now_override or datetime.now(timezone.utc).isoformat()

    ledger = _load(out / "rejected-candidate-ledger.json", {})
    records = (
        ledger.get("records")
        if isinstance(ledger, dict) and isinstance(ledger.get("records"), dict)
        else {}
    )
    shadow_state = _load(out / "reawakening-shadow-state.json", {})
    v2_started_at = str(
        shadow_state.get("v2_started_at")
        or shadow_state.get("updated_at")
        or now
    )

    state_path = out / STATE_FILE
    old_state = _load(state_path, {})
    candidates = (
        old_state.get("candidates")
        if isinstance(old_state, dict)
        and isinstance(old_state.get("candidates"), dict)
        else {}
    )

    if pause_seconds is None:
        try:
            pause_seconds = float(
                os.environ.get(
                    "WALLET500_REAWAKENING_REQUEST_PAUSE_SECONDS",
                    DEFAULT_REQUEST_PAUSE_SECONDS,
                )
            )
        except Exception:
            pause_seconds = DEFAULT_REQUEST_PAUSE_SECONDS
    pause_seconds = max(0.0, float(pause_seconds))

    eligible = 0
    attempted = 0
    success = 0
    misses = 0
    invalid = 0
    added = 0

    for ledger_key, record in records.items():
        if not isinstance(record, dict):
            continue
        ok, eligibility_reasons = eligible_reject(record)
        if not ok:
            continue
        eligible += 1

        chain, token, pair, canonical = _record_identity(record)
        if not chain or not token or not pair or canonical == "||":
            invalid += 1
            continue

        candidate = (
            candidates.get(ledger_key)
            if isinstance(candidates.get(ledger_key), dict)
            else {}
        )
        candidate.update(
            {
                "token_key": ledger_key,
                "canonical_identity": canonical,
                "chain": chain,
                "token": token,
                "pair_address": pair,
                "first_rejected_at": record.get("first_rejected_at"),
                "v2_started_at": v2_started_at,
                "eligibility_reasons": eligibility_reasons,
                "updated_at": now,
            }
        )

        attempted += 1
        try:
            live = exact_pair_snapshot(chain, token, pair)
        except Exception:
            live = None

        if live is None:
            misses += 1
            candidate["last_measurement_status"] = "EXACT_PAIR_NOT_RETURNED_OR_IDENTITY_UNPROVEN"
            candidate["last_measurement_at"] = now
            candidates[ledger_key] = candidate
            if pause_seconds:
                time.sleep(pause_seconds)
            continue

        live_chain, live_token, live_pair = _identity(live)
        live_canonical = _key(
            {"chain": live_chain, "token": live_token, "pair_address": live_pair}
        )
        try:
            price = float(live.get("price_usd") or 0)
        except Exception:
            price = 0.0
        if (
            live.get("token_identity_verified") is not True
            or live_canonical != canonical
            or price <= 0
        ):
            invalid += 1
            candidate["last_measurement_status"] = "EXACT_PAIR_IDENTITY_VALIDATION_FAILED"
            candidate["last_measurement_at"] = now
            candidates[ledger_key] = candidate
            if pause_seconds:
                time.sleep(pause_seconds)
            continue

        snapshot = _compact_snapshot(
            live,
            chain=chain,
            token=token,
            pair=pair,
            observed_at=now,
        )
        if _append_observation(candidate, snapshot):
            added += 1
        success += 1
        candidate["last_measurement_status"] = "EXACT_PAIR_FORWARD_OBSERVED"
        candidate["last_measurement_at"] = now
        candidates[ledger_key] = candidate
        if pause_seconds:
            time.sleep(pause_seconds)

    state = {
        "version": 1,
        "mode": MODE,
        "updated_at": now,
        "v2_started_at": v2_started_at,
        "production_portfolio_impact": "NONE",
        "production_gate_changed": False,
        "automatic_buy": False,
        "measurement_contract": {
            "eligible_reject_rule": "REAWAKENING_V2_ELIGIBLE_REJECT_ONLY",
            "pair_identity": "IMMUTABLE_FIRST_REJECT_EXACT_PAIR",
            "token_identity_must_be_verified": True,
            "forward_only": True,
            "hot_observations_per_candidate": MAX_HOT_OBSERVATIONS,
            "hot_state_note": (
                "hot observations are bounded operational state; immutable trigger "
                "evidence remains in reawakening-shadow-state.json"
            ),
        },
        "candidates": candidates,
    }
    _write(state_path, state)

    report = {
        "updated_at": now,
        "mode": MODE,
        "v2_started_at": v2_started_at,
        "production_portfolio_impact": "NONE",
        "production_gate_changed": False,
        "automatic_buy": False,
        "eligible_rejects": eligible,
        "exact_pair_attempted": attempted,
        "exact_pair_successes": success,
        "exact_pair_misses": misses,
        "identity_invalid_or_missing": invalid,
        "observations_added_this_run": added,
        "state_candidates": len(candidates),
        "state_hot_observations": sum(
            len(c.get("hot_observations") or [])
            for c in candidates.values()
            if isinstance(c, dict)
        ),
    }
    _write(out / REPORT_FILE, report)
    return report


def _merge_history(existing: list[dict], direct: list[dict]) -> list[dict]:
    rows: dict[tuple, dict] = {}
    for row in [*(existing or []), *(direct or [])]:
        if not isinstance(row, dict):
            continue
        fp = (
            row.get("observed_at"),
            row.get("source"),
            row.get("price_usd"),
            row.get("liquidity_usd"),
            row.get("pair_address"),
        )
        rows[fp] = row
    return sorted(rows.values(), key=lambda x: str(x.get("observed_at") or ""))


def inject_forward_state_into_runtime_tracker(output_dir: str = "data") -> int:
    """Inject direct forward rows into the workspace tracker for shadow evaluation.

    The workflow publisher never stages outcome-tracker.json from this lane, so this
    mutation is runtime-only and cannot contaminate production measurement history.
    """
    out = Path(output_dir)
    forward = _load(out / STATE_FILE, {})
    candidates = (
        forward.get("candidates")
        if isinstance(forward, dict) and isinstance(forward.get("candidates"), dict)
        else {}
    )
    tracker_path = out / "outcome-tracker.json"
    tracker = _load(tracker_path, {})
    if not isinstance(tracker, dict):
        tracker = {}
    tokens = tracker.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
        tracker["tokens"] = tokens

    index: dict[str, str] = {}
    for tracker_key, record in tokens.items():
        if not isinstance(record, dict):
            continue
        canonical = _key(
            {
                "chain": record.get("chain"),
                "token": record.get("token"),
                "pair_address": record.get("entry_pair_address"),
            }
        )
        if canonical != "||":
            index[canonical] = tracker_key

    injected = 0
    for ledger_key, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        direct = [
            x
            for x in (candidate.get("hot_observations") or [])
            if isinstance(x, dict)
        ]
        if not direct:
            continue
        canonical = str(candidate.get("canonical_identity") or "")
        if not canonical or canonical == "||":
            continue

        tracker_key = index.get(canonical)
        if tracker_key is None:
            tracker_key = f"reawakening-forward::{ledger_key}"
            tokens[tracker_key] = {
                "chain": candidate.get("chain"),
                "token": candidate.get("token"),
                "entry_pair_address": candidate.get("pair_address"),
                "history": [],
                "research_only_runtime_overlay": True,
            }
            index[canonical] = tracker_key

        tracker_record = tokens.get(tracker_key)
        if not isinstance(tracker_record, dict):
            continue
        existing = (
            tracker_record.get("history")
            if isinstance(tracker_record.get("history"), list)
            else []
        )
        tracker_record["history"] = _merge_history(existing, direct)
        tracker_record["reawakening_forward_overlay"] = True
        tokens[tracker_key] = tracker_record
        injected += 1

    tracker["tokens"] = tokens
    tracker_path.write_text(json.dumps(tracker, indent=2), encoding="utf-8")
    return injected


def _postprocess_shadow(
    output_dir: str,
    report: dict,
    injected_candidates: int,
) -> dict:
    out = Path(output_dir)
    payload_path = out / "reawakening-shadow.json"
    shadow_state_path = out / "reawakening-shadow-state.json"
    payload = _load(payload_path, {})
    shadow_state = _load(shadow_state_path, {})
    forward = _load(out / STATE_FILE, {})
    candidates = (
        forward.get("candidates")
        if isinstance(forward, dict) and isinstance(forward.get("candidates"), dict)
        else {}
    )

    direct_times: dict[str, set[str]] = {}
    for key, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        direct_times[key] = {
            str(row.get("observed_at"))
            for row in (candidate.get("hot_observations") or [])
            if isinstance(row, dict) and row.get("observed_at")
        }

    targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    triggers = (
        shadow_state.get("v2_triggers")
        if isinstance(shadow_state, dict)
        and isinstance(shadow_state.get("v2_triggers"), dict)
        else {}
    )
    direct_trigger_count = 0
    for target in targets:
        if not isinstance(target, dict):
            continue
        key = str(target.get("token_key") or "")
        timestamps = direct_times.get(key, set())
        if (
            str(target.get("triggered_at") or "") in timestamps
            or str(target.get("first_confirmation_at") or "") in timestamps
        ):
            target["evidence_source"] = "DEDICATED_EXACT_PAIR_FORWARD_TRACKER"
            direct_trigger_count += 1
            if isinstance(triggers.get(key), dict):
                triggers[key]["evidence_source"] = "DEDICATED_EXACT_PAIR_FORWARD_TRACKER"

    if isinstance(shadow_state, dict):
        shadow_state["v2_triggers"] = triggers
        _write(shadow_state_path, shadow_state)

    payload["primary_recheck_source"] = (
        "reawakening-forward-state.json dedicated exact-pair observations + "
        "outcome-tracker.json exact-pair history"
    )
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    counts.update(
        {
            "dedicated_forward_state_candidates": int(report.get("state_candidates") or 0),
            "dedicated_forward_hot_rows": int(report.get("state_hot_observations") or 0),
            "dedicated_forward_observations_added_this_run": int(
                report.get("observations_added_this_run") or 0
            ),
            "dedicated_forward_exact_pair_successes_this_run": int(
                report.get("exact_pair_successes") or 0
            ),
            "dedicated_forward_exact_pair_misses_this_run": int(
                report.get("exact_pair_misses") or 0
            ),
            "dedicated_forward_runtime_tracker_candidates": injected_candidates,
            "dedicated_forward_triggers_v2": direct_trigger_count,
        }
    )
    payload["counts"] = counts
    payload["dedicated_forward_contract"] = {
        "mode": MODE,
        "research_only": True,
        "production_gate_changed": False,
        "automatic_buy": False,
        "immutable_exact_pair": True,
        "token_identity_verified_required": True,
        "forward_only": True,
    }
    truth_rules = (
        payload.get("truth_rules") if isinstance(payload.get("truth_rules"), list) else []
    )
    rule = (
        "dedicated forward observations measure the immutable rejected exact pair "
        "independently of normal live-candidate files and never change production"
    )
    if rule not in truth_rules:
        truth_rules.append(rule)
    payload["truth_rules"] = truth_rules
    payload["targets"] = targets
    _write(payload_path, payload)
    return payload


def run(
    output_dir: str = "data",
    *,
    now_override: str | None = None,
    pause_seconds: float | None = None,
) -> dict:
    report = collect(
        output_dir,
        now_override=now_override,
        pause_seconds=pause_seconds,
    )
    injected = inject_forward_state_into_runtime_tracker(output_dir)
    shadow_run(output_dir)
    payload = _postprocess_shadow(output_dir, report, injected)

    report["runtime_tracker_candidates_injected"] = injected
    report["shadow_triggers_v2"] = int(
        (payload.get("counts") or {}).get("shadow_triggers_v2") or 0
    )
    _write(Path(output_dir) / REPORT_FILE, report)
    print(
        json.dumps(
            {
                "mode": MODE,
                "eligible_rejects": report.get("eligible_rejects"),
                "exact_pair_successes": report.get("exact_pair_successes"),
                "exact_pair_misses": report.get("exact_pair_misses"),
                "observations_added": report.get("observations_added_this_run"),
                "runtime_tracker_candidates_injected": injected,
                "shadow_triggers_v2": report.get("shadow_triggers_v2"),
            },
            indent=2,
        )
    )
    return payload


if __name__ == "__main__":
    run()
