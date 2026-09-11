from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "WALLET500_ENGINE_LEARNING_REVIEW_V1"


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _dt(value: Any):
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _rows(payload: Any) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    for key in ("alerts", "targets", "active_deep_watch", "coins", "candidates", "rows", "records", "wallets"):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def _identity(row: dict) -> str:
    chain = str(row.get("network") or row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or row.get("address") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or row.get("pair") or "").lower().strip()
    return f"{chain}|{token}|{pair}" if chain and token and pair else ""


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _provider_health(waking: dict) -> dict:
    statuses: list[dict] = []
    for row in waking.get("targets") or []:
        if isinstance(row, dict):
            statuses.extend(x for x in (row.get("provider_status") or []) if isinstance(x, dict))
    if not statuses:
        for key, count in (waking.get("provider_status_counts") or {}).items():
            if ":" in str(key):
                provider, status = str(key).split(":", 1)
                for _ in range(int(count or 0)):
                    statuses.append({"provider": provider, "status": status})
    by_provider: dict[str, Counter] = {}
    for item in statuses:
        p = str(item.get("provider") or "unknown").lower()
        s = str(item.get("status") or "UNKNOWN").upper()
        by_provider.setdefault(p, Counter())[s] += 1
    out = {}
    degraded = []
    for provider, counts in sorted(by_provider.items()):
        total = sum(counts.values())
        healthy = sum(v for k, v in counts.items() if k in {"OK", "SUCCESS", "AVAILABLE"})
        bad = total - healthy
        state = "HEALTHY" if total and bad == 0 else "DEGRADED" if healthy else "UNAVAILABLE"
        out[provider] = {"state": state, "observations": total, "healthy": healthy, "failed_or_unavailable": bad, "statuses": dict(counts)}
        if state != "HEALTHY":
            degraded.append(provider)
    return {"providers": out, "degraded_providers": degraded, "provider_count": len(out), "healthy_provider_count": sum(x["state"] == "HEALTHY" for x in out.values())}


def _num(obj: dict, *keys: str) -> float:
    for key in keys:
        try:
            value = obj.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass
    return 0.0


def _smart_money(data: Path) -> dict:
    files = sorted({*data.glob("*smart*money*.json"), *data.glob("*wallet*quality*.json")})
    status_counts = Counter()
    tier_counts = Counter()
    wallets = 0
    exact_files = []
    pending_rows: dict[str, dict] = {}
    for path in files:
        payload = _load(path, {})
        if not payload:
            continue
        exact_files.append(path.name)
        for obj in _walk(payload):
            status = obj.get("status") or obj.get("qualification_status") or obj.get("history_status")
            tier = obj.get("tier") or obj.get("quality_tier") or obj.get("wallet_tier")
            address = obj.get("wallet") or obj.get("wallet_address") or obj.get("address")
            if address and (status or tier):
                wallets += 1
                if status:
                    status_counts[str(status)] += 1
                if tier:
                    tier_counts[str(tier)] += 1
                if status and "PENDING_HISTORY" in str(status).upper():
                    completed = _num(obj, "completed_exposures", "history_completed", "completed_history")
                    eligible = _num(obj, "eligible_exposures", "history_eligible", "eligible_history")
                    cross = _num(obj, "cross_token_count", "cross_token", "tokens_seen")
                    evidence_fields = sum(obj.get(k) not in (None, "", [], {}) for k in (
                        "completed_exposures", "eligible_exposures", "cross_token_count",
                        "win_rate", "roi", "realized_pnl", "timing_edge", "false_positive_rate",
                    ))
                    score = completed * 1000.0 + cross * 100.0 + eligible * 10.0 + evidence_fields
                    row = {
                        "wallet": str(address),
                        "status": str(status),
                        "source_file": path.name,
                        "completed_exposures": completed,
                        "eligible_exposures": eligible,
                        "cross_token_count": cross,
                        "existing_evidence_fields": evidence_fields,
                        "priority_score_existing_evidence_only": score,
                        "promotion_forbidden": True,
                        "threshold_change_forbidden": True,
                    }
                    prev = pending_rows.get(str(address))
                    if prev is None or score > prev["priority_score_existing_evidence_only"]:
                        pending_rows[str(address)] = row
    pending = sum(v for k, v in status_counts.items() if "PENDING_HISTORY" in k.upper())
    qualified = sum(v for k, v in status_counts.items() if any(x in k.upper() for x in ("QUALIFIED", "VERIFIED", "ELITE", "STRONG")) and "PENDING" not in k.upper())
    queue = sorted(pending_rows.values(), key=lambda x: (-x["priority_score_existing_evidence_only"], x["wallet"]))[:100]
    return {
        "source_files": exact_files,
        "wallet_rows_with_quality_state": wallets,
        "status_counts": dict(status_counts),
        "tier_counts": dict(tier_counts),
        "pending_history": pending,
        "qualified_or_verified": qualified,
        "backlog_ratio": round(pending / max(1, pending + qualified), 4),
        "qualification_queue_mode": "RESEARCH_ONLY_EXISTING_EVIDENCE_PRIORITY",
        "qualification_queue": queue,
        "qualification_queue_rule": "ORDER_EXISTING_PENDING_HISTORY_FOR_REVIEW_ONLY; NEVER PROMOTE_OR_CHANGE_QUALIFICATION_THRESHOLDS",
    }


