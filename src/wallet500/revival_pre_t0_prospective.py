from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "REVIVAL_PRE_T0_PROSPECTIVE_V1"
MODE = "RESEARCH_ONLY_PRE_T0_PROSPECTIVE_VALIDATION"
NETWORK = "solana"
PRE_MODE = "RESEARCH_ONLY_IMMUTABLE_PRE_T0_EVIDENCE"
FORENSICS_MODE = "RESEARCH_ONLY_REVIVAL_FORENSICS_V2"
WINNERS = {"REVIVAL_X2", "REVIVAL_X4", "REVIVAL_X10"}
FAILURES = {"NO_REVIVAL_24H", "FAILED_LIQUIDITY_SURVIVAL"}
HORIZONS = ("5m", "15m", "60m", "240m", "1440m")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _n(value: object) -> float | None:
    try:
        x = float(value)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _key(token: str, pair: str) -> str:
    return f"{token}|{pair.lower()}"


def _pair_exact(a: object, b: object) -> bool:
    # Solana base58 is case-sensitive. Never normalize the actual identity check.
    return bool(a) and bool(b) and str(a) == str(b)


def _valid_binding(binding: dict, event: dict) -> tuple[bool, str]:
    if binding.get("status") != "BOUND_TO_PRE_WAKING_EVIDENCE":
        return False, "NOT_BOUND"
    snap = binding.get("snapshot")
    if not isinstance(snap, dict):
        return False, "SNAPSHOT_MISSING"
    t0 = event.get("t0") or {}
    token = str(event.get("token_address") or "")
    pair = str(t0.get("pair_address") or "")
    if str(snap.get("token_address") or "") != token:
        return False, "TOKEN_MISMATCH"
    if not _pair_exact(snap.get("pair_address"), pair):
        return False, "PAIR_MISMATCH"
    captured = _dt(snap.get("captured_at"))
    waking = _dt(t0.get("waking_t0"))
    if not captured or not waking:
        return False, "TIME_MISSING"
    if captured > waking:
        return False, "POST_T0_BINDING_FORBIDDEN"
    if snap.get("record_id") != binding.get("pre_t0_record_id"):
        return False, "RECORD_ID_MISMATCH"
    if snap.get("evidence_sha256") != binding.get("pre_t0_evidence_sha256"):
        return False, "EVIDENCE_HASH_MISMATCH"
    return True, "OK"


def _result_row(event: dict, binding: dict) -> dict:
    snap = binding["snapshot"]
    outcome = str(event.get("outcome_class") or "PENDING_24H")
    horizons = event.get("horizons") or {}
    selected_horizons = {k: horizons[k] for k in HORIZONS if isinstance(horizons.get(k), dict)}
    return {
        "event_id": event.get("event_id"),
        "network": NETWORK,
        "token_address": event.get("token_address"),
        "symbol": event.get("symbol"),
        "pair_address": (event.get("t0") or {}).get("pair_address"),
        "waking_t0": (event.get("t0") or {}).get("waking_t0"),
        "pre_t0_record_id": binding.get("pre_t0_record_id"),
        "pre_t0_captured_at": binding.get("pre_t0_captured_at"),
        "pre_t0_evidence_sha256": binding.get("pre_t0_evidence_sha256"),
        "pre_t0_shadow_status": (snap.get("confirmation_shadow") or {}).get("status"),
        "pre_t0_coverage": snap.get("coverage") or {},
        "pre_t0_families": snap.get("families") or {},
        "pre_t0_market": snap.get("market") or {},
        "outcome": {
            "class": outcome,
            "completed_24h": event.get("completed") is True,
            "completed_at": event.get("completed_at"),
            "peak_return_pct": _n(event.get("peak_return_pct")),
            "max_drawdown_from_t0_pct": _n(event.get("max_drawdown_from_t0_pct")),
            "minimum_liquidity_return_pct": _n(event.get("minimum_liquidity_return_pct")),
            "winner_x2_plus": outcome in WINNERS,
            "failure": outcome in FAILURES,
        },
        "checkpoints": selected_horizons,
        "truth_contract": {
            "pre_t0_must_predate_or_equal_waking_t0": True,
            "exact_token": True,
            "exact_pair_case_sensitive": True,
            "post_t0_feature_backfill": "FORBIDDEN",
            "outcome_source": "REVIVAL_FORENSICS_V2_FORWARD_ONLY",
        },
    }


