from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import social_intelligence_v2 as intel

DATA = Path("data")
OUTPUT = DATA / "social-intelligence-v2.json"
MESH_SOURCES = {"telegram", "farcaster", "discord", "threads", "bluesky"}
ALL_DIRECT_SOURCES = {"x", "youtube", "reddit", "telegram", "farcaster", "discord", "threads", "bluesky"}
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


def _recompute_kol(exact_social: list[dict], reputation: dict[str, dict]) -> tuple[float, str, int]:
    independent_authors = {
        f"{x.get('source')}:{x.get('author')}"
        for x in exact_social
        if x.get("author")
    }
    independent_sources = {
        str(x.get("source"))
        for x in exact_social
        if x.get("source")
    }
    rep_scores = []
    rep_samples = 0
    for key in independent_authors:
        rep = reputation.get(key) or {}
        if rep.get("forward_reputation_score") is not None:
            rep_scores.append(intel._n(rep.get("forward_reputation_score")))
            rep_samples += int(rep.get("forward_sample_count") or 0)

    if rep_scores:
        score = min(
            100.0,
            sum(rep_scores) / len(rep_scores) * 0.7
            + min(30.0, len(independent_authors) * 6.0),
        )
        confidence = "MEASURED_FORWARD_HISTORY"
    else:
        score = min(
            45.0,
            len(independent_authors) * 8.0 + len(independent_sources) * 5.0,
        )
        confidence = "ATTENTION_ONLY_NO_FORWARD_REPUTATION"
    return round(score, 1), confidence, rep_samples


def _recompute_narrative(row: dict) -> None:
    scores = row.get("scores") or {}
    coverage = row.get("coverage") or {}
    availability = row.get("availability") or {}

    social_ok = bool(availability.get("social_momentum"))
    kol_ok = bool(availability.get("kol_quality"))
    news_ok = bool(availability.get("news_catalyst"))
    available = {"social": social_ok, "kol": kol_ok, "news": news_ok}
    weights = {"social": 45.0, "kol": 25.0, "news": 30.0}
    values = {
        "social": intel._n(scores.get("social_momentum"), 0.0),
        "kol": intel._n(scores.get("kol_quality"), 0.0),
        "news": intel._n(scores.get("news_catalyst"), 0.0),
    }
    denom = sum(weights[k] for k, ok in available.items() if ok)
    manipulation = intel._n(scores.get("hype_manipulation_risk"), 0.0)
    narrative = (
        sum(weights[k] * values[k] / 100.0 for k, ok in available.items() if ok)
        / denom
        * 100.0
        if denom
        else 0.0
    )
    narrative = max(0.0, min(100.0, narrative - manipulation * 0.25))
    scores["narrative"] = round(narrative, 1) if denom else None

    freshness = intel._n(coverage.get("freshness_score"), 0.0)
    coverage_pct = round(sum(1 for ok in available.values() if ok) / 3.0 * 100.0, 1)
    confidence = round(min(100.0, coverage_pct * 0.65 + freshness * 0.35), 1)
    coverage["score_pct"] = coverage_pct
    scores["confidence"] = confidence
    availability["narrative"] = bool(denom)
    availability["confidence"] = True

    row["scores"] = scores
    row["coverage"] = coverage
    row["availability"] = availability