def _outcome_index(data: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name in ("alpha-proof-ledger.json", "alpha-proof-report.json", "signal-outcomes.json"):
        payload = _load(data / name, {})
        for row in _rows(payload):
            key = _identity(row)
            if not key:
                continue
            outcome = row.get("outcome") or row.get("classification") or row.get("result") or row.get("status")
            observed = row.get("outcome_at") or row.get("resolved_at") or row.get("updated_at") or row.get("generated_at")
            if outcome is not None:
                out.setdefault(key, {"source": name, "outcome": outcome, "observed_at": observed})
    return out


def run(data_dir: str | Path = "data", now: str | None = None) -> dict:
    data = Path(data_dir)
    generated = now or datetime.now(timezone.utc).isoformat()
    bench = _load(data / "prospective-benchmark-ledger.json", {})
    latest = _load(data / "prospective-benchmark-latest.json", {})
    waking = _load(data / "waking-confirmation-latest.json", {})
    if bench and (bench.get("no_hindsight") is not True or bench.get("production_effect") is not False):
        raise RuntimeError("PROSPECTIVE_BENCHMARK_TRUTH_INVALID")

    records = bench.get("records") or {}
    outcomes = _outcome_index(data)
    blocker_counts = Counter()
    cohort = []
    missed = []
    attribution_ready = 0
    lead_rows = []
    for identity, rec in records.items():
        if len(str(identity).split("|")) != 3:
            continue
        stages = rec.get("stages") or {}
        blockers = []
        if "WAKING" in stages and "PRE_T0" not in stages:
            blockers.append("WAITING_FOR_IMMUTABLE_PRE_T0_BINDING_OR_EVIDENCE")
        if "PRE_T0" in stages and "PRODUCTION" not in stages:
            blockers.append("RESEARCH_ONLY_NOT_PRODUCTION_VERIFIED")
        if not stages:
            blockers.append("NO_VERIFIED_STAGE_OBSERVATION")
        frozen = {stage: (info or {}).get("frozen_evidence") for stage, info in stages.items() if isinstance(info, dict) and (info or {}).get("frozen_evidence")}
        if frozen:
            attribution_ready += 1
        else:
            blockers.append("ATTRIBUTION_NOT_FROZEN_AT_FIRST_SEEN")
        blocker_counts.update(blockers)
        highest = next((s for s in ("PRODUCTION", "PRE_T0", "WAKING") if s in stages), "DISCOVERED")
        outcome = outcomes.get(identity)
        row = {"identity": identity, "highest_stage": highest, "blockers": blockers, "frozen_evidence_stages": sorted(frozen), "canonical_later_outcome": outcome}
        cohort.append(row)
        if outcome and "PRODUCTION" not in stages:
            missed.append({"identity": identity, "highest_stage": highest, "canonical_later_outcome": outcome, "interpretation": "RESEARCH_ONLY_CANDIDATE_WITH_LATER_CANONICAL_OUTCOME_NO_NEW_SUCCESS_THRESHOLD"})
        if outcome and outcome.get("observed_at"):
            ot = _dt(outcome.get("observed_at"))
            if ot:
                lead = {"identity": identity, "outcome_source": outcome.get("source")}
                for stage in ("WAKING", "PRE_T0", "PRODUCTION"):
                    st = _dt((stages.get(stage) or {}).get("first_seen_at"))
                    lead[f"{stage.lower()}_lead_minutes"] = round((ot-st).total_seconds()/60, 2) if st and ot >= st else None
                lead_rows.append(lead)

    provider = _provider_health(waking)
    smart = _smart_money(data)
    payload = {
        "version": VERSION,
        "generated_at": generated,
        "mode": "RESEARCH_ONLY_PROSPECTIVE_ENGINE_LEARNING",
        "no_hindsight": True,
        "production_effect": False,
        "automatic_buy": False,
        "truth_contract": {
            "production_threshold_changes": "FORBIDDEN",
            "retrospective_first_seen_backfill": "FORBIDDEN",
            "outcome_success_threshold_invented_here": False,
            "exact_pair_identity_required": True,
            "failed_provider_counts_as_positive_evidence": False,
            "smart_money_queue_can_promote": False,
        },
        "prospective_cohort": {"records": len(cohort), "stage_counts": (latest.get("counts") or {}), "blocker_counts": dict(blocker_counts), "attribution_ready_records": attribution_ready, "rows": cohort},
        "missed_outcomes": {"count": len(missed), "rows": missed},
        "provider_health": provider,
        "smart_money_quality": smart,
        "lead_time": {"rows_with_canonical_outcome_time": len(lead_rows), "rows": lead_rows},
        "signal_attribution": {"ready": attribution_ready, "rule": "USE_ONLY_FROZEN_EVIDENCE_CAPTURED_AT_FIRST_STAGE_OBSERVATION; NEVER BACKFILL OLD RECORDS"},
    }
    _write(data / "engine-learning-review.json", payload)
    return payload


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
