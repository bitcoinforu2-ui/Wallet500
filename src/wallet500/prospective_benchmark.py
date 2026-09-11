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
    for key in ("alerts", "targets", "coins", "candidates"):
        v = payload.get(key)
        if isinstance(v, list): return [x for x in v if isinstance(x, dict)]
    return []


def _key(row: dict) -> str:
    chain = str(row.get("network") or row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or row.get("address") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or row.get("pair") or "").lower().strip()
    return f"{chain}|{token}|{pair}" if chain and token and pair else ""


def _iso(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception: return None


def run(data_dir: str | Path = "data", now: str | None = None) -> dict:
    data = Path(data_dir)
    generated = now or datetime.now(timezone.utc).isoformat()
    ledger_path = data / "prospective-benchmark-ledger.json"
    ledger = _load(ledger_path, {"version": VERSION, "mode": "RESEARCH_ONLY_PROSPECTIVE_NO_HINDSIGHT", "no_hindsight": True, "records": {}})
    if ledger.get("version") != VERSION or ledger.get("no_hindsight") is not True:
        raise RuntimeError("PROSPECTIVE_LEDGER_TRUTH_INVALID")
    records = ledger.setdefault("records", {})

    feeds = [
        ("WAKING", _load(data / "waking-confirmation-latest.json", {})),
        ("PRE_T0", _load(data / "waking-pre-t0-confirmation.json", {})),
        ("PRODUCTION", _load(data / "real-alerts.json", {})),
    ]
    for stage, payload in feeds:
        observed_at = payload.get("generated_at") or generated
        for row in _rows(payload):
            key = _key(row)
            if not key: continue  # fail closed: no exact pair identity, no cohort record
            rec = records.setdefault(key, {"identity": key, "first_seen_at": observed_at, "stages": {}, "immutable_first_observation": True})
            # First observation is immutable; later runs can append new stage first-seen only.
            rec.setdefault("stages", {}).setdefault(stage, {"first_seen_at": observed_at})

    progression = []
    dwell: dict[str, list[float]] = {"WAKING_TO_PRE_T0": [], "PRE_T0_TO_PRODUCTION": []}
    for key, rec in records.items():
        stages = rec.get("stages") or {}
        w, p, r = (_iso((stages.get(x) or {}).get("first_seen_at")) for x in ("WAKING", "PRE_T0", "PRODUCTION"))
        blockers = []
        if "WAKING" in stages and "PRE_T0" not in stages: blockers.append("WAITING_FOR_IMMUTABLE_PRE_T0_BINDING_OR_EVIDENCE")
        if "PRE_T0" in stages and "PRODUCTION" not in stages: blockers.append("RESEARCH_ONLY_NOT_PRODUCTION_VERIFIED")
        if w and p and p >= w: dwell["WAKING_TO_PRE_T0"].append((p-w).total_seconds()/60)
        if p and r and r >= p: dwell["PRE_T0_TO_PRODUCTION"].append((r-p).total_seconds()/60)
        progression.append({"identity": key, "highest_stage": next((s for s in reversed(STAGES) if s in stages), "DISCOVERED"), "blockers": blockers})

    def stats(xs: list[float]) -> dict:
        if not xs: return {"n": 0, "median_minutes": None, "p90_minutes": None}
        ys=sorted(xs); n=len(ys)
        return {"n": n, "median_minutes": round(ys[(n-1)//2],2), "p90_minutes": round(ys[min(n-1, int((n-1)*0.9))],2)}

    ledger["updated_at"] = generated
    ledger["production_effect"] = False
    ledger["automatic_buy"] = False
    _write(ledger_path, ledger)
    out = {"version": VERSION, "generated_at": generated, "mode": ledger["mode"], "no_hindsight": True, "production_effect": False, "counts": {"cohort": len(records), "waking": sum("WAKING" in (r.get("stages") or {}) for r in records.values()), "pre_t0": sum("PRE_T0" in (r.get("stages") or {}) for r in records.values()), "production": sum("PRODUCTION" in (r.get("stages") or {}) for r in records.values())}, "dwell": {k:stats(v) for k,v in dwell.items()}, "progression": progression}
    _write(data / "prospective-benchmark-latest.json", out)
    return out


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))

if __name__ == "__main__": main()
