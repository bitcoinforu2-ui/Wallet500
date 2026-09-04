from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
LEDGER = DATA / "veteran-dna-forward-ledger.json"
SHADOW = DATA / "veteran-dna-shadow-eval.json"
OUT = DATA / "veteran-dna-context-coverage.json"
MODE = "VETERAN_DNA_CONTEXT_COVERAGE_V1"


def load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def pct(n: int, d: int):
    return round(100.0 * n / d, 2) if d else None


def present(value) -> bool:
    return value is not None and value != ""


def coverage(records: dict) -> dict:
    total = len(records)
    counts = Counter()
    age_sources = Counter()
    context_statuses = Counter()
    social_statuses = Counter()
    rows = []

    for key, rec in records.items():
        counts["market_t0"] += int(isinstance(rec.get("t0_features"), dict))
        counts["exact_pair"] += int(bool(rec.get("pair_address")))
        counts["veteran_age"] += int(rec.get("market_age_verified") is True and float(rec.get("market_age_min_days_at_t0") or 0) >= 180)
        age_sources[str(rec.get("market_age_evidence_source") or "MISSING")] += 1

        status = str(rec.get("t0_context_status") or "NO_CONTEXT_STATUS")
        context_statuses[status] += 1
        ctx = rec.get("t0_context") if isinstance(rec.get("t0_context"), dict) else None
        valid_ctx = bool(ctx and ctx.get("no_hindsight") is True and ctx.get("immutable_after_freeze") is True and float(ctx.get("freeze_lag_minutes") or 0) <= 5)
        counts["valid_t0_context"] += int(valid_ctx)

        revival = (ctx or {}).get("revival") if valid_ctx else None
        holder = (ctx or {}).get("holder_shadow") if valid_ctx else None
        social = (ctx or {}).get("organic_social") if valid_ctx else None
        kol = (ctx or {}).get("kol_convergence") if valid_ctx else None

        counts["revival_context"] += int(isinstance(revival, dict))
        counts["holder_shadow"] += int(isinstance(holder, dict))
        counts["holder_count"] += int(isinstance(holder, dict) and present(holder.get("holder_count_shadow")))
        counts["holder_concentration"] += int(isinstance(holder, dict) and any(present(holder.get(k)) for k in ("top1_pct", "top5_pct", "top10_pct", "top20_pct", "concentration_risk_score")))
        counts["organic_social_context"] += int(isinstance(social, dict))
        if isinstance(social, dict):
            social_statuses[str(social.get("status") or "UNKNOWN")] += 1
        counts["organic_social_numeric"] += int(isinstance(social, dict) and present(social.get("organic_acceleration_score")))
        counts["kol_context"] += int(isinstance(kol, dict))
        counts["kol_numeric"] += int(isinstance(kol, dict) and any(present(kol.get(k)) for k in ("independent_wallet_groups", "independent_sources", "wallet_count")))

        rows.append({
            "key": key,
            "token": rec.get("token_address"),
            "pair": rec.get("pair_address"),
            "context_status": status,
            "valid_t0_context": valid_ctx,
            "revival": isinstance(revival, dict),
            "holder_shadow": isinstance(holder, dict),
            "holder_count": isinstance(holder, dict) and present(holder.get("holder_count_shadow")),
            "holder_concentration": isinstance(holder, dict) and any(present(holder.get(k)) for k in ("top1_pct", "top5_pct", "top10_pct", "top20_pct", "concentration_risk_score")),
            "organic_social": isinstance(social, dict),
            "organic_social_numeric": isinstance(social, dict) and present(social.get("organic_acceleration_score")),
            "kol": isinstance(kol, dict),
            "kol_numeric": isinstance(kol, dict) and any(present(kol.get(k)) for k in ("independent_wallet_groups", "independent_sources", "wallet_count")),
        })

    fields = [
        "market_t0", "exact_pair", "veteran_age", "valid_t0_context", "revival_context",
        "holder_shadow", "holder_count", "holder_concentration",
        "organic_social_context", "organic_social_numeric", "kol_context", "kol_numeric",
    ]
    metrics = {name: {"n": int(counts[name]), "pct": pct(int(counts[name]), total)} for name in fields}

    actionable_bottlenecks = sorted(
        [
            {"feature": "HOLDER_COUNT_TIMESTAMP_SAFE", "coverage_n": counts["holder_count"], "coverage_pct": pct(counts["holder_count"], total)},
            {"feature": "ORGANIC_SOCIAL_NUMERIC", "coverage_n": counts["organic_social_numeric"], "coverage_pct": pct(counts["organic_social_numeric"], total)},
            {"feature": "KOL_NUMERIC", "coverage_n": counts["kol_numeric"], "coverage_pct": pct(counts["kol_numeric"], total)},
            {"feature": "HOLDER_CONCENTRATION_RISK_CONTEXT", "coverage_n": counts["holder_concentration"], "coverage_pct": pct(counts["holder_concentration"], total)},
        ],
        key=lambda x: (x["coverage_n"], x["feature"]),
    )

    return {
        "records": total,
        "metrics": metrics,
        "context_statuses": dict(context_statuses),
        "market_age_evidence_sources": dict(age_sources),
        "organic_social_statuses": dict(social_statuses),
        "bottlenecks_lowest_coverage_first": actionable_bottlenecks,
        "rows": rows,
    }


def main() -> None:
    ledger = load(LEDGER, {})
    if ledger.get("mode") != "VETERAN_DNA_FORWARD_NO_HINDSIGHT_V1":
        raise SystemExit("VETERAN_DNA_COVERAGE_LEDGER_CONTRACT_INVALID")
    cov = coverage(ledger.get("records") or {})
    shadow = load(SHADOW, {})
    payload = {
        "version": 1,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {
            "veteran_only": True,
            "exact_pair_only": True,
            "no_hindsight": True,
            "valid_context_requires_freeze_lag_minutes_lte": 5,
            "missing_context_never_imputed": True,
            "holder_shadow_is_risk_context_not_positive_growth_signal": True,
            "social_mentions_not_equal_organic_acceleration": True,
        },
        "coverage": cov,
        "checkpoint_quality": shadow.get("checkpoint_quality") or {},
        "status": "COVERAGE_AUDIT_ONLY_NO_PRODUCTION_IMPACT",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {
        "records": cov["records"],
        "metrics": cov["metrics"],
        "context_statuses": cov["context_statuses"],
        "bottlenecks": cov["bottlenecks_lowest_coverage_first"],
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