def enrich(payload: dict, scan_payload: dict, influencer_payload: dict) -> dict:
    scans = _scan_map(scan_payload)
    reputation = intel._influencer_forward_reputation(influencer_payload)
    mesh_event_total = 0
    mesh_tokens = 0
    mesh_sources_seen = Counter()

    for row in payload.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        token = str(row.get("token_address") or "")
        scan = scans.get(token) or {}
        events = [x for x in (scan.get("events") or []) if isinstance(x, dict)]
        social = [
            x for x in events
            if str(x.get("source") or "") in ALL_DIRECT_SOURCES
        ]
        exact_social = [
            x for x in social
            if str(x.get("attribution") or "") in EXACT_ATTRS
        ]
        mesh_exact = [
            x for x in exact_social
            if str(x.get("source") or "") in MESH_SOURCES
        ]
        if mesh_exact:
            mesh_tokens += 1
        mesh_event_total += len(mesh_exact)
        for event in mesh_exact:
            mesh_sources_seen[str(event.get("source") or "")] += 1

        independent_authors = {
            f"{x.get('source')}:{x.get('author')}"
            for x in exact_social
            if x.get("author")
        }
        independent_sources = {
            str(x.get("source"))
            for x in exact_social
            if x.get("source")
        }

        coverage = row.get("coverage") or {}
        coverage["exact_social_events"] = len(exact_social)
        coverage["exact_contract_social_events"] = sum(
            1 for x in exact_social if x.get("attribution") == "EXACT_CONTRACT"
        )
        coverage["exact_pair_social_events"] = sum(
            1 for x in exact_social if x.get("attribution") == "EXACT_PAIR"
        )
        coverage["independent_authors"] = len(independent_authors)
        coverage["independent_sources"] = len(independent_sources)
        coverage["mesh_exact_social_events"] = len(mesh_exact)
        coverage["mesh_exact_sources"] = sorted({
            str(x.get("source"))
            for x in mesh_exact
            if x.get("source")
        })
        row["coverage"] = coverage

        availability = row.get("availability") or {}
        availability["kol_quality"] = bool(exact_social)
        row["availability"] = availability

        scores = row.get("scores") or {}
        if exact_social:
            kol, kol_conf, samples = _recompute_kol(exact_social, reputation)
            scores["kol_quality"] = kol
            coverage["forward_reputation_samples"] = samples
            row["kol_confidence"] = kol_conf
        else:
            scores["kol_quality"] = None
        row["scores"] = scores

        reasons = [
            x for x in (row.get("reasons") or [])
            if not str(x).startswith("INDEPENDENT_KOL_AUTHORS_")
        ]
        if len(independent_authors) >= 2:
            reasons.append(f"INDEPENDENT_KOL_AUTHORS_{len(independent_authors)}")
        if mesh_exact:
            reasons.append(
                "SOCIAL_MESH_EXACT:"
                + ",".join(sorted({
                    str(x.get("source"))
                    for x in mesh_exact
                    if x.get("source")
                }))
            )
        row["reasons"] = reasons

        _recompute_narrative(row)

    counts = payload.get("counts") or {}
    counts["mesh_exact_social_events"] = mesh_event_total
    counts["mesh_tokens_with_exact_social"] = mesh_tokens
    counts["mesh_source_event_counts"] = dict(mesh_sources_seen)
    counts["kol_quality_observed"] = sum(
        1 for x in (payload.get("tokens") or [])
        if isinstance(x, dict)
        and bool((x.get("availability") or {}).get("kol_quality"))
    )
    payload["counts"] = counts

    truth = payload.get("truth_contract") or {}
    truth.update({
        "social_mesh_sources_enabled": True,
        "mesh_name_symbol_context_is_not_organic": True,
        "mesh_exact_identity_required_for_kol_credit": True,
        "telegram_official_context_requires_author_match": True,
        "missing_mesh_provider_is_unknown_not_zero": True,
    })
    payload["truth_contract"] = truth
    payload["version"] = max(4, int(payload.get("version") or 0))
    payload["social_mesh_sources"] = sorted(MESH_SOURCES)
    payload["social_mesh_direct_sources"] = sorted(ALL_DIRECT_SOURCES)
    return payload


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    payload = _load(data / OUTPUT.name, {})
    scan_payload = _load(data / "social-source-scan.json", {})
    influencer_payload = _load(data / "social-influencer-ledger.json", {})
    payload = enrich(payload, scan_payload, influencer_payload)
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "counts": payload.get("counts"),
        "mesh_sources": payload.get("social_mesh_sources"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
