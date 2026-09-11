from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import social_feed_scan_v5

DATA = Path("data")
OUTPUT = DATA / "six-of-seven-live-intelligence.json"
MODE = "VETERAN_6_OF_7_DEEP_LIVE_INTELLIGENCE_V1"


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("chain") or "").strip().lower(),
        str(row.get("token_address") or "").strip(),
        str(row.get("pair_address") or "").strip(),
    )


def select_six_of_seven(real: dict) -> list[dict]:
    """Return exact-pair veteran candidates that currently pass exactly 6/7 gates.

    The deep search is an intelligence escalation, never an alert bypass. Risk-blocked,
    unresolved identity/pair, or non-veteran rows are excluded.
    """
    rows = list(real.get("verified_watch") or [])
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if int(row.get("readiness_passed") or 0) != 6 or int(row.get("readiness_total") or 0) != 7:
            continue
        if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
            continue
        if row.get("market_age_verified") is not True:
            continue
        if str(row.get("radar_tier") or "") not in {"NEAR_ALERT", "VERIFIED_WATCH"}:
            continue
        risk_reasons = list(row.get("risk_reasons") or [])
        if risk_reasons:
            continue
        chain, token, pair = _key(row)
        if not chain or not token or not pair:
            continue
        item = dict(row)
        item["deep_live_trigger"] = "READINESS_6_OF_7"
        item["deep_live_missing_gate"] = (list(row.get("missing_gates") or []) or [None])[0]
        out.append(item)
    out.sort(key=lambda x: (float(x.get("signal_score") or 0), float(x.get("execution_pool_liquidity_usd") or 0)), reverse=True)
    return out


def _envelope_row(candidate: dict) -> dict:
    """Create a temporary research target understood by the mature social scanner."""
    return {
        "chain": candidate.get("chain"),
        "network": candidate.get("chain"),
        "token_address": candidate.get("token_address"),
        "pair_address": candidate.get("pair_address"),
        "symbol": candidate.get("symbol"),
        "status": "EVIDENCE_READY",
        "discovery_tier": "WAKING_EVIDENCE_READY",
        "market_age_verified": True,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "deep_live_priority": True,
        "adaptive_discovery": {"anomaly_score": float(candidate.get("signal_score") or 0)},
        "market": {"revival_score_verified": float(candidate.get("signal_score") or 0)},
    }


def _merge_priority_targets(envelope: dict, urgent: list[dict]) -> dict:
    existing = [x for x in (envelope.get("candidates") or []) if isinstance(x, dict)]
    urgent_rows = [_envelope_row(x) for x in urgent]
    urgent_keys = {_key(x) for x in urgent_rows}
    merged = urgent_rows + [x for x in existing if _key(x) not in urgent_keys]
    out = dict(envelope)
    out["candidates"] = merged
    return out


def _summarize_target(target: dict) -> dict:
    events = [x for x in (target.get("events") or []) if isinstance(x, dict)]
    exact = [x for x in events if str(x.get("attribution") or "") in {"EXACT_CONTRACT", "EXACT_PAIR"}]
    official = [x for x in events if str(x.get("attribution") or "") == "OFFICIAL_CHANNEL_CONTEXT"]
    context = [x for x in events if str(x.get("attribution") or "") == "NAME_SYMBOL_CONTEXT"]
    direct_sources = sorted({str(x.get("source") or "") for x in exact + official if x.get("source")})
    fresh_items = []
    for event in events:
        fresh_items.append({
            "source": event.get("source"),
            "author": event.get("author"),
            "published_at": event.get("published_at"),
            "attribution": event.get("attribution"),
            "text": str(event.get("text") or "")[:500],
            "url": event.get("url"),
        })
    return {
        "chain": target.get("network") or target.get("chain"),
        "symbol": target.get("symbol"),
        "name": target.get("name"),
        "token_address": target.get("token_address"),
        "pair_address": target.get("pair_address"),
        "exact_events": len(exact),
        "official_context_events": len(official),
        "name_symbol_context_events": len(context),
        "verified_direct_sources": direct_sources,
        "provider_status": list(target.get("provider_status") or []),
        "events": fresh_items[:80],
    }


