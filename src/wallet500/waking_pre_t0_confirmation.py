from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "WAKING_PRE_T0_CONFIRMATION_V1"
MODE = "RESEARCH_ONLY_WAKING_PRE_T0_CONFIRMATION_SHADOW"
NETWORK = "solana"


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _key(token: str, pair: str) -> str:
    return f"{token}|{pair.lower()}"


def _pair_index(revival: dict) -> dict[str, str]:
    out = {}
    for row in revival.get("coins") or []:
        if not isinstance(row, dict):
            continue
        token = str(row.get("token_address") or "").strip()
        pair = str(row.get("dex_pair_address") or "").strip()
        if token and pair:
            out[token] = pair
    return out


def shadow_status(binding: dict | None) -> tuple[str, dict]:
    if not isinstance(binding, dict):
        return "MISSING_PRE_T0_BINDING", {"verified_families": 0, "positive_families": 0}
    if binding.get("status") != "BOUND_TO_PRE_WAKING_EVIDENCE" or not isinstance(binding.get("snapshot"), dict):
        return "MISSING_PRE_T0_NO_BACKFILL", {"verified_families": 0, "positive_families": 0}
    snapshot = binding["snapshot"]
    coverage = snapshot.get("coverage") or {}
    verified = int(coverage.get("verified_families") or 0)
    positive = int(coverage.get("positive_families_excluding_concentration") or 0)
    concentration = ((snapshot.get("families") or {}).get("concentration") or {})
    risk = concentration.get("concentration_risk_score")
    try:
        high_risk = risk is not None and float(risk) >= 70
    except (TypeError, ValueError):
        high_risk = False
    if high_risk:
        status = "PRE_T0_RISK_SHADOW"
    elif verified >= 4 and positive >= 3:
        status = "PRE_T0_STRONG_SHADOW"
    elif verified >= 3 and positive >= 2:
        status = "PRE_T0_CONFIRMED_SHADOW"
    elif verified >= 2:
        status = "PRE_T0_PARTIAL_SHADOW"
    else:
        status = "PRE_T0_INSUFFICIENT_SHADOW"
    return status, {
        "verified_families": verified,
        "positive_families": positive,
        "concentration_risk_score": risk,
    }


def run(data_dir: str | Path = "data", now: str | None = None) -> dict:
    data = Path(data_dir)
    waking = _load(data / "waking-confirmation-latest.json", {})
    revival = _load(data / "revival-1000-latest.json", {})
    ledger = _load(data / "revival-pre-t0-evidence-ledger.json", {})
    if waking.get("network") != NETWORK or waking.get("no_hindsight") is not True:
        raise RuntimeError("WAKING_CONFIRMATION_SOURCE_TRUTH_INVALID")
    if revival.get("network") != NETWORK or revival.get("no_hindsight") is not True:
        raise RuntimeError("REVIVAL_SOURCE_TRUTH_INVALID")
    if ledger and (ledger.get("mode") != "RESEARCH_ONLY_IMMUTABLE_PRE_T0_EVIDENCE" or ledger.get("no_hindsight") is not True):
        raise RuntimeError("PRE_T0_LEDGER_TRUTH_INVALID")

    pairs = _pair_index(revival)
    bindings = ledger.get("waking_bindings") or {}
    rows = []
    for row in waking.get("targets") or []:
        if not isinstance(row, dict):
            continue
        token = str(row.get("token_address") or "").strip()
        pair = pairs.get(token, "")
        binding = bindings.get(_key(token, pair)) if token and pair else None
        status, metrics = shadow_status(binding)
        rows.append({
            "network": NETWORK,
            "token_address": token,
            "symbol": row.get("symbol"),
            "pair_address": pair or None,
            "waking_confirmation_status": row.get("confirmation_status"),
            "waking_confirmation_score": row.get("confirmation_score"),
            "pre_t0_shadow_status": status,
            "pre_t0_metrics": metrics,
            "pre_t0_binding": binding,
            "production_effect": False,
            "pre_alpha_promotion": "FORBIDDEN",
            "automatic_buy": False,
        })

    generated = now or datetime.now(timezone.utc).isoformat()
    counts = {
        "waking_targets": len(rows),
        "pre_t0_bound": sum(1 for r in rows if r["pre_t0_shadow_status"] not in {"MISSING_PRE_T0_BINDING", "MISSING_PRE_T0_NO_BACKFILL"}),
        "pre_t0_strong": sum(1 for r in rows if r["pre_t0_shadow_status"] == "PRE_T0_STRONG_SHADOW"),
        "pre_t0_confirmed": sum(1 for r in rows if r["pre_t0_shadow_status"] == "PRE_T0_CONFIRMED_SHADOW"),
        "pre_t0_missing": sum(1 for r in rows if r["pre_t0_shadow_status"] in {"MISSING_PRE_T0_BINDING", "MISSING_PRE_T0_NO_BACKFILL"}),
    }
    payload = {
        "version": VERSION,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": generated,
        "source_waking_generated_at": waking.get("generated_at"),
        "source_revival_generated_at": revival.get("generated_at"),
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "truth_contract": {
            "uses_only_immutable_pre_waking_binding": True,
            "retroactive_backfill": "FORBIDDEN",
            "existing_waking_confirmation_mutated": False,
            "shadow_only_until_prospective_validation": True,
        },
        "counts": counts,
        "targets": rows,
    }
    _write(data / "waking-pre-t0-confirmation.json", payload)
    return payload


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
