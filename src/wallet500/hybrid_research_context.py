from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
HYBRID = DATA / "hybrid-token-profiles.json"
LIQUIDITY = DATA / "revival-liquidity-learning.json"
HISTORICAL_DNA = DATA / "revival-historical-dna.json"
WINNER_DNA = DATA / "winner-dna-study.json"
OUT = DATA / "hybrid-research-context.json"
QUEUE = DATA / "hybrid-catalyst-scan-queue.json"
LEDGER = DATA / "hybrid-catalyst-trigger-ledger.json"
MODE = "RESEARCH_ONLY_HYBRID_RESEARCH_CONTEXT_V1"
CONTRACT = "HYBRID_RESEARCH_CONTEXT_V1"


def _load(path: Path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now():
    return datetime.now(timezone.utc).isoformat()


def _liq_map(payload: dict) -> dict[str, dict]:
    out = {}
    if payload.get("mode") != "RESEARCH_ONLY_REVIVAL_LIQUIDITY_LEARNING_V1":
        return out
    for row in payload.get("current_signals") or []:
        token = str(row.get("token_address") or "")
        if token:
            out[token] = row
    return out


def _historical_map(payload: dict) -> dict:
    if payload.get("mode") != "RESEARCH_ONLY_REVIVAL_HISTORICAL_DNA_V1" or payload.get("network") != "solana":
        return {}
    return payload.get("archetypes") or {}


def _winner_gate(payload: dict) -> dict:
    solana = payload.get("solana_study") if isinstance(payload, dict) else None
    if isinstance(solana, dict):
        status = str(solana.get("status") or "INSUFFICIENT_BALANCED_SAMPLE")
        return {
            "status": status,
            "usable_for_context": status == "RESEARCH_READY",
            "winner_n": int(solana.get("winner_n") or 0),
            "control_n": int(solana.get("control_n") or 0),
            "rule": solana.get("label_rule"),
        }
    winners = int((payload or {}).get("winner_n") or 0)
    controls = int((payload or {}).get("control_n") or 0)
    return {
        "status": "BLOCKED_LEGACY_UNBALANCED_SAMPLE",
        "usable_for_context": False,
        "winner_n": winners,
        "control_n": controls,
        "rule": "Legacy Top-N study is blocked when it does not expose a balanced Solana winner/control cohort.",
    }


def _available_score(channel: dict, threshold: float) -> bool:
    return bool(channel.get("available") is True and _f(channel.get("score")) >= threshold)


def _current_archetypes(profile: dict, liq: dict | None) -> list[str]:
    out = []
    signal = str((liq or {}).get("research_signal") or "")
    if signal == "LIQ_LEADS":
        out.append("LIQ_LEADS")
    elif signal == "CO_MOVE_STRONG":
        out.append("CO_MOVE_UP")

    pair = ((profile.get("channels") or {}).get("liquidity_pair") or {})
    dev = pair.get("deviation") or {}
    liq_dev = (dev.get("liquidity") or {}).get("change_from_previous_pct")
    vol_ratio = (dev.get("pair_volume_24h") or {}).get("ratio_to_baseline")
    if liq_dev is not None and vol_ratio is not None and _f(liq_dev) >= 2 and _f(vol_ratio) >= 1.5:
        out.append("LIQ_PLUS_VOLUME")
    return list(dict.fromkeys(out))


def _historical_matches(archetypes: list[str], historical: dict) -> list[dict]:
    matches = []
    for name in archetypes:
        row = historical.get(name)
        if not isinstance(row, dict):
            matches.append({"archetype": name, "status": "NO_HISTORICAL_SAMPLE", "horizons": {}})
            continue
        horizons = row.get("horizons") or {}
        matches.append(
            {
                "archetype": name,
                "status": row.get("status") or "INSUFFICIENT_SAMPLE",
                "events_detected": int(row.get("events_detected") or 0),
                "horizons": {
                    k: {
                        "status": v.get("status"),
                        "sample_n": int(v.get("sample_n") or 0),
                        "unique_tokens": int(v.get("unique_tokens") or 0),
                        "median_return_pct": v.get("median_return_pct"),
                        "hit_10pct_rate": v.get("hit_10pct_rate"),
                        "hit_25pct_rate": v.get("hit_25pct_rate"),
                        "hit_50pct_rate": v.get("hit_50pct_rate"),
                    }
                    for k, v in horizons.items()
                    if isinstance(v, dict)
                },
            }
        )
    return matches


def _signal_families(profile: dict, liq: dict | None) -> list[str]:
    channels = profile.get("channels") or {}
    families = []
    if _available_score(channels.get("market") or {}, 55):
        families.append("MARKET")
    pair_strong = _available_score(channels.get("liquidity_pair") or {}, 55)
    flow_signal = str((liq or {}).get("research_signal") or "") in {"LIQ_LEADS", "CO_MOVE_STRONG"}
    if pair_strong or flow_signal:
        families.append("LIQUIDITY_FLOW")
    if _available_score(channels.get("holders") or {}, 60):
        families.append("HOLDERS")
    if _available_score(channels.get("wallets") or {}, 60):
        families.append("WALLETS")
    if _available_score(channels.get("social") or {}, 60):
        families.append("SOCIAL")
    if _available_score(channels.get("news") or {}, 60):
        families.append("NEWS")
    return families


def _trigger_families(families: list[str]) -> list[str]:
    # Social/news are the evidence the downstream catalyst scan is meant to discover,
    # so they never count as prerequisites for starting that scan.
    allowed = {"MARKET", "LIQUIDITY_FLOW", "HOLDERS", "WALLETS"}
    return [x for x in families if x in allowed]


def _scan_requested(profile: dict, trigger_families: list[str]) -> bool:
    identity = profile.get("identity") or {}
    if identity.get("exact_pair_verified") is not True:
        return False
    if not profile.get("baseline_ready"):
        return False
    if _f(profile.get("risk_score")) >= 35:
        return False
    return len(set(trigger_families)) >= 2


def _queue_lookup(old_queue: dict) -> dict[str, dict]:
    return {
        str(x.get("token_address")): x
        for x in (old_queue.get("queue") or [])
        if isinstance(x, dict) and x.get("token_address")
    }


def enrich_payload(
    hybrid: dict,
    liquidity: dict,
    historical_dna: dict,
    winner_dna: dict,
    old_queue: dict | None = None,
    old_ledger: dict | None = None,
    at: str | None = None,
):
    if hybrid.get("mode") != "RESEARCH_ONLY_HYBRID_TOKEN_PROFILE_V1" or hybrid.get("contract") != "HYBRID_TOKEN_PROFILE_V1":
        raise RuntimeError("HYBRID_BASE_CONTRACT_INVALID")
    if hybrid.get("network") != "solana":
        raise RuntimeError("HYBRID_BASE_NETWORK_INVALID")

    at = at or _now()
    old_queue = old_queue or {}
    old_ledger = old_ledger or {}
    liq_by_token = _liq_map(liquidity)
    hist = _historical_map(historical_dna)
    winner_gate = _winner_gate(winner_dna)
    old_by_token = _queue_lookup(old_queue)
    queue = []
    events = list(old_ledger.get("events") or [])
    known_event_keys = {str(x.get("event_key")) for x in events if isinstance(x, dict) and x.get("event_key")}
    attached = 0
    requested = 0
    historical_supported = 0

    for profile in hybrid.get("profiles") or []:
        token = str(profile.get("token_address") or "")
        liq = liq_by_token.get(token)
        archetypes = _current_archetypes(profile, liq)
        matches = _historical_matches(archetypes, hist)
        if any(x.get("status") == "RESEARCH_READY" for x in matches):
            historical_supported += 1
        families = _signal_families(profile, liq)
        trigger = _trigger_families(families)
        scan = _scan_requested(profile, trigger)
        identity = profile.get("identity") or {}
        signature = "+".join(sorted(set(trigger)))
        previous = old_by_token.get(token) or {}
        first_requested = None
        if scan:
            requested += 1
            if previous.get("trigger_signature") == signature and previous.get("first_requested_at"):
                first_requested = previous.get("first_requested_at")
            else:
                first_requested = at
            event_key = f"{token}:{signature}:{first_requested}"
            if event_key not in known_event_keys:
                events.append(
                    {
                        "event_key": event_key,
                        "token_address": token,
                        "symbol": profile.get("symbol"),
                        "name": profile.get("name"),
                        "pair_address": identity.get("dex_pair_address"),
                        "engine_trigger_at": first_requested,
                        "profile_observed_at": profile.get("observed_at"),
                        "trigger_families": sorted(set(trigger)),
                        "hybrid_status_at_trigger": profile.get("status"),
                        "hybrid_score_at_trigger": profile.get("hybrid_score_verified_normalized"),
                        "risk_score_at_trigger": profile.get("risk_score"),
                        "current_archetypes": archetypes,
                        "production_impact": "NONE",
                    }
                )
                known_event_keys.add(event_key)
            queue.append(
                {
                    "network": "solana",
                    "token_address": token,
                    "symbol": profile.get("symbol"),
                    "name": profile.get("name"),
                    "pair_address": identity.get("dex_pair_address"),
                    "first_requested_at": first_requested,
                    "latest_requested_at": at,
                    "trigger_signature": signature,
                    "trigger_families": sorted(set(trigger)),
                    "hybrid_status": profile.get("status"),
                    "hybrid_score_verified_normalized": profile.get("hybrid_score_verified_normalized"),
                    "risk_score": profile.get("risk_score"),
                    "current_archetypes": archetypes,
                    "lookup_contract": {
                        "primary_identity": "EXACT_SOLANA_MINT",
                        "secondary_terms": [profile.get("symbol"), profile.get("name")],
                        "secondary_terms_never_sufficient_for_contract_match": True,
                    },
                    "requested_source_classes": [
                        "OFFICIAL_PROJECT",
                        "CRYPTO_NEWS",
                        "X_TWITTER",
                        "REDDIT",
                        "YOUTUBE",
                        "TELEGRAM",
                        "DISCORD",
                        "GITHUB_PROJECT_ACTIVITY",
                    ],
                    "research_question": "Was a verified public catalyst visible before or after the Wallet500 engine trigger, and how long before the subsequent market move?",
                    "production_impact": "NONE",
                }
            )

        profile["research_context"] = {
            "contract": CONTRACT,
            "observed_at": at,
            "production_impact": "NONE",
            "liquidity_learning": {
                "available": liq is not None,
                "research_signal": (liq or {}).get("research_signal"),
                "baseline_at": (liq or {}).get("baseline_at"),
                "liquidity_change_30m_pct": (liq or {}).get("liquidity_change_30m_pct"),
                "price_change_30m_pct": (liq or {}).get("price_change_30m_pct"),
                "market_cap_change_30m_pct": (liq or {}).get("market_cap_change_30m_pct"),
                "liq_mcap_pct": (liq or {}).get("liq_mcap_pct"),
                "liq_mcap_ratio_change_30m_pct": (liq or {}).get("liq_mcap_ratio_change_30m_pct"),
            },
            "current_archetypes": archetypes,
            "historical_matches": matches,
            "winner_dna_gate": winner_gate,
            "independent_signal_families": families,
            "catalyst_scan": {
                "requested": scan,
                "first_requested_at": first_requested,
                "trigger_families": sorted(set(trigger)),
                "trigger_signature": signature if scan else None,
                "rule": "Requires >=2 independent pre-catalyst families among MARKET/LIQUIDITY_FLOW/HOLDERS/WALLETS, exact pair, baseline ready, risk <35.",
            },
            "promotion_rule": "Historical/social/news context has zero Hybrid Score effect until prospective validation proves incremental value.",
        }
        attached += 1

    queue.sort(key=lambda x: (_f(x.get("risk_score")), -_f(x.get("hybrid_score_verified_normalized"))))
    events = events[-5000:]
    hybrid["research_context_contract"] = {
        "version": 1,
        "contract": CONTRACT,
        "generated_at": at,
        "production_impact": "NONE",
        "no_hindsight": True,
        "historical_dna_source": historical_dna.get("mode"),
        "liquidity_learning_source": liquidity.get("mode"),
        "winner_dna_gate": winner_gate,
        "catalyst_trigger_rule": ">=2 INDEPENDENT PRE-CATALYST SIGNAL FAMILIES; SOCIAL/NEWS DO NOT COUNT AS PREREQUISITES",
    }

    summary = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "network": "solana",
        "generated_at": at,
        "production_impact": "NONE",
        "no_hindsight": True,
        "counts": {
            "profiles_attached": attached,
            "profiles_with_liquidity_learning": sum(1 for p in hybrid.get("profiles") or [] if (p.get("research_context") or {}).get("liquidity_learning", {}).get("available")),
            "profiles_with_research_ready_historical_match": historical_supported,
            "catalyst_scan_requested": requested,
            "trigger_ledger_events": len(events),
        },
        "winner_dna_gate": winner_gate,
        "historical_dna_counts": historical_dna.get("counts") or {},
        "rule": "Research context is explanatory/shadow data only and never changes Hybrid score or production portfolio state.",
    }
    queue_payload = {
        "version": 1,
        "mode": "RESEARCH_ONLY_CATALYST_SCAN_QUEUE_V1",
        "generated_at": at,
        "network": "solana",
        "production_impact": "NONE",
        "queue_count": len(queue),
        "queue": queue,
    }
    ledger_payload = {
        "version": 1,
        "mode": "IMMUTABLE_CATALYST_TRIGGER_LEDGER_V1",
        "updated_at": at,
        "network": "solana",
        "production_impact": "NONE",
        "events_count": len(events),
        "events": events,
    }
    return hybrid, summary, queue_payload, ledger_payload


def run() -> dict:
    hybrid = _load(HYBRID, {})
    liquidity = _load(LIQUIDITY, {})
    historical = _load(HISTORICAL_DNA, {})
    winner = _load(WINNER_DNA, {})
    old_queue = _load(QUEUE, {})
    old_ledger = _load(LEDGER, {})
    enriched, summary, queue, ledger = enrich_payload(hybrid, liquidity, historical, winner, old_queue, old_ledger)
    HYBRID.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    QUEUE.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
