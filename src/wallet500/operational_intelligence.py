from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "WALLET500_OPERATIONAL_INTELLIGENCE_V1"
RESEARCH_FILES = {
    "pre_t0": "revival-pre-t0-evidence.json",
    "waking_shadow": "waking-pre-t0-confirmation.json",
    "waking_live": "waking-confirmation-latest.json",
}
PRODUCTION_FILES = {"real_alerts": "real-alerts.json"}


def _load(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _dt(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(path)


def _identity(row: dict) -> tuple[str, str, str]:
    chain = str(row.get("network") or row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or row.get("address") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or row.get("pair") or "").lower().strip()
    return chain, token, pair


def _rows(payload: dict) -> list[dict]:
    for key in ("alerts", "targets", "coins", "candidates", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def build(data_dir: str | Path = "data", now: str | None = None) -> dict:
    data = Path(data_dir)
    generated = now or datetime.now(timezone.utc).isoformat()
    now_dt = _dt(generated) or datetime.now(timezone.utc)
    feeds: dict[str, dict] = {}
    findings: list[dict] = []
    identities: dict[tuple[str, str, str], list[str]] = {}

    for lane, name in {**RESEARCH_FILES, **PRODUCTION_FILES}.items():
        p = data / name
        payload = _load(p)
        stamp = _dt(payload.get("generated_at"))
        age = None if stamp is None else max(0.0, (now_dt - stamp).total_seconds() / 60.0)
        feeds[lane] = {
            "file": name,
            "present": p.exists(),
            "nonempty": p.exists() and p.stat().st_size > 0,
            "generated_at": payload.get("generated_at"),
            "age_minutes": None if age is None else round(age, 2),
            "version": payload.get("version"),
            "mode": payload.get("mode"),
            "no_hindsight": payload.get("no_hindsight"),
            "production_portfolio_impact": payload.get("production_portfolio_impact"),
            "count": len(_rows(payload)),
        }
        if not payload:
            findings.append({"severity": "CRITICAL", "code": "FEED_MISSING_OR_INVALID", "feed": lane})
        for row in _rows(payload):
            ident = _identity(row)
            if ident[1] and ident[2]:
                identities.setdefault(ident, []).append(lane)

    pre = _load(data / RESEARCH_FILES["pre_t0"])
    shadow = _load(data / RESEARCH_FILES["waking_shadow"])
    live = _load(data / RESEARCH_FILES["waking_live"])
    real = _load(data / PRODUCTION_FILES["real_alerts"])

    for lane, payload in (("pre_t0", pre), ("waking_shadow", shadow)):
        if payload and (payload.get("no_hindsight") is not True or payload.get("production_portfolio_impact") != "NONE" or payload.get("automatic_buy") is not False):
            findings.append({"severity": "CRITICAL", "code": "RESEARCH_PRODUCTION_SEPARATION_LOST", "feed": lane})

    live_t, shadow_t = _dt(live.get("generated_at")), _dt(shadow.get("generated_at"))
    if live_t and shadow_t and (live_t - shadow_t).total_seconds() > 30 * 60:
        findings.append({"severity": "CRITICAL", "code": "WAKING_SPLIT_STATE", "lag_minutes": round((live_t-shadow_t).total_seconds()/60, 2)})

    # Exact-pair guard: never collapse token identity across different pairs.
    token_pairs: dict[tuple[str, str], set[str]] = {}
    for chain, token, pair in identities:
        token_pairs.setdefault((chain, token), set()).add(pair)
    ambiguous = [{"chain": c, "token": t, "pairs": sorted(ps)} for (c, t), ps in token_pairs.items() if len(ps) > 1]
    if ambiguous:
        findings.append({"severity": "WARN", "code": "MULTI_PAIR_TOKEN_PRESENT", "count": len(ambiguous), "examples": ambiguous[:10]})

    # Production truth checks are observational only; thresholds are never modified.
    contract = real.get("truth_contract") or {}
    contract_text = json.dumps(contract, sort_keys=True).lower()
    if real and "50000" not in contract_text and "50k" not in contract_text:
        findings.append({"severity": "WARN", "code": "PRODUCTION_50K_CONTRACT_NOT_MACHINE_VISIBLE"})

    counts = {
        "critical": sum(x["severity"] == "CRITICAL" for x in findings),
        "warn": sum(x["severity"] == "WARN" for x in findings),
    }
    payload = {
        "version": VERSION,
        "generated_at": generated,
        "mode": "OBSERVABILITY_ONLY_NO_THRESHOLD_CHANGES",
        "no_hindsight": True,
        "production_effect": False,
        "feeds": feeds,
        "identity": {"exact_pair_key": "chain|token|pair", "ambiguous_token_count": len(ambiguous)},
        "counts": counts,
        "findings": findings,
        "snapshot_sha256": hashlib.sha256(json.dumps(feeds, sort_keys=True).encode()).hexdigest(),
    }
    _atomic_write(data / "operational-intelligence.json", payload)
    return payload


def main() -> None:
    print(json.dumps(build(), ensure_ascii=False))


if __name__ == "__main__":
    main()
