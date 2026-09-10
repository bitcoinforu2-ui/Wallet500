from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
EVENTS = DATA / "deep-intelligence-event-ledger.json"
EDGE = DATA / "deep-intelligence-edge.json"
OUT = DATA / "pre-catalyst-fingerprints.json"
REGISTRY = DATA / "pre-catalyst-fingerprint-registry.json"
MODE = "FORWARD_ONLY_PRE_CATALYST_FINGERPRINT_V1"
MAX_STEPS = 8


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _key(row: dict) -> str:
    chain = str(row.get("chain") or "").strip().lower()
    token = str(row.get("token_address") or "").strip()
    return f"{chain}:{token}" if chain and token else ""


def _event_time(row: dict) -> str:
    return str(row.get("published_at") or row.get("observed_at") or "")


def _compress(categories: list[str]) -> list[str]:
    out = []
    for category in categories:
        if not category:
            continue
        if not out or out[-1] != category:
            out.append(category)
    return out[-MAX_STEPS:]


def _fingerprint(sequence: list[str]) -> str:
    raw = ">".join(sequence)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] if raw else ""


def build(data_dir: Path = DATA) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    ledger = _load(data_dir / EVENTS.name, {})
    edge = _load(data_dir / EDGE.name, {})
    registry = _load(data_dir / REGISTRY.name, {})
    registry_items = dict(registry.get("fingerprints") or {}) if isinstance(registry, dict) else {}

    current_keys = {_key(x): x for x in (edge.get("candidates") or []) if isinstance(x, dict) and _key(x)}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in ledger.get("events") or []:
        if not isinstance(event, dict):
            continue
        k = _key(event)
        if k in current_keys:
            grouped[k].append(event)

    rows = []
    for k, candidate in current_keys.items():
        events = sorted(grouped.get(k, []), key=_event_time)
        sequence = _compress([str(x.get("category") or "") for x in events])
        fp = _fingerprint(sequence)
        transitions = [f"{a}>{b}" for a, b in zip(sequence, sequence[1:])]
        first = events[0] if events else {}
        latest = events[-1] if events else {}
        unique_sources = sorted({str(x.get("source") or "") for x in events if x.get("source")})
        row = {
            "chain": candidate.get("chain"),
            "symbol": candidate.get("symbol"),
            "token_address": candidate.get("token_address"),
            "pair_address": candidate.get("pair_address"),
            "edge_score": candidate.get("edge_score"),
            "edge_band": candidate.get("edge_band"),
            "sequence": sequence,
            "sequence_length": len(sequence),
            "fingerprint": fp or None,
            "transitions": transitions,
            "first_verified_micro_event_at": first.get("published_at") or first.get("observed_at"),
            "latest_verified_micro_event_at": latest.get("published_at") or latest.get("observed_at"),
            "unique_sources": unique_sources,
            "event_count": len(events),
            "forward_outcome": "PENDING",
            "production_effect": False,
        }
        rows.append(row)
        if fp:
            reg = dict(registry_items.get(fp) or {})
            if not reg:
                reg = {
                    "fingerprint": fp,
                    "sequence": sequence,
                    "first_seen_at": now,
                    "tokens_seen": [],
                    "outcomes": {"pending": 0, "real_alert": 0, "breakout": 0, "fade": 0, "failed_survival": 0},
                }
            tokens = list(reg.get("tokens_seen") or [])
            token_key = k
            if token_key not in tokens:
                tokens.append(token_key)
            reg["tokens_seen"] = tokens[-500:]
            reg["observation_count"] = len(tokens)
            reg["last_seen_at"] = now
            registry_items[fp] = reg

    transition_counts = Counter(t for row in rows for t in row.get("transitions") or [])
    fingerprint_counts = Counter(str(row.get("fingerprint")) for row in rows if row.get("fingerprint"))
    rows.sort(key=lambda x: (float(x.get("edge_score") or 0), x.get("sequence_length") or 0), reverse=True)

    registry_payload = {
        "version": 1,
        "mode": "IMMUTABLE_FORWARD_PATTERN_REGISTRY",
        "updated_at": now,
        "fingerprints": registry_items,
        "truth_contract": {
            "no_hindsight": True,
            "patterns_are_observed_before_outcomes_are_attached": True,
            "registry_never_changes_production_gate": True,
        },
    }
    _write(data_dir / REGISTRY.name, registry_payload)
    out = {
        "version": 1,
        "mode": MODE,
        "generated_at": now,
        "candidate_count": len(rows),
        "fingerprints": rows,
        "current_fingerprint_frequency": dict(fingerprint_counts),
        "current_transition_frequency": dict(transition_counts),
        "truth_contract": {
            "veteran_6_of_7_only_via_edge_input": True,
            "forward_only": True,
            "no_hindsight": True,
            "pattern_frequency_is_not_profit_probability": True,
            "production_effect": False,
            "automatic_buy": False,
        },
        "learning_plan": {
            "future_labels": ["REAL_ALERT", "BREAKOUT", "FADE", "FAILED_SURVIVAL"],
            "goal": "Estimate which pre-catalyst sequences repeatedly precede validated forward outcomes without weakening hard gates.",
        },
    }
    _write(data_dir / OUT.name, out)
    return out


def main() -> None:
    out = build(DATA)
    print(json.dumps({
        "candidate_count": out.get("candidate_count"),
        "leaders": [
            {"symbol": x.get("symbol"), "fingerprint": x.get("fingerprint"), "sequence": x.get("sequence")}
            for x in (out.get("fingerprints") or [])[:5]
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
