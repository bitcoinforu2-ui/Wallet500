from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "WALLET500_PROSPECTIVE_BENCHMARK_V1"
STAGES = ("DISCOVERED", "WAKING", "PRE_T0", "PRODUCTION")


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


def _rows(payload: dict) -> list[dict]:
    for key in ("alerts", "targets", "active_deep_watch", "coins", "candidates"):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def _direct_identity(row: dict) -> tuple[str, str, str]:
    chain = str(row.get("network") or row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or row.get("address") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or row.get("pair") or "").lower().strip()
    return chain, token, pair


def _unique_pair_index(revival: dict) -> dict[tuple[str, str], str]:
    seen: dict[tuple[str, str], set[str]] = {}
    for row in _rows(revival):
        chain, token, pair = _direct_identity(row)
        if chain and token and pair:
            seen.setdefault((chain, token), set()).add(pair)
    return {key: next(iter(pairs)) for key, pairs in seen.items() if len(pairs) == 1}


def _key(row: dict, unique_pairs: dict[tuple[str, str], str]) -> tuple[str, bool]:
    chain, token, pair = _direct_identity(row)
    joined = False
    if chain and token and not pair:
        pair = unique_pairs.get((chain, token), "")
        joined = bool(pair)
    return (f"{chain}|{token}|{pair}" if chain and token and pair else "", joined)


def _iso(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _freeze_evidence(row: dict) -> dict:
    """Freeze only evidence present at first stage observation.

    This intentionally ignores later outcomes and never mutates an existing stage.
    The allow-list prevents accidental persistence of bulky or unrelated state.
    """
    out: dict[str, Any] = {}
    for key in (
        "confirmation_status", "confirmation_score", "base_watch_status", "watch_status",
        "signals", "strong_channels", "channels", "provider_status", "provider_status_counts",
        "pre_t0_shadow_status", "pre_t0_metrics", "decision", "decision_status", "withheld_reason",
        "verified", "actionable", "liquidity_usd", "execution_liquidity_usd",
    ):
        if key in row:
            out[key] = row.get(key)
    return out


def run(data_dir: str | Path = "data", now: str | None = None) -> dict:
    data = Path(data_dir)
    generated = now or datetime.now(timezone.utc).isoformat()
    ledger_path = data / "prospective-benchmark-ledger.json"
    ledger = _load(ledger_path, {"version": VERSION, "mode": "RESEARCH_ONLY_PROSPECTIVE_NO_HINDSIGHT", "no_hindsight": True, "records": {}})
    if ledger.get("version") != VERSION or ledger.get("no_hindsight") is not True:
        raise RuntimeError("PROSPECTIVE_LEDGER_TRUTH_INVALID")
    records = ledger.setdefault("records", {})

    revival = _load(data / "revival-1000-latest.json", {})
    if revival and (revival.get("network") != "solana" or revival.get("no_hindsight") is not True):
        raise RuntimeError("PROSPECTIVE_IDENTITY_SOURCE_TRUTH_INVALID")
    unique_pairs = _unique_pair_index(revival)

    feeds = [
        ("WAKING", _load(data / "waking-confirmation-latest.json", {})),
        ("PRE_T0", _load(data / "waking-pre-t0-confirmation.json", {})),
        ("PRODUCTION", _load(data / "real-alerts.json", {})),
    ]
    skipped_missing_exact_pair = 0
    joined_exact_pair = 0
    frozen_new_stage_evidence = 0
    for stage, payload in feeds:
        feed_observed_at = payload.get("generated_at") or generated
        for row in _rows(payload):
            key, joined = _key(row, unique_pairs)
            if not key:
                skipped_missing_exact_pair += 1
                continue
            observed_at = generated if joined else feed_observed_at
            if joined:
                joined_exact_pair += 1
            rec = records.setdefault(key, {"identity": key, "first_seen_at": observed_at, "stages": {}, "immutable_first_observation": True})
            stages = rec.setdefault("stages", {})
            if stage not in stages:
                frozen = _freeze_evidence(row)
                stages[stage] = {
                    "first_seen_at": observed_at,
                    "exact_pair_joined_at_observation": joined,
                    "frozen_evidence": frozen,
                    "frozen_evidence_backfilled": False,
                }
                if frozen:
                    frozen_new_stage_evidence += 1
            # Critical no-hindsight rule: an existing stage is never enriched later.

    progression = []
    dwell: dict[str, list[float]] = {"WAKING_TO_PRE_T0": [], "PRE_T0_TO_PRODUCTION": []}
    for key, rec in records.items():
        stages = rec.get("stages") or {}
        w, p, r = (_iso((stages.get(x) or {}).get("first_seen_at")) for x in ("WAKING", "PRE_T0", "PRODUCTION"))
        blockers = []
        if "WAKING" in stages and "PRE_T0" not in stages:
            blockers.append("WAITING_FOR_IMMUTABLE_PRE_T0_BINDING_OR_EVIDENCE")
        if "PRE_T0" in stages and "PRODUCTION" not in stages:
            blockers.append("RESEARCH_ONLY_NOT_PRODUCTION_VERIFIED")
        if not any((info or {}).get("frozen_evidence") for info in stages.values() if isinstance(info, dict)):
            blockers.append("ATTRIBUTION_NOT_FROZEN_AT_FIRST_SEEN")
        if w and p and p >= w:
            dwell["WAKING_TO_PRE_T0"].append((p-w).total_seconds()/60)
        if p and r and r >= p:
            dwell["PRE_T0_TO_PRODUCTION"].append((r-p).total_seconds()/60)
        progression.append({"identity": key, "highest_stage": next((s for s in reversed(STAGES) if s in stages), "DISCOVERED"), "blockers": blockers})

    def stats(xs: list[float]) -> dict:
        if not xs:
            return {"n": 0, "median_minutes": None, "p90_minutes": None}
        ys = sorted(xs); n = len(ys)
        return {"n": n, "median_minutes": round(ys[(n-1)//2], 2), "p90_minutes": round(ys[min(n-1, int((n-1)*0.9))], 2)}

    ledger["updated_at"] = generated
    ledger["production_effect"] = False
    ledger["automatic_buy"] = False
    ledger["identity_contract"] = {"key": "chain|token|exact_pair", "symbol_fallback": False, "ambiguous_pair_join": "FORBIDDEN", "joined_pair_first_seen_backdating": "FORBIDDEN"}
    ledger["attribution_contract"] = {"freeze_only_at_first_stage_observation": True, "retrospective_evidence_backfill": "FORBIDDEN", "outcome_fields_frozen_as_signal_evidence": False}
    _write(ledger_path, ledger)
    out = {
        "version": VERSION, "generated_at": generated, "mode": ledger["mode"], "no_hindsight": True, "production_effect": False,
        "identity_quality": {"joined_unique_exact_pair_this_run": joined_exact_pair, "skipped_missing_or_ambiguous_exact_pair_this_run": skipped_missing_exact_pair},
        "attribution_quality": {"new_stage_evidence_frozen_this_run": frozen_new_stage_evidence, "retrospective_backfill": False},
        "counts": {"cohort": len(records), "waking": sum("WAKING" in (r.get("stages") or {}) for r in records.values()), "pre_t0": sum("PRE_T0" in (r.get("stages") or {}) for r in records.values()), "production": sum("PRODUCTION" in (r.get("stages") or {}) for r in records.values())},
        "dwell": {k: stats(v) for k, v in dwell.items()}, "progression": progression,
    }
    _write(data / "prospective-benchmark-latest.json", out)
    return out


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