def _summary(rows: list[dict]) -> dict:
    completed = [r for r in rows if (r.get("outcome") or {}).get("completed_24h")]
    winners = [r for r in completed if (r.get("outcome") or {}).get("winner_x2_plus")]
    failures = [r for r in completed if (r.get("outcome") or {}).get("failure")]
    by_shadow: dict[str, dict] = {}
    for status in sorted({str(r.get("pre_t0_shadow_status") or "UNKNOWN") for r in rows}):
        group = [r for r in rows if str(r.get("pre_t0_shadow_status") or "UNKNOWN") == status]
        done = [r for r in group if (r.get("outcome") or {}).get("completed_24h")]
        wins = [r for r in done if (r.get("outcome") or {}).get("winner_x2_plus")]
        by_shadow[status] = {
            "enrolled": len(group),
            "completed": len(done),
            "winners_x2_plus": len(wins),
            "win_rate_completed": round(len(wins) / len(done), 6) if done else None,
        }
    family_stats = {}
    family_names = sorted({name for r in rows for name in (r.get("pre_t0_families") or {})})
    for name in family_names:
        positive = [r for r in rows if ((r.get("pre_t0_families") or {}).get(name) or {}).get("positive") is True]
        done = [r for r in positive if (r.get("outcome") or {}).get("completed_24h")]
        wins = [r for r in done if (r.get("outcome") or {}).get("winner_x2_plus")]
        family_stats[name] = {
            "positive_at_pre_t0": len(positive),
            "completed": len(done),
            "winners_x2_plus": len(wins),
            "win_rate_completed": round(len(wins) / len(done), 6) if done else None,
        }
    return {
        "enrolled_with_valid_pre_t0": len(rows),
        "pending_24h": len(rows) - len(completed),
        "completed_24h": len(completed),
        "winners_x2_plus": len(winners),
        "failures": len(failures),
        "win_rate_completed": round(len(winners) / len(completed), 6) if completed else None,
        "by_pre_t0_shadow_status": by_shadow,
        "family_positive_forward_performance": family_stats,
        "claim_status": (
            "ENOUGH_FOR_PRELIMINARY_PROSPECTIVE_COMPARISON"
            if len(completed) >= 20 and len(winners) >= 5 and len(failures) >= 5
            else "INSUFFICIENT_PROSPECTIVE_SAMPLE"
        ),
    }


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    ledger = _load(data / "revival-pre-t0-evidence-ledger.json", {})
    forensics = _load(data / "revival-forensics-latest.json", {})
    if ledger.get("mode") != PRE_MODE or ledger.get("no_hindsight") is not True:
        raise RuntimeError("PRE_T0_PROSPECTIVE_LEDGER_TRUTH_INVALID")
    if forensics.get("mode") != FORENSICS_MODE or forensics.get("no_hindsight") is not True:
        raise RuntimeError("PRE_T0_PROSPECTIVE_FORENSICS_TRUTH_INVALID")
    if forensics.get("network") != NETWORK or forensics.get("production_portfolio_impact") != "NONE":
        raise RuntimeError("PRE_T0_PROSPECTIVE_FORENSICS_SAFETY_INVALID")

    bindings = ledger.get("waking_bindings") or {}
    rows = []
    invalid = defaultdict(int)
    for event in forensics.get("events") or []:
        if not isinstance(event, dict):
            continue
        t0 = event.get("t0") or {}
        token = str(event.get("token_address") or "")
        pair = str(t0.get("pair_address") or "")
        if not token or not pair:
            invalid["EVENT_IDENTITY_MISSING"] += 1
            continue
        binding = bindings.get(_key(token, pair))
        if not isinstance(binding, dict):
            continue
        ok, reason = _valid_binding(binding, event)
        if not ok:
            invalid[reason] += 1
            continue
        rows.append(_result_row(event, binding))

    rows.sort(key=lambda r: str(r.get("waking_t0") or ""), reverse=True)
    generated = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": VERSION,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": generated,
        "source_pre_t0_updated_at": ledger.get("updated_at"),
        "source_forensics_generated_at": forensics.get("generated_at"),
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "horizons": list(HORIZONS),
        "truth_contract": {
            "enrollment_requires_existing_bound_pre_t0_snapshot": True,
            "pre_t0_snapshot_must_not_postdate_waking_t0": True,
            "exact_pair_case_sensitive_validation": True,
            "retroactive_pre_t0_backfill": "FORBIDDEN",
            "outcomes_are_forward_forensics_only": True,
            "production_thresholds_modified": False,
        },
        "invalid_binding_counts": dict(invalid),
        "summary": _summary(rows),
        "events": rows,
    }
    _write(data / "revival-pre-t0-prospective.json", payload)
    return payload


def main() -> None:
    p = run()
    print(json.dumps({"version": p["version"], "summary": p["summary"], "invalid": p["invalid_binding_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
