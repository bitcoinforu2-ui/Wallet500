from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
ENVELOPE = DATA / "candidate-evidence-envelope.json"
PROBE = DATA / "revival-wallet-coverage-probe.json"
OUTPUT = DATA / "pending-confirmation-audit.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _family_status(row: dict, key: str) -> dict:
    fam = (row.get("families") or {}).get(key) or {}
    return {
        "verified": fam.get("verified") is True,
        "positive": fam.get("positive") is True,
        "status": fam.get("status"),
    }


def run() -> dict:
    envelope = _load(ENVELOPE)
    probe = _load(PROBE)
    probe_by = {
        str(x.get("token_address") or ""): x
        for x in (probe.get("tokens") or [])
        if isinstance(x, dict) and x.get("token_address")
    }
    unresolved = []
    counter = Counter()
    for row in envelope.get("candidates") or []:
        pending = sorted(str(x) for x in (row.get("pending_confirmations") or []))
        if not pending:
            continue
        for code in pending:
            counter[code] += 1
        token = str(row.get("token_address") or "")
        p = probe_by.get(token) or {}
        unresolved.append({
            "token_address": token,
            "symbol": row.get("symbol"),
            "pair_address": row.get("pair_address"),
            "status": row.get("status"),
            "discovery_tier": row.get("discovery_tier"),
            "pending_confirmations": pending,
            "verification_outcomes": row.get("verification_outcomes") or [],
            "holder_growth": _family_status(row, "holder_growth"),
            "wallet_accumulation": _family_status(row, "wallet_accumulation"),
            "smart_money": _family_status(row, "smart_money"),
            "cex_revival": _family_status(row, "cex_revival"),
            "social": _family_status(row, "social"),
            "pair_survival": _family_status(row, "pair_survival"),
            "broad_wallet_probe": {
                "present": bool(p),
                "pair_address": p.get("pair_address"),
                "coverage_verified": p.get("coverage_verified"),
                "target_mint_touched": p.get("target_mint_touched"),
                "unresolved_target_touch": p.get("unresolved_target_touch"),
                "resolved_signed_owner": p.get("resolved_signed_owner"),
                "status": p.get("status"),
                "evidence_age_seconds": p.get("evidence_age_seconds"),
            },
            "market": {
                "market_positive": (row.get("market") or {}).get("market_positive"),
                "liquidity_usd": (row.get("market") or {}).get("liquidity_usd"),
                "same_pair_status": ((row.get("families") or {}).get("pair_survival") or {}).get("status"),
            },
        })
    payload = {
        "version": 1,
        "mode": "RESEARCH_ONLY_PENDING_CONFIRMATION_AUDIT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_effect": False,
        "automatic_buy": False,
        "counts": dict(sorted(counter.items())),
        "unresolved_candidate_count": len(unresolved),
        "truth_contract": {
            "read_only_diagnostic": True,
            "changes_candidate_promotion": False,
            "changes_real_alert_gate": False,
            "exact_pair_identity_preserved": True,
        },
        "candidates": unresolved,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    p = run()
    print(json.dumps({"counts": p["counts"], "unresolved_candidate_count": p["unresolved_candidate_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
