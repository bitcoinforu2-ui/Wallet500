from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

try:
    import resilient_http
except ImportError:  # package import in pytest / module mode
    from scripts import resilient_http

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/protocol-buyback-registry.json"
OUT = ROOT / "data/protocol-value-accrual-discovery.json"

OVERVIEW_URL = (
    "https://api.llama.fi/overview/fees"
    "?excludeTotalDataChart=true"
    "&excludeTotalDataChartBreakdown=true"
    "&dataType=dailyHoldersRevenue"
)
UA = "Wallet500-ValueAccrualScout/1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def norm_slug(value) -> str:
    return str(value or "").strip().lower()


def overview_rows(payload) -> list[dict]:
    """Normalize DefiLlama overview response without assuming one exact shape."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("protocols")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        rows = []
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            row = dict(value)
            row.setdefault("slug", key)
            rows.append(row)
        return rows
    return []


def registry_slug_index(registry: dict) -> dict[str, dict]:
    """Only exact declared slugs map discovery to an exact token identity."""
    index = {}
    for entry in registry.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("active") is not True:
            continue
        slugs = set()
        direct = norm_slug(entry.get("defillama_slug"))
        if direct:
            slugs.add(direct)
        sensor = entry.get("buyback_sensor")
        if isinstance(sensor, dict):
            slugs.add(norm_slug(sensor.get("defillama_fees_slug")))
            funding = sensor.get("funding_source")
            if isinstance(funding, dict):
                slugs.add(norm_slug(funding.get("slug")))
            for source in sensor.get("execution_sources") or []:
                if isinstance(source, dict):
                    slugs.add(norm_slug(source.get("slug")))
        for slug in {x for x in slugs if x}:
            index[slug] = entry
    return index


def row_slug(row: dict) -> str:
    for key in ("slug", "id", "name"):
        value = norm_slug(row.get(key))
        if value:
            return value
    return ""


def metric(row: dict, *names):
    for name in names:
        if name in row:
            parsed = num(row.get(name))
            if parsed is not None:
                return parsed
    return None


def score_row(row: dict) -> dict | None:
    total24 = metric(row, "total24h", "total24H", "holdersRevenue24h", "dailyHoldersRevenue")
    total7 = metric(row, "total7d", "total7D")
    total30 = metric(row, "total30d", "total30D")
    if total24 is None or total24 <= 0:
        return None

    avg7 = total7 / 7.0 if total7 is not None and total7 > 0 else None
    avg30 = total30 / 30.0 if total30 is not None and total30 > 0 else None
    ratio24_7 = total24 / avg7 if avg7 and avg7 > 0 else None
    ratio7_30 = avg7 / avg30 if avg7 and avg30 and avg30 > 0 else None

    score = 0.0
    reasons = []

    if total24 >= 25_000:
        score += 15
        reasons.append("HOLDER_VALUE_24H_25K_PLUS")
    if total24 >= 100_000:
        score += 10
        reasons.append("HOLDER_VALUE_24H_100K_PLUS")
    if total24 >= 500_000:
        score += 10
        reasons.append("HOLDER_VALUE_24H_500K_PLUS")
    if total24 >= 1_000_000:
        score += 10
        reasons.append("HOLDER_VALUE_24H_1M_PLUS")

    if ratio24_7 is not None and ratio24_7 >= 1.25:
        score += 15
        reasons.append(f"VALUE_ACCEL_24H_VS_7D_{ratio24_7:.2f}X")
    if ratio24_7 is not None and ratio24_7 >= 1.75:
        score += 10
    if ratio24_7 is not None and ratio24_7 >= 2.5:
        score += 10

    if ratio7_30 is not None and ratio7_30 >= 1.10:
        score += 10
        reasons.append(f"VALUE_ACCEL_7D_VS_30D_{ratio7_30:.2f}X")
    if ratio7_30 is not None and ratio7_30 >= 1.5:
        score += 10

    score = min(100.0, score)
    if score < 25:
        return None

    return {
        "slug": row_slug(row),
        "name": str(row.get("displayName") or row.get("name") or row.get("slug") or ""),
        "category": row.get("category"),
        "chains": row.get("chains") or [],
        "holder_value_24h_usd": round(total24, 2),
        "holder_value_7d_usd": round(total7, 2) if total7 is not None else None,
        "holder_value_30d_usd": round(total30, 2) if total30 is not None else None,
        "value_24h_vs_7d_avg_multiple": round(ratio24_7, 4) if ratio24_7 is not None else None,
        "value_7d_avg_vs_30d_avg_multiple": round(ratio7_30, 4) if ratio7_30 is not None else None,
        "discovery_score": round(score, 1),
        "reasons": reasons,
    }


def enrich_mapping(row: dict, mapping: dict[str, dict]) -> dict:
    slug = norm_slug(row.get("slug"))
    entry = mapping.get(slug)
    if not entry:
        return {
            **row,
            "registry_mapped": False,
            "identity_verified": False,
            "actionable": False,
            "status": "MECHANISM_AND_EXACT_IDENTITY_REQUIRED",
            "candidate_type": "VALUE_ACCRUAL_DISCOVERY",
            "telegram_eligible": False,
            "direct_buy_eligible": False,
            "mapping_rule": "EXACT_DECLARED_DEFILLAMA_SLUG_ONLY",
        }

    required = (
        str(entry.get("network") or "").strip(),
        str(entry.get("contract") or "").strip(),
        str(entry.get("pair") or "").strip(),
    )
    exact = all(required)
    return {
        **row,
        "registry_mapped": True,
        "registry_id": entry.get("id"),
        "protocol_name": entry.get("protocol_name"),
        "symbol": str(entry.get("symbol") or "").upper(),
        "network": entry.get("network"),
        "contract": entry.get("contract"),
        "pair": entry.get("pair"),
        "dex_url": entry.get("dex_url") or "",
        "identity_verified": exact,
        # This scout never creates a BUY or direct Unified candidate. A mapped
        # protocol is handled by protocol_buyback_radar after source verification.
        "actionable": False,
        "status": "MAPPED_TO_BUYBACK_RADAR" if exact else "EXACT_IDENTITY_INCOMPLETE",
        "candidate_type": "VALUE_ACCRUAL_DISCOVERY",
        "telegram_eligible": False,
        "direct_buy_eligible": False,
        "mapping_rule": "EXACT_DECLARED_DEFILLAMA_SLUG_ONLY",
    }


def main() -> int:
    registry = load(REGISTRY, {"entries": []})
    mapping = registry_slug_index(registry)

    try:
        payload = resilient_http.request_json(
            OVERVIEW_URL,
            timeout=20,
            attempts=4,
            cache_ttl=120,
            user_agent=UA,
        )
    except Exception as exc:
        out = {
            "version": 1,
            "generated_at": now_iso(),
            "mode": "GLOBAL_HOLDER_VALUE_ACCRUAL_DISCOVERY",
            "status": "SOURCE_UNAVAILABLE",
            "error": f"{type(exc).__name__}:{str(exc)[:180]}",
            "truth_contract": {
                "holder_value_accrual_is_not_automatically_buyback": True,
                "ticker_or_name_auto_mapping_forbidden": True,
                "no_direct_telegram": True,
                "no_direct_buy": True,
            },
            "discoveries": [],
        }
        OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"status": out["status"], "discoveries": 0}, ensure_ascii=False))
        return 0

    scored = []
    for raw in overview_rows(payload):
        candidate = score_row(raw)
        if candidate is not None:
            scored.append(enrich_mapping(candidate, mapping))

    scored.sort(
        key=lambda x: (
            -float(x.get("discovery_score") or 0),
            -float(x.get("holder_value_24h_usd") or 0),
            str(x.get("slug") or ""),
        )
    )
    mapped = [x for x in scored if x.get("registry_mapped") is True]
    unmapped = [x for x in scored if x.get("registry_mapped") is not True]

    out = {
        "version": 1,
        "generated_at": now_iso(),
        "mode": "GLOBAL_HOLDER_VALUE_ACCRUAL_DISCOVERY",
        "status": "OK",
        "source": "DefiLlama dailyHoldersRevenue overview",
        "source_data_type": "dailyHoldersRevenue",
        "registry_exact_slug_count": len(mapping),
        "discovery_count": len(scored),
        "mapped_count": len(mapped),
        "unmapped_research_count": len(unmapped),
        "truth_contract": {
            "holder_value_accrual_is_not_automatically_buyback": True,
            "unmapped_rows_require_mechanism_verification": True,
            "unmapped_rows_require_exact_chain_contract_pair": True,
            "ticker_or_name_auto_mapping_forbidden": True,
            "mapped_rows_still_require_buyback_radar_execution_or_funding_evidence": True,
            "no_direct_telegram": True,
            "no_direct_buy": True,
        },
        "discoveries": scored[:100],
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "discoveries": out["discovery_count"],
        "mapped": out["mapped_count"],
        "unmapped_research": out["unmapped_research_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
