from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "social-neural-graph.json"
MODE = "RESEARCH_ONLY_SOCIAL_NEURAL_GRAPH_V1"

# Research seed set. Audience size is deliberately not used as a quality score.
NODES = {
    "elonmusk": {"tier": 0, "role": "CATALYST", "aliases": ["elonmusk", "elon musk"]},
    "cz_binance": {"tier": 0, "role": "CATALYST", "aliases": ["cz_binance", "changpeng zhao", "cz"]},
    "vitalikbuterin": {"tier": 0, "role": "CATALYST", "aliases": ["vitalikbuterin", "vitalik buterin"]},
    "saylor": {"tier": 0, "role": "CATALYST", "aliases": ["saylor", "michael saylor"]},
    "mario_nawfal": {"tier": 1, "role": "AMPLIFIER_HUB", "aliases": ["marionawfal", "mario nawfal"]},
    "altcoin_daily": {"tier": 1, "role": "RETAIL_DISTRIBUTION", "aliases": ["altcoindaily", "altcoin daily"]},
    "pomp": {"tier": 1, "role": "INSTITUTIONAL_BRIDGE", "aliases": ["apompliano", "anthony pompliano", "pomp"]},
    "planb": {"tier": 1, "role": "THESIS_ORIGINATOR", "aliases": ["100trillionusd", "planb"]},
    "raoul_pal": {"tier": 1, "role": "THESIS_ORIGINATOR", "aliases": ["raoulgmi", "raoul pal"]},
    "ben_cowen": {"tier": 1, "role": "QUANT_VALIDATION", "aliases": ["intocryptoverse", "benjamin cowen"]},
    "coin_bureau": {"tier": 1, "role": "RESEARCH_DISTRIBUTION", "aliases": ["coinbureau", "coin bureau"]},
    "scott_melker": {"tier": 1, "role": "AMPLIFIER_HUB", "aliases": ["scottmelker", "scott melker", "wolf of all streets"]},
    "ran_neuner": {"tier": 1, "role": "FAST_AMPLIFIER", "aliases": ["cryptomanran", "ran neuner", "crypto banter"]},
    "arthur_hayes": {"tier": 1, "role": "THESIS_ORIGINATOR", "aliases": ["cryptohayes", "arthur hayes"]},
}

# Publicly documented collaboration circles. They reduce independence credit; they do not prove coordination.
CLUSTERS = {
    "crypto_town_hall": {"mario_nawfal", "scott_melker", "ran_neuner"},
}


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def canonical_author(author: Any) -> str | None:
    a = str(author or "").strip().lower().lstrip("@").replace("_", " ")
    if not a:
        return None
    compact = a.replace(" ", "").replace("-", "")
    for key, meta in NODES.items():
        for alias in meta["aliases"]:
            b = alias.lower().lstrip("@").replace("_", " ")
            if a == b or compact == b.replace(" ", "").replace("-", ""):
                return key
    return None


def cluster_for(node: str) -> str:
    for name, members in CLUSTERS.items():
        if node in members:
            return name
    return f"independent:{node}"


def analyze_events(events: list[dict]) -> dict:
    verified = []
    for e in events:
        if not isinstance(e, dict) or e.get("attribution") not in {"EXACT_CONTRACT", "EXACT_PAIR"}:
            continue
        node = canonical_author(e.get("author"))
        ts = _dt(e.get("published_at") or e.get("observed_at"))
        if not node or not ts:
            continue
        verified.append((ts, node, e))
    verified.sort(key=lambda x: x[0])

    first = {}
    for ts, node, e in verified:
        first.setdefault(node, (ts, e))
    ordered = sorted(((ts, node, e) for node, (ts, e) in first.items()), key=lambda x: x[0])
    edges = []
    for i in range(len(ordered) - 1):
        t1, n1, _ = ordered[i]
        t2, n2, _ = ordered[i + 1]
        latency = max(0.0, (t2 - t1).total_seconds() / 60.0)
        same_cluster = cluster_for(n1) == cluster_for(n2)
        edges.append({"from": n1, "to": n2, "latency_minutes": round(latency, 2), "same_cluster": same_cluster})

    clusters = {cluster_for(node) for _, node, _ in ordered}
    tiers = {NODES[node]["tier"] for _, node, _ in ordered}
    independent = len(clusters)
    raw = len(ordered)
    # Cross-cluster and cross-tier propagation matters more than repeated voices in one known circle.
    cascade_score = min(100.0, independent * 22.0 + max(0, len(tiers) - 1) * 18.0 + len(edges) * 4.0)
    if raw and independent == 1:
        cascade_score = min(cascade_score, 28.0)
    return {
        "known_kol_mentions": raw,
        "independent_clusters": independent,
        "tiers_reached": sorted(tiers),
        "first_source": ordered[0][1] if ordered else None,
        "first_source_at": ordered[0][0].isoformat() if ordered else None,
        "edges": edges,
        "cascade_score": round(cascade_score, 1),
        "independence_ratio": round(independent / raw, 3) if raw else None,
    }


def build(data_dir: Path = DATA) -> dict:
    now = datetime.now(timezone.utc)
    scan = _load(data_dir / "social-source-scan.json", {})
    rows = []
    for target in scan.get("targets") or []:
        if not isinstance(target, dict) or not target.get("token_address"):
            continue
        graph = analyze_events(target.get("events") or [])
        rows.append({
            "token_address": target.get("token_address"),
            "symbol": target.get("symbol"),
            "pair_address": target.get("pair_address"),
            **graph,
        })
    rows.sort(key=lambda x: (x["cascade_score"], x["independent_clusters"]), reverse=True)
    return {
        "version": 1,
        "mode": MODE,
        "generated_at": now.isoformat(),
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "nodes": {k: {"tier": v["tier"], "role": v["role"]} for k, v in NODES.items()},
        "known_collaboration_clusters": {k: sorted(v) for k, v in CLUSTERS.items()},
        "truth_contract": {
            "social_mentions_are_not_organic_acceleration": True,
            "same_cluster_mentions_are_not_independent_confirmations": True,
            "collaboration_edge_does_not_imply_secret_coordination": True,
            "only_exact_contract_or_exact_pair_events_receive_graph_credit": True,
            "followers_do_not_equal_quality": True,
            "forward_outcomes_required_for_skill": True,
            "graph_never_overrides_identity_liquidity_security_or_pair_survival": True,
            "research_only_no_automatic_buy": True,
        },
        "tokens": rows,
    }


def run(data_dir: str | Path = "data") -> dict:
    d = Path(data_dir)
    payload = build(d)
    out = d / OUTPUT.name
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = run(DATA)
    print(json.dumps({"mode": payload["mode"], "tokens": len(payload["tokens"]), "output": str(OUTPUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
