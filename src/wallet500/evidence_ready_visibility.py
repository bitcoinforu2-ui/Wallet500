from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA = Path("data")


def _load(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _key(row: dict) -> tuple[str, str, str]:
    chain = str(row.get("chain") or row.get("network") or "").strip().lower()
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast"}:
        token = token.lower()
        pair = pair.lower()
    return chain, token, pair


def _is_ready(row: dict) -> bool:
    return bool(
        row.get("evidence_ready") is True
        or row.get("evidence_envelope_status") == "EVIDENCE_READY"
        or row.get("status") in {"EVIDENCE_READY", "EVIDENCE_READY_NOT_REAL_ALERT"}
    )


def _projection(row: dict) -> dict:
    truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
    out = {
        "symbol": row.get("symbol"),
        "chain": row.get("chain") or row.get("network"),
        "token_address": row.get("token_address") or row.get("token") or row.get("mint"),
        "pair_address": row.get("pair_address") or row.get("dex_pair_address"),
        "dex_url": row.get("dex_url"),
        "price_usd": market.get("price_usd"),
        "liquidity_usd": truth.get("execution_pool_liquidity_usd"),
        "execution_pool_liquidity_usd": truth.get("execution_pool_liquidity_usd"),
        "market_age_days": truth.get("market_age_days"),
        "market_age_verified": truth.get("market_age_verified_180d_plus") is True,
        "exact_identity_verified": truth.get("exact_identity_verified") is True,
        "exact_pair_verified": truth.get("exact_pair_verified") is True,
        "evidence_envelope_status": "EVIDENCE_READY",
        "evidence_ready": True,
        "evidence_positive_lanes": list(coverage.get("positive_independent_lanes") or []),
        "evidence_verified_lanes": list(coverage.get("verified_independent_lanes") or []),
        "evidence_positive_count": int(coverage.get("positive_independent_count") or 0),
        "evidence_verified_count": int(coverage.get("verified_independent_count") or 0),
        "status": "EVIDENCE_READY_NOT_REAL_ALERT",
        "radar_tier": "VERIFIED_WATCH",
        "actionable_research_alert": False,
        "production_effect": False,
        "automatic_buy": False,
        "visibility_source": "CANONICAL_EVIDENCE_ENVELOPE_PROJECTION",
    }
    for key in ("mintability_verified", "mintable", "mint_authority", "mintability_status", "mintability_checked_at"):
        if key in row:
            out[key] = row.get(key)
    return out


def repair(data_dir: Path = DATA) -> dict:
    """Materialize every canonical Evidence Ready token on a non-actionable research surface.

    REAL Alert's generic watch list is intentionally display-capped.  Canonical
    Evidence Ready truth must not disappear merely because a higher-priority watch
    row occupies that cap.  This repair creates a dedicated research-only surface
    from the already-sanitized canonical envelope and never changes production or
    alert eligibility.
    """
    envelope_path = data_dir / "candidate-evidence-envelope.json"
    real_path = data_dir / "real-alerts.json"
    envelope = _load(envelope_path, {})
    real = _load(real_path, {})
    if not isinstance(envelope, dict):
        envelope = {}
    if not isinstance(real, dict):
        real = {}

    canonical = [
        row for row in (envelope.get("candidates") or [])
        if isinstance(row, dict) and row.get("status") == "EVIDENCE_READY"
    ]
    canonical_by_key = {_key(row): row for row in canonical if all(_key(row))}

    visible = set()
    for surface in ("verified_watch", "evidence_ready", "dormant_no_activity"):
        for row in real.get(surface) or []:
            if isinstance(row, dict) and _is_ready(row):
                visible.add(_key(row))

    dedicated = [row for row in (real.get("evidence_ready") or []) if isinstance(row, dict) and _is_ready(row)]
    dedicated_keys = {_key(row) for row in dedicated}
    added = 0
    for key, row in canonical_by_key.items():
        if key in visible or key in dedicated_keys:
            continue
        dedicated.append(_projection(row))
        dedicated_keys.add(key)
        added += 1

    # Remove stale dedicated rows that are no longer canonical while preserving
    # only the current forward snapshot.
    dedicated = [row for row in dedicated if _key(row) in canonical_by_key]
    real["evidence_ready"] = dedicated
    counts = real.get("counts") if isinstance(real.get("counts"), dict) else {}
    counts["evidence_ready_research"] = len(canonical_by_key)
    real["counts"] = counts
    real["evidence_ready_visibility"] = {
        "version": 1,
        "status": "CANONICAL_RESEARCH_VISIBILITY_ENFORCED",
        "canonical_count": len(canonical_by_key),
        "dedicated_surface_count": len(dedicated),
        "materialized_missing_this_run": added,
        "production_effect": False,
        "automatic_buy": False,
    }
    _write(real_path, real)
    return real["evidence_ready_visibility"]
