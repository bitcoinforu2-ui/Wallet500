from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

DATA = Path("data")
OUTPUT = DATA / "social-intelligence-v2.json"
INDEX_SOURCES = {"telegram_index", "farcaster_index", "discord_index", "threads_index", "bluesky_index", "mesh_index"}
EXACT_ATTRS = {"EXACT_CONTRACT", "EXACT_PAIR"}


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _scan_map(payload: dict) -> dict[str, dict]:
    return {
        str(x.get("token_address")): x
        for x in (payload.get("targets") or [])
        if isinstance(x, dict) and x.get("token_address")
    }


def enrich(payload: dict, scan_payload: dict) -> dict:
    scans = _scan_map(scan_payload)
    total = 0
    tokens = 0
    sources = Counter()

    for row in payload.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        scan = scans.get(str(row.get("token_address") or "")) or {}
        context = [
            x for x in (scan.get("events") or [])
            if isinstance(x, dict)
            and str(x.get("source") or "") in INDEX_SOURCES
            and str(x.get("attribution") or "") in EXACT_ATTRS
            and x.get("context_only") is True
        ]
        if context:
            tokens += 1
        total += len(context)
        for event in context:
            sources[str(event.get("source") or "mesh_index")] += 1

        coverage = row.get("coverage") or {}
        coverage["mesh_indexed_exact_context_events"] = len(context)
        coverage["mesh_indexed_exact_context_sources"] = sorted({
            str(x.get("source")) for x in context if x.get("source")
        })
        coverage["mesh_indexed_context_is_organic"] = False
        row["coverage"] = coverage

        reasons = [x for x in (row.get("reasons") or []) if not str(x).startswith("SOCIAL_MESH_INDEX_CONTEXT:")]
        if context:
            reasons.append(
                "SOCIAL_MESH_INDEX_CONTEXT:"
                + ",".join(sorted({str(x.get("source")) for x in context if x.get("source")}))
            )
        row["reasons"] = reasons

    counts = payload.get("counts") or {}
    counts["mesh_indexed_exact_context_events"] = total
    counts["mesh_tokens_with_indexed_exact_context"] = tokens
    counts["mesh_index_source_counts"] = dict(sources)
    payload["counts"] = counts

    truth = payload.get("truth_contract") or {}
    truth["mesh_public_index_is_context_only_not_organic"] = True
    truth["mesh_public_index_never_grants_kol_credit"] = True
    truth["mesh_public_index_zero_is_unknown_not_zero"] = True
    payload["truth_contract"] = truth
    return payload


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    payload = _load(data / OUTPUT.name, {})
    scan = _load(data / "social-source-scan.json", {})
    payload = enrich(payload, scan)
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({"counts": payload.get("counts") or {}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