def _truth_contract() -> dict:
    return {
        "focus": "VETERAN_COIN_REVIVAL_ONLY",
        "exact_token_and_pair_required": True,
        "risk_blocked_candidates_excluded": True,
        "symbol_or_name_only_context_never_promotes_gate": True,
        "exact_contract_pair_or_verified_official_context_required_for_evidence": True,
        "deep_live_search_never_bypasses_strong_decision_gate": True,
        "missing_provider_means_unknown_not_zero": True,
        "empty_current_set_must_publish_fresh_snapshot": True,
    }


def run(data_dir: str | Path = DATA) -> dict:
    data = Path(data_dir)
    now = datetime.now(timezone.utc).isoformat()
    real = _load(data / "real-alerts.json", {})
    urgent = select_six_of_seven(real)
    previous = _load(data / OUTPUT.name, {})

    if not urgent:
        payload = {
            "version": 1,
            "mode": MODE,
            "generated_at": now,
            "triggered": False,
            "trigger_rule": "EVERY_VERIFIED_VETERAN_CANDIDATE_AT_EXACTLY_6_OF_7_READINESS",
            "candidate_count": 0,
            "candidate_identities": [],
            "meaningful_changes": [],
            "targets": [],
            "snapshot_status": "CURRENT_EMPTY",
            "previous_generated_at": previous.get("generated_at") if isinstance(previous, dict) else None,
            "stale_snapshot_prevented": True,
            "production_effect": False,
            "automatic_buy": False,
            "truth_contract": _truth_contract(),
        }
        _write(data / OUTPUT.name, payload)
        return payload

    envelope_path = data / "candidate-evidence-envelope.json"
    original_text = envelope_path.read_text(encoding="utf-8") if envelope_path.exists() else None
    envelope = _load(envelope_path, {})
    _write(envelope_path, _merge_priority_targets(envelope, urgent))
    try:
        scan = social_feed_scan_v5.run(data)
    finally:
        if original_text is None:
            envelope_path.unlink(missing_ok=True)
        else:
            envelope_path.write_text(original_text, encoding="utf-8")

    wanted = {_key(x) for x in urgent}
    targets = [_summarize_target(x) for x in (scan.get("targets") or []) if isinstance(x, dict) and _key(x) in wanted]
    previous_by_key = {_key(x): x for x in (previous.get("targets") or []) if isinstance(x, dict)}
    changed = []
    for row in targets:
        before = previous_by_key.get(_key(row), {})
        delta_exact = int(row.get("exact_events") or 0) - int(before.get("exact_events") or 0)
        delta_official = int(row.get("official_context_events") or 0) - int(before.get("official_context_events") or 0)
        row["new_exact_events_since_previous_deep_scan"] = max(0, delta_exact)
        row["new_official_events_since_previous_deep_scan"] = max(0, delta_official)
        row["meaningful_new_live_intelligence"] = delta_exact > 0 or delta_official > 0
        if row["meaningful_new_live_intelligence"]:
            changed.append({
                "symbol": row.get("symbol"),
                "token_address": row.get("token_address"),
                "pair_address": row.get("pair_address"),
                "new_exact_events": max(0, delta_exact),
                "new_official_events": max(0, delta_official),
                "verified_direct_sources": row.get("verified_direct_sources"),
            })

    payload = {
        "version": 1,
        "mode": MODE,
        "generated_at": now,
        "triggered": True,
        "trigger_rule": "EVERY_VERIFIED_VETERAN_CANDIDATE_AT_EXACTLY_6_OF_7_READINESS",
        "candidate_count": len(urgent),
        "candidate_identities": [
            {
                "chain": x.get("chain"),
                "symbol": x.get("symbol"),
                "token_address": x.get("token_address"),
                "pair_address": x.get("pair_address"),
                "missing_gate": x.get("deep_live_missing_gate"),
                "readiness": "6/7",
            }
            for x in urgent
        ],
        "meaningful_changes": changed,
        "targets": targets,
        "snapshot_status": "CURRENT_ACTIVE",
        "stale_snapshot_prevented": True,
        "production_effect": False,
        "automatic_buy": False,
        "truth_contract": _truth_contract(),
    }
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "triggered": payload.get("triggered"),
        "candidate_count": payload.get("candidate_count"),
        "snapshot_status": payload.get("snapshot_status"),
        "meaningful_changes": payload.get("meaningful_changes", []),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
