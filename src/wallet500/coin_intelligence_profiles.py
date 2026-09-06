from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA = Path("data")
LATEST = DATA / "coin-intelligence-profiles.json"
LEDGER = DATA / "coin-intelligence-profile-ledger.json"
ARCHIVE = DATA / "coin-intelligence-profile-archive.json"
DNA_LIBRARY = DATA / "coin-profile-dna-library.json"

MODE = "COIN_INTELLIGENCE_PROFILE_V1"
CONTRACT = "COIN_INTELLIGENCE_PROFILE_V1"
MAX_HOT_PROFILES = 5000
MAX_TIMELINE = 96
MAX_SNAPSHOTS = 48
MAX_ARCHIVE = 50000
MAX_ALIASES = 32
MAX_SOURCES = 64
MAX_PAIRS = 32

EVM_CHAINS = {
    "ethereum", "bsc", "arbitrum", "base", "optimism", "polygon", "avalanche",
    "fantom", "linea", "zksync", "mantle", "scroll", "blast",
}
CHAIN_ALIASES = {
    "eth": "ethereum",
    "ethereum-mainnet": "ethereum",
    "bnb": "bsc",
    "bnb-chain": "bsc",
    "binance-smart-chain": "bsc",
    "arb": "arbitrum",
    "arbitrum-one": "arbitrum",
    "sol": "solana",
}

NEGATIVE_WORDS = (
    "BLOCK", "REJECT", "FAIL", "DUMP", "RUG", "RISK", "DISTRIBUT", "SELLING",
    "EXIT", "CRASH", "LIQUIDITY_DROP", "QUARANTINE", "INVALID", "STALE",
)
POSITIVE_WORDS = (
    "PASS", "WINNER", "MOONSHOT", "ACCELERAT", "WAKING", "IGNITION",
    "CONFIRMED", "ACCUMULATION", "CONVICTION_BUY", "LISTING", "REVIVAL",
)

SOURCE_FILES = (
    "cross-source-correlation.json",
    "signal-intelligence.json",
    "signal-dna-ledger.json",
    "hybrid-token-profiles.json",
    "holder-cluster-gate.json",
    "candidate-evidence-envelope.json",
    "revival-1000-latest.json",
    "revival-radar.json",
    "revival-snapshots.json",
    "cex-revival-radar.json",
    "social-intelligence-v2.json",
    "cross-signal-fusion-v2.json",
    "real-alerts.json",
    "real-alert-10usd-summary.json",
    "rejected-outcome-report.json",
    "global-listing-ledger.json",
    "catalyst-wire-ledger.json",
    "external-alpha-events.json",
)

NUMERIC_KEYS = {
    "price_usd", "current_price_usd", "dex_price_usd", "reference_price",
    "market_cap_usd", "marketcap_usd",
    "liquidity_usd", "dex_pair_liquidity_usd", "execution_pool_liquidity_usd",
    "current_liquidity_usd", "volume_h1", "volume_h24", "volume_24h_usd",
    "dex_pair_volume_24h_usd", "price_change_h1", "price_change_h1_pct",
    "price_change_24h_pct", "change_24h_pct", "revival_score",
    "revival_score_verified", "cex_revival_score", "cex_score",
    "holder_growth_pct", "unique_buyers_change_pct", "wallet_accumulation_score",
    "social_acceleration_score", "social_acceleration", "volume_change_pct",
    "liquidity_change_pct", "buy_sell_ratio", "top1_pct", "top5_pct", "top10_pct",
    "adjusted_top1_pct", "adjusted_top5_pct", "adjusted_top10_pct",
    "cluster_pct", "largest_cluster_pct", "risk_score", "hybrid_score_raw",
    "hybrid_score_verified_normalized", "evidence_coverage_pct",
    "peak_return_pct", "return_pct", "tradable_peak_gain_since_reject_pct",
    "holder_acceleration", "unique_buyer_acceleration", "wallet_accumulation",
    "social_acceleration", "volume_acceleration", "liquidity_expansion",
    "cex_acceleration", "price_structure",
}

FACT_KEYS = {
    "status", "decision", "phase", "revival_phase", "wallet_intent",
    "confirmation_tier", "source_confirmation_count", "exchange_confirmation_count",
    "discovery_confirmation_multiplier", "sources_seen", "exchange_sources_seen",
    "source_categories_seen", "source_lanes_present", "strong_channels",
    "risk_reasons", "reasons", "blockers", "reject_reasons", "first_reject_reasons",
    "alert_eligible", "evidence_ready", "production_status", "risk_status",
    "holder_status", "pair_age_days", "market_age_days", "age_days",
    "identity_confidence", "learning_score", "probability_gain_100pct",
    "probability_gain_300pct", "probability_loss_50pct",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_chain(value: object) -> str:
    chain = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(chain, chain)


def _norm_token(value: object, chain: object) -> str:
    token = str(value or "").strip()
    c = _norm_chain(chain)
    if c in EVM_CHAINS or c == "evm_unknown" or token.startswith("0x"):
        return token.lower()
    return token


def _norm_pair(value: object, chain: object) -> str:
    pair = str(value or "").strip()
    return pair.lower() if _norm_chain(chain) in EVM_CHAINS else pair


def _parse_ts(value: object) -> datetime | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def _ts_text(value: object, fallback: str) -> str:
    dt = _parse_ts(value)
    return dt.isoformat() if dt else fallback


def _asset_key(chain: object, token: object) -> str:
    c = _norm_chain(chain)
    t = _norm_token(token, c)
    return f"{c}:{t}" if c and t else ""


def _identity(row: dict, default_chain: str = "") -> tuple[str, str, str]:
    chain = _norm_chain(
        row.get("chain") or row.get("network") or row.get("blockchain")
        or row.get("chain_id") or default_chain
    )
    token = (
        row.get("token_address") or row.get("token") or row.get("mint")
        or row.get("contract") or row.get("contract_address")
        or row.get("contractAddress") or row.get("address")
    )
    pair = (
        row.get("pair_address") or row.get("entry_pair_address")
        or row.get("dex_pair_address") or row.get("pairAddress")
        or row.get("execution_pair_address")
    )
    return chain, _norm_token(token, chain), _norm_pair(pair, chain)


def _safe_num(value: object) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _compact_value(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if isinstance(value, int) else round(value, 8)
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, list):
        out = []
        for x in value[:24]:
            v = _compact_value(x, depth + 1)
            if v is not None:
                out.append(v)
        return out
    if isinstance(value, dict):
        out = {}
        for k, v0 in list(value.items())[:80]:
            v = _compact_value(v0, depth + 1)
            if v is not None:
                out[str(k)[:100]] = v
        return out
    return str(value)[:300]


def _pick_timestamp(row: dict, fallback: str) -> str:
    for key in (
        "observed_at", "updated_at", "generated_at", "created_at", "timestamp",
        "first_seen_at", "last_seen_at", "t0_at",
    ):
        if row.get(key):
            return _ts_text(row.get(key), fallback)
    return fallback


def _pick_aliases(row: dict) -> dict[str, list[str]]:
    symbols = []
    names = []
    for k in ("symbol", "ticker"):
        v = str(row.get(k) or "").strip()
        if v and v.upper() != "UNKNOWN":
            symbols.append(v)
    for k in ("name", "token_name"):
        v = str(row.get(k) or "").strip()
        if v and v.upper() != "UNKNOWN":
            names.append(v)
    return {"symbols": symbols, "names": names}


def _extract_selected_facts(row: dict) -> dict:
    facts: dict[str, Any] = {}
    for key in NUMERIC_KEYS:
        if key in row:
            n = _safe_num(row.get(key))
            if n is not None:
                facts[key] = round(n, 8)
    for key in FACT_KEYS:
        if key in row and row.get(key) not in (None, "", [], {}):
            facts[key] = _compact_value(row.get(key))
    return facts


def _flatten_metric_facts(row: dict, depth: int = 0, prefix: str = "") -> dict:
    if depth > 3 or not isinstance(row, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in row.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if key in NUMERIC_KEYS:
            n = _safe_num(value)
            if n is not None:
                out[path] = round(n, 8)
        elif key in FACT_KEYS and value not in (None, "", [], {}):
            out[path] = _compact_value(value)
        elif isinstance(value, dict):
            out.update(_flatten_metric_facts(value, depth + 1, path))
    return out


def _classification(event_type: str, facts: dict) -> str:
    text = (event_type + " " + json.dumps(facts, sort_keys=True, ensure_ascii=False)).upper()
    if any(word in text for word in NEGATIVE_WORDS):
        return "NEGATIVE"
    if any(word in text for word in POSITIVE_WORDS):
        return "POSITIVE"
    return "NEUTRAL"


def _event_hash(obs: dict) -> str:
    stable = {
        "lane": obs.get("lane"),
        "source_owner": obs.get("source_owner"),
        "event_type": obs.get("event_type"),
        "pair_address": obs.get("pair_address"),
        "facts": obs.get("facts") or {},
    }
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _observation(
    *,
    chain: str,
    token: str,
    pair: str = "",
    symbol: str | None = None,
    name: str | None = None,
    observed_at: str,
    lane: str,
    source_owner: str,
    source_category: str,
    event_type: str,
    facts: dict | None = None,
    source_url: str | None = None,
    identity_confidence: str | None = None,
) -> dict:
    c = _norm_chain(chain)
    t = _norm_token(token, c)
    p = _norm_pair(pair, c)
    out = {
        "chain": c,
        "token": t,
        "pair_address": p or None,
        "symbol": symbol,
        "name": name,
        "observed_at": observed_at,
        "lane": lane,
        "source_owner": str(source_owner or lane).lower(),
        "source_category": source_category,
        "event_type": event_type,
        "facts": _compact_value(facts or {}),
        "source_url": source_url,
        "identity_confidence": identity_confidence or (
            "PROVISIONAL_EVM_ADDRESS_ONLY" if c == "evm_unknown" else "EXACT_CHAIN_CONTRACT"
        ),
    }
    out["classification"] = _classification(event_type, out["facts"])
    out["event_hash"] = _event_hash(out)
    return out


def _rows(payload: Any, preferred: Iterable[str] = ()) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in tuple(preferred) + (
        "candidates", "targets", "alerts", "coins", "tokens", "rows", "positions",
        "items", "profiles", "events", "observations", "false_negatives",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _generic_rows(path: Path, lane: str, category: str, preferred: Iterable[str] = ()) -> list[dict]:
    payload = _load(path, {})
    generated = _pick_timestamp(payload, _now()) if isinstance(payload, dict) else _now()
    out = []
    for row in _rows(payload, preferred):
        chain, token, pair = _identity(row)
        if not chain or not token:
            continue
        aliases = _pick_aliases(row)
        event_type = str(
            row.get("event_type") or row.get("status") or row.get("decision")
            or row.get("revival_phase") or lane
        )
        facts = _flatten_metric_facts(row)
        out.append(_observation(
            chain=chain,
            token=token,
            pair=pair,
            symbol=aliases["symbols"][0] if aliases["symbols"] else None,
            name=aliases["names"][0] if aliases["names"] else None,
            observed_at=_pick_timestamp(row, generated),
            lane=lane,
            source_owner=str(row.get("source_owner") or row.get("source") or lane),
            source_category=category,
            event_type=event_type,
            facts=facts,
            source_url=row.get("source_url") or row.get("url"),
            identity_confidence=row.get("identity_confidence"),
        ))
    return out


def _cross_source(path: Path) -> list[dict]:
    payload = _load(path, {})
    assets = payload.get("assets") if isinstance(payload, dict) else {}
    if not isinstance(assets, dict):
        return []
    generated = _pick_timestamp(payload, _now())
    out: list[dict] = []
    for asset in assets.values():
        if not isinstance(asset, dict):
            continue
        chain, token, pair = _identity(asset)
        if not chain or not token:
            continue
        summary_facts = {
            k: _compact_value(asset.get(k))
            for k in (
                "confirmation_tier", "source_confirmation_count", "exchange_confirmation_count",
                "surface_count", "event_count", "source_category_count", "sources_seen",
                "exchange_sources_seen", "source_categories_seen",
                "discovery_confirmation_multiplier", "source_first_seen_spread_seconds",
                "identity_confidence",
            )
            if asset.get(k) not in (None, "", [], {})
        }
        out.append(_observation(
            chain=chain, token=token, pair=pair,
            symbol=asset.get("symbol"), observed_at=str(asset.get("last_seen_any_source_at") or generated),
            lane="CROSS_SOURCE_CORRELATION", source_owner="wallet500-correlation",
            source_category="correlation", event_type=str(asset.get("confirmation_tier") or "CROSS_SOURCE"),
            facts=summary_facts, identity_confidence=asset.get("identity_confidence"),
        ))
        for evidence in asset.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            ec, et, ep = _identity(evidence, chain)
            if not ec or not et:
                continue
            efacts = {
                "source_id": evidence.get("source_id"),
                "source_kind": evidence.get("source_kind"),
                "lane": evidence.get("lane"),
            }
            out.append(_observation(
                chain=ec, token=et, pair=ep, symbol=evidence.get("symbol"),
                observed_at=str(evidence.get("last_seen_at") or evidence.get("first_seen_at") or generated),
                lane=str(evidence.get("lane") or "CROSS_SOURCE_EVIDENCE"),
                source_owner=str(evidence.get("source_owner") or "unknown"),
                source_category=str(evidence.get("source_category") or "external_evidence"),
                event_type=str(evidence.get("event_type") or "SOURCE_EVIDENCE"),
                facts=efacts, source_url=evidence.get("source_url"),
                identity_confidence=evidence.get("identity_resolution") or asset.get("identity_confidence"),
            ))
    return out


def _signal_dna(path: Path) -> list[dict]:
    payload = _load(path, {})
    generated = _pick_timestamp(payload, _now())
    out = []
    for row in _rows(payload, ("candidates",)):
        chain, token, pair = _identity(row)
        if not chain or not token:
            continue
        dna = row.get("signal_dna") if isinstance(row.get("signal_dna"), dict) else {}
        wallet = row.get("wallet_intent") if isinstance(row.get("wallet_intent"), dict) else {}
        phase = row.get("revival_phase") if isinstance(row.get("revival_phase"), dict) else {}
        ev = row.get("expected_value") if isinstance(row.get("expected_value"), dict) else {}
        facts = {
            "signal_dna": _compact_value(dna),
            "wallet_intent": _compact_value(wallet),
            "revival_phase": _compact_value(phase),
            "expected_value": _compact_value(ev),
            "source_lanes_present": _compact_value(row.get("source_lanes_present") or []),
            "production_safe_data": row.get("production_safe_data"),
            "data_health_status": row.get("data_health_status"),
        }
        out.append(_observation(
            chain=chain, token=token, pair=pair, symbol=row.get("symbol"),
            observed_at=_pick_timestamp(row, generated),
            lane="SIGNAL_INTELLIGENCE", source_owner="wallet500-signal-dna",
            source_category="learned_dna", event_type=str(phase.get("phase") or "SIGNAL_DNA_SNAPSHOT"),
            facts=facts,
        ))
    return out


def _signal_ledger(path: Path) -> list[dict]:
    payload = _load(path, {})
    records = payload.get("records") if isinstance(payload, dict) else []
    if not isinstance(records, list):
        return []
    out = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        chain, token, pair = _identity(rec)
        if not chain or not token:
            continue
        facts = {
            "immutable_t0": rec.get("immutable_t0"),
            "t0_price_usd": rec.get("t0_price_usd"),
            "t0_liquidity_usd": rec.get("t0_liquidity_usd"),
            "t0_signal_dna": _compact_value(rec.get("t0_signal_dna") or {}),
            "t0_wallet_intent": _compact_value(rec.get("t0_wallet_intent") or {}),
            "t0_revival_phase": _compact_value(rec.get("t0_revival_phase") or {}),
            "t0_expected_value": _compact_value(rec.get("t0_expected_value") or {}),
        }
        out.append(_observation(
            chain=chain, token=token, pair=pair, symbol=rec.get("symbol"),
            observed_at=_ts_text(rec.get("t0_at"), _now()), lane="SIGNAL_DNA_LEDGER",
            source_owner="wallet500-signal-dna", source_category="learned_dna",
            event_type="IMMUTABLE_T0_SIGNAL_DNA", facts=facts,
        ))
        for snap in (rec.get("observations") or [])[-24:]:
            if not isinstance(snap, dict):
                continue
            out.append(_observation(
                chain=chain, token=token, pair=pair, symbol=rec.get("symbol"),
                observed_at=_ts_text(snap.get("at"), _now()), lane="SIGNAL_DNA_LEDGER",
                source_owner="wallet500-signal-dna", source_category="learned_dna",
                event_type=str(snap.get("revival_phase") or "DNA_OBSERVATION"),
                facts=_compact_value(snap),
            ))
    return out


def _global_listing_ledger(path: Path) -> list[dict]:
    payload = _load(path, {})
    records = payload.get("records") if isinstance(payload, dict) else {}
    if not isinstance(records, dict):
        return []
    out = []
    for rec in records.values():
        if not isinstance(rec, dict):
            continue
        obs = rec.get("last_observation") or rec.get("first_observation") or {}
        if not isinstance(obs, dict):
            continue
        chain, token, pair = _identity(obs)
        if not chain or not token:
            continue
        out.append(_observation(
            chain=chain, token=token, pair=pair,
            observed_at=_ts_text(rec.get("last_seen_at") or obs.get("observed_at"), _now()),
            lane="GLOBAL_LISTING_INTELLIGENCE",
            source_owner=str(obs.get("source") or "listing"),
            source_category="exchange_or_launchpad",
            event_type=str(obs.get("stage") or "LISTING_DISCOVERY"),
            facts={
                "surface": obs.get("surface"),
                "first_seen_at": rec.get("first_seen_at"),
                "last_seen_at": rec.get("last_seen_at"),
            },
            source_url=obs.get("source_url"),
            identity_confidence="PROVISIONAL_EVM_ADDRESS_ONLY" if chain == "evm_unknown" else None,
        ))
    return out


def _catalyst_ledger(path: Path) -> list[dict]:
    payload = _load(path, {})
    events = payload.get("events") if isinstance(payload, dict) else {}
    if isinstance(events, list):
        events = {str(i): x for i, x in enumerate(events)}
    if not isinstance(events, dict):
        return []
    out = []
    for rec in events.values():
        if not isinstance(rec, dict):
            continue
        event = rec.get("event") if isinstance(rec.get("event"), dict) else rec
        chain, token, pair = _identity(event)
        if not chain or not token:
            continue
        out.append(_observation(
            chain=chain, token=token, pair=pair, symbol=event.get("symbol"),
            observed_at=_ts_text(rec.get("last_seen_at") or event.get("observed_at"), _now()),
            lane="CATALYST_WIRE",
            source_owner=str(event.get("source_owner") or event.get("source") or "catalyst"),
            source_category="official_catalyst",
            event_type=str(event.get("event_type") or "OFFICIAL_CATALYST"),
            facts=_extract_selected_facts(event),
            source_url=event.get("source_url") or event.get("source_surface_url"),
        ))
    return out


def _external_alpha(path: Path) -> list[dict]:
    payload = _load(path, [])
    if isinstance(payload, dict):
        rows = payload.get("events") or payload.get("records") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
    else:
        rows = payload
    if not isinstance(rows, list):
        return []
    out = []
    for raw in rows:
        rec = raw.get("event") if isinstance(raw, dict) and isinstance(raw.get("event"), dict) else raw
        if not isinstance(rec, dict):
            continue
        chain, token, pair = _identity(rec)
        if not chain or not token:
            continue
        out.append(_observation(
            chain=chain, token=token, pair=pair, symbol=rec.get("symbol"),
            observed_at=_pick_timestamp(rec, _now()), lane="EXTERNAL_ALPHA_INTEL",
            source_owner=str(rec.get("source_owner") or rec.get("source") or rec.get("agent") or "external-alpha"),
            source_category="external_alpha",
            event_type=str(rec.get("event_type") or rec.get("decision") or "EXTERNAL_ALPHA_OBSERVATION"),
            facts=_flatten_metric_facts(rec), source_url=rec.get("source_url") or rec.get("url"),
        ))
    return out


def _rejected_outcomes(path: Path) -> list[dict]:
    payload = _load(path, {})
    rows = payload.get("false_negatives") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
        combined = {**identity, **row}
        chain, token, pair = _identity(combined)
        if not chain or not token:
            continue
        out.append(_observation(
            chain=chain, token=token, pair=pair, symbol=row.get("symbol"),
            observed_at=_pick_timestamp(row, _pick_timestamp(payload, _now())),
            lane="REJECTED_OUTCOME_TRACKER", source_owner="wallet500-outcomes",
            source_category="outcome", event_type="FALSE_NEGATIVE_OUTCOME",
            facts={
                "tradable_peak_gain_since_reject_pct": row.get("tradable_peak_gain_since_reject_pct"),
                "first_reject_source": row.get("first_reject_source"),
                "first_reject_reasons": row.get("first_reject_reasons"),
            },
        ))
    return out


def _collect(root: Path) -> list[dict]:
    adapters = [
        ("cross-source-correlation.json", _cross_source),
        ("signal-intelligence.json", _signal_dna),
        ("signal-dna-ledger.json", _signal_ledger),
        ("global-listing-ledger.json", _global_listing_ledger),
        ("catalyst-wire-ledger.json", _catalyst_ledger),
        ("external-alpha-events.json", _external_alpha),
        ("rejected-outcome-report.json", _rejected_outcomes),
    ]
    out: list[dict] = []
    for name, fn in adapters:
        out.extend(fn(root / name))
    generic_specs = {
        "hybrid-token-profiles.json": ("HYBRID_TOKEN_PROFILE", "hybrid_profile", ("profiles",)),
        "holder-cluster-gate.json": ("HOLDER_CLUSTER_GATE", "holder_risk", ("rows",)),
        "candidate-evidence-envelope.json": ("CANDIDATE_EVIDENCE", "evidence", ("candidates",)),
        "revival-1000-latest.json": ("REVIVAL_MARKET", "market", ("coins",)),
        "revival-radar.json": ("REVIVAL_RADAR", "market", ("alerts",)),
        "revival-snapshots.json": ("REVIVAL_SNAPSHOT", "market", ()),
        "cex-revival-radar.json": ("CEX_REVIVAL", "exchange", ("alerts",)),
        "social-intelligence-v2.json": ("SOCIAL_INTELLIGENCE", "social", ("tokens",)),
        "cross-signal-fusion-v2.json": ("CROSS_SIGNAL_FUSION", "fusion", ("tokens",)),
        "real-alerts.json": ("REAL_ALERTS", "alert", ("alerts",)),
        "real-alert-10usd-summary.json": ("REAL_ALERT_OUTCOMES", "outcome", ("positions",)),
    }
    for name, (lane, category, pref) in generic_specs.items():
        out.extend(_generic_rows(root / name, lane, category, pref))
    return _resolve_provisional_evm(out)


def _resolve_provisional_evm(observations: list[dict]) -> list[dict]:
    exact_by_addr: dict[str, set[str]] = {}
    for obs in observations:
        chain = _norm_chain(obs.get("chain"))
        token = _norm_token(obs.get("token"), chain)
        if chain in EVM_CHAINS and token.startswith("0x"):
            exact_by_addr.setdefault(token, set()).add(chain)
    resolved = []
    for original in observations:
        obs = dict(original)
        chain = _norm_chain(obs.get("chain"))
        token = _norm_token(obs.get("token"), chain)
        if chain == "evm_unknown":
            exact = exact_by_addr.get(token, set())
            if len(exact) == 1:
                obs["chain"] = next(iter(exact))
                obs["identity_confidence"] = "PROVISIONAL_EVM_ATTACHED_TO_UNIQUE_EXACT_CHAIN"
            elif len(exact) > 1:
                obs["identity_confidence"] = "PROVISIONAL_EVM_AMBIGUOUS_MULTICHAIN"
            else:
                obs["identity_confidence"] = "PROVISIONAL_EVM_ADDRESS_ONLY"
        resolved.append(obs)
    return resolved


def _merge_unique(old: list, new: Iterable[str], max_items: int) -> list:
    out = [str(x) for x in old if str(x).strip()]
    seen = set(out)
    for x in new:
        s = str(x or "").strip()
        if s and s not in seen:
            out.append(s)
            seen.add(s)
    return out[-max_items:]


def _timeline_merge(timeline: list[dict], obs: dict) -> tuple[list[dict], bool]:
    events = [dict(x) for x in timeline if isinstance(x, dict)]
    h = obs["event_hash"]
    for event in events:
        if event.get("event_hash") == h:
            event["last_seen_at"] = obs["observed_at"]
            event["seen_count"] = int(event.get("seen_count") or 1) + 1
            return events[-MAX_TIMELINE:], False
    events.append({
        "event_hash": h,
        "first_seen_at": obs["observed_at"],
        "last_seen_at": obs["observed_at"],
        "seen_count": 1,
        "lane": obs["lane"],
        "source_owner": obs["source_owner"],
        "source_category": obs["source_category"],
        "event_type": obs["event_type"],
        "classification": obs["classification"],
        "pair_address": obs.get("pair_address"),
        "source_url": obs.get("source_url"),
        "facts": obs.get("facts") or {},
    })
    events.sort(key=lambda x: str(x.get("first_seen_at") or ""))
    return events[-MAX_TIMELINE:], True


def _latest_channel(profile: dict, obs: dict) -> None:
    current = profile.setdefault("current", {})
    category = str(obs.get("source_category") or "other")
    old = current.get(category)
    old_ts = _parse_ts(old.get("observed_at")) if isinstance(old, dict) else None
    new_ts = _parse_ts(obs.get("observed_at"))
    if old is None or old_ts is None or (new_ts and new_ts >= old_ts):
        current[category] = {
            "observed_at": obs.get("observed_at"),
            "lane": obs.get("lane"),
            "source_owner": obs.get("source_owner"),
            "event_type": obs.get("event_type"),
            "classification": obs.get("classification"),
            "pair_address": obs.get("pair_address"),
            "facts": obs.get("facts") or {},
        }


def _extract_nested_number(data: Any, names: set[str], depth: int = 0) -> float | None:
    if depth > 5 or not isinstance(data, dict):
        return None
    vals = []
    for k, v in data.items():
        leaf = str(k).split(".")[-1]
        if leaf in names:
            n = _safe_num(v)
            if n is not None:
                vals.append(n)
        if isinstance(v, dict):
            n = _extract_nested_number(v, names, depth + 1)
            if n is not None:
                vals.append(n)
    return max(vals) if vals else None


def _current_facts(profile: dict) -> dict:
    out: dict[str, Any] = {}
    for channel in (profile.get("current") or {}).values():
        if isinstance(channel, dict):
            facts = channel.get("facts")
            if isinstance(facts, dict):
                out.update(facts)
    return out


def _feature(value: float | None, scale: float, *, invert: bool = False) -> float | None:
    if value is None:
        return None
    v = max(0.0, min(1.0, value / scale))
    return round(1.0 - v if invert else v, 6)


def _fingerprint(profile: dict) -> dict:
    current = profile.get("current") or {}
    facts = _current_facts(profile)
    cross = current.get("correlation") or {}
    cross_facts = cross.get("facts") or {}
    source_count = _safe_num(cross_facts.get("source_confirmation_count"))
    exchange_count = _safe_num(cross_facts.get("exchange_confirmation_count"))
    revival = _extract_nested_number(facts, {"revival_score", "revival_score_verified"})
    volume_accel = _extract_nested_number(facts, {"volume_acceleration", "volume_change_pct", "volume_clock_ratio"})
    liquidity = _extract_nested_number(facts, {"liquidity_usd", "dex_pair_liquidity_usd", "execution_pool_liquidity_usd"})
    holder_top10 = _extract_nested_number(facts, {"adjusted_top10_pct", "top10_pct"})
    wallet_acc = _extract_nested_number(facts, {"wallet_accumulation", "wallet_accumulation_score", "smart_money_score"})
    social_acc = _extract_nested_number(facts, {"social_acceleration", "social_acceleration_score", "organic_acceleration_score"})
    cex = _extract_nested_number(facts, {"cex_acceleration", "cex_revival_score", "cex_score"})
    price_structure = _extract_nested_number(facts, {"price_structure"})
    risk = _extract_nested_number(facts, {"risk_score"})
    dimensions = {
        "source_confirmation": _feature(source_count, 5),
        "exchange_confirmation": _feature(exchange_count, 4),
        "revival_strength": _feature(revival, 100),
        "volume_acceleration": _feature(volume_accel, 150),
        "liquidity_depth": None if liquidity is None else round(max(0.0, min(1.0, math.log10(max(1.0, liquidity)) / 7.0)), 6),
        "holder_safety": _feature(holder_top10, 100, invert=True),
        "wallet_accumulation": _feature(wallet_acc, 100 if (wallet_acc or 0) > 1 else 1),
        "social_acceleration": _feature(social_acc, 100 if (social_acc or 0) > 1 else 1),
        "cex_acceleration": _feature(cex, 100 if (cex or 0) > 1 else 1),
        "price_structure": _feature(price_structure, 1 if (price_structure or 0) <= 1 else 100),
        "risk_inverse": _feature(risk, 100, invert=True),
        "evidence_density": _feature(float(len(current)), 10),
    }
    observed = {k: v for k, v in dimensions.items() if v is not None}
    return {
        "dimensions": dimensions,
        "feature_coverage_count": len(observed),
        "feature_coverage_ratio": round(len(observed) / len(dimensions), 6),
        "truth_rule": "MISSING_DIMENSIONS_REMAIN_UNOBSERVED",
    }


def _outcome_summary(profile: dict) -> dict:
    returns = []
    peaks = []
    labels = []
    for event in profile.get("timeline") or []:
        facts = event.get("facts") if isinstance(event, dict) else {}
        if not isinstance(facts, dict):
            continue
        text = (str(event.get("event_type") or "") + " " + json.dumps(facts, ensure_ascii=False)).upper()
        if "MOONSHOT" in text:
            labels.append("MOONSHOT")
        elif "WINNER" in text:
            labels.append("WINNER")
        elif any(x in text for x in ("DUMP", "LOSS", "FAILED SURVIVAL")):
            labels.append("LOSS")
        r = _extract_nested_number(facts, {"return_pct"})
        p = _extract_nested_number(facts, {"peak_return_pct", "tradable_peak_gain_since_reject_pct"})
        if r is not None:
            returns.append(r)
        if p is not None:
            peaks.append(p)
    best = max(peaks + returns) if (peaks or returns) else None
    latest = returns[-1] if returns else None
    if "MOONSHOT" in labels or (best is not None and best >= 1000):
        label = "MOONSHOT"
    elif "WINNER" in labels or (best is not None and best >= 100):
        label = "WINNER"
    elif "LOSS" in labels or (latest is not None and latest <= -50):
        label = "LOSS"
    else:
        label = "UNLABELED"
    return {
        "label": label,
        "best_observed_return_pct": round(best, 6) if best is not None else None,
        "latest_observed_return_pct": round(latest, 6) if latest is not None else None,
        "research_only": True,
    }


def _new_profile(key: str, obs: dict) -> dict:
    now = obs["observed_at"]
    return {
        "profile_id": key,
        "chain": obs["chain"],
        "token_address": obs["token"],
        "identity_confidence": obs.get("identity_confidence"),
        "first_seen_at": now,
        "last_seen_at": now,
        "symbols": [],
        "names": [],
        "pairs_seen": [],
        "sources_seen": [],
        "source_categories_seen": [],
        "lanes_seen": [],
        "timeline": [],
        "snapshots": [],
        "current": {},
        "stats": {
            "material_events": 0,
            "positive_events": 0,
            "negative_events": 0,
            "neutral_events": 0,
        },
        "production_effect": "NONE_RESEARCH_PROFILE_ONLY",
    }


def _apply(profile: dict, obs: dict) -> None:
    profile["last_seen_at"] = max(str(profile.get("last_seen_at") or ""), str(obs.get("observed_at") or ""))
    if obs.get("identity_confidence"):
        if str(profile.get("identity_confidence") or "").startswith("PROVISIONAL") and str(obs["identity_confidence"]).startswith("EXACT"):
            profile["identity_confidence"] = obs["identity_confidence"]
        elif not profile.get("identity_confidence"):
            profile["identity_confidence"] = obs["identity_confidence"]
    profile["symbols"] = _merge_unique(profile.get("symbols") or [], [obs.get("symbol")], MAX_ALIASES)
    profile["names"] = _merge_unique(profile.get("names") or [], [obs.get("name")], MAX_ALIASES)
    profile["pairs_seen"] = _merge_unique(profile.get("pairs_seen") or [], [obs.get("pair_address")], MAX_PAIRS)
    profile["sources_seen"] = _merge_unique(profile.get("sources_seen") or [], [obs.get("source_owner")], MAX_SOURCES)
    profile["source_categories_seen"] = _merge_unique(profile.get("source_categories_seen") or [], [obs.get("source_category")], MAX_SOURCES)
    profile["lanes_seen"] = _merge_unique(profile.get("lanes_seen") or [], [obs.get("lane")], MAX_SOURCES)
    timeline, added = _timeline_merge(profile.get("timeline") or [], obs)
    profile["timeline"] = timeline
    _latest_channel(profile, obs)
    if added:
        stats = profile.setdefault("stats", {})
        stats["material_events"] = int(stats.get("material_events") or 0) + 1
        k = obs.get("classification", "NEUTRAL").lower() + "_events"
        stats[k] = int(stats.get(k) or 0) + 1


def _snapshot(profile: dict, at: str) -> None:
    fp = _fingerprint(profile)
    outcome = _outcome_summary(profile)
    snapshot = {
        "at": at,
        "fingerprint": fp,
        "outcome": outcome,
        "source_count": len(profile.get("sources_seen") or []),
        "lane_count": len(profile.get("lanes_seen") or []),
        "pair_count": len(profile.get("pairs_seen") or []),
    }
    snaps = [x for x in (profile.get("snapshots") or []) if isinstance(x, dict)]
    stable = json.dumps({k: snapshot[k] for k in ("fingerprint", "outcome", "source_count", "lane_count", "pair_count")}, sort_keys=True)
    prev = None
    if snaps:
        prev = json.dumps({k: snaps[-1].get(k) for k in ("fingerprint", "outcome", "source_count", "lane_count", "pair_count")}, sort_keys=True)
    if stable != prev:
        snaps.append(snapshot)
    profile["snapshots"] = snaps[-MAX_SNAPSHOTS:]
    profile["fingerprint"] = fp
    profile["outcome"] = outcome
    profile["evidence_summary"] = {
        "distinct_source_owners": len(profile.get("sources_seen") or []),
        "distinct_source_categories": len(profile.get("source_categories_seen") or []),
        "distinct_lanes": len(profile.get("lanes_seen") or []),
        "pairs_seen": len(profile.get("pairs_seen") or []),
        "material_events": int((profile.get("stats") or {}).get("material_events") or 0),
        "positive_events": int((profile.get("stats") or {}).get("positive_events") or 0),
        "negative_events": int((profile.get("stats") or {}).get("negative_events") or 0),
        "neutral_events": int((profile.get("stats") or {}).get("neutral_events") or 0),
    }


def _archive_entry(profile: dict) -> dict:
    return {
        "profile_id": profile.get("profile_id"),
        "chain": profile.get("chain"),
        "token_address": profile.get("token_address"),
        "symbols": (profile.get("symbols") or [])[-5:],
        "names": (profile.get("names") or [])[-3:],
        "first_seen_at": profile.get("first_seen_at"),
        "last_seen_at": profile.get("last_seen_at"),
        "fingerprint": profile.get("fingerprint"),
        "outcome": profile.get("outcome"),
        "evidence_summary": profile.get("evidence_summary"),
        "archived_from_hot_profile": True,
    }


def _sort_profiles(profiles: dict[str, dict]) -> list[tuple[str, dict]]:
    return sorted(profiles.items(), key=lambda kv: str(kv[1].get("last_seen_at") or ""), reverse=True)


def build(root: Path = DATA, at: str | None = None) -> tuple[dict, dict, dict, dict]:
    at = at or _now()
    previous = _load(root / LEDGER.name, {"profiles": {}})
    profiles = previous.get("profiles") if isinstance(previous, dict) else {}
    if not isinstance(profiles, dict):
        profiles = {}
    profiles = {str(k): dict(v) for k, v in profiles.items() if isinstance(v, dict)}
    observations = _collect(root)

    for obs in sorted(observations, key=lambda x: str(x.get("observed_at") or "")):
        key = _asset_key(obs.get("chain"), obs.get("token"))
        if not key:
            continue
        profile = profiles.get(key)
        if profile is None:
            profile = _new_profile(key, obs)
            profiles[key] = profile
        _apply(profile, obs)

    for profile in profiles.values():
        _snapshot(profile, at)

    archive_payload = _load(root / ARCHIVE.name, {"entries": {}})
    archive = archive_payload.get("entries") if isinstance(archive_payload, dict) else {}
    if not isinstance(archive, dict):
        archive = {}

    ordered = _sort_profiles(profiles)
    hot = dict(ordered[:MAX_HOT_PROFILES])
    evicted = ordered[MAX_HOT_PROFILES:]
    for key, profile in evicted:
        archive[key] = _archive_entry(profile)
    if len(archive) > MAX_ARCHIVE:
        keep = sorted(archive.items(), key=lambda kv: str(kv[1].get("last_seen_at") or ""), reverse=True)[:MAX_ARCHIVE]
        archive = dict(keep)

    exact = sum(1 for p in hot.values() if str(p.get("identity_confidence") or "").startswith("EXACT"))
    provisional = len(hot) - exact
    multi_source = sum(1 for p in hot.values() if int((p.get("evidence_summary") or {}).get("distinct_source_owners") or 0) >= 2)
    with_negative = sum(1 for p in hot.values() if int((p.get("evidence_summary") or {}).get("negative_events") or 0) > 0)
    with_outcome = sum(1 for p in hot.values() if (p.get("outcome") or {}).get("label") != "UNLABELED")

    ledger = {
        "version": 1,
        "contract": CONTRACT,
        "updated_at": at,
        "policy": "EXACT_CHAIN_CONTRACT_PRIMARY_APPEND_MATERIAL_EVENTS_BOUNDED_HOT_HISTORY_COMPACT_ARCHIVE",
        "truth_contract": {
            "symbol_never_defines_identity": True,
            "exact_identity_key": "chain+contract_or_mint",
            "provisional_evm_never_cross_chain_merges": True,
            "negative_evidence_is_retained": True,
            "material_duplicate_events_are_deduplicated": True,
            "missing_fingerprint_dimensions_remain_unobserved": True,
            "profile_never_bypasses_production_gates": True,
            "automatic_trade": False,
        },
        "profiles": hot,
    }
    latest_profiles = [p for _, p in _sort_profiles(hot)]
    latest = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "generated_at": at,
        "automatic_trade": False,
        "production_change": False,
        "purpose": "Persistent cross-source coin intelligence dossiers for research, audit and future DNA comparison.",
        "counts": {
            "source_observations_ingested_this_build": len(observations),
            "hot_profiles": len(hot),
            "archived_profiles": len(archive),
            "exact_identity_profiles": exact,
            "provisional_identity_profiles": provisional,
            "multi_source_profiles": multi_source,
            "profiles_with_negative_evidence": with_negative,
            "profiles_with_outcomes": with_outcome,
        },
        "truth_contract": ledger["truth_contract"],
        "profiles": latest_profiles,
    }
    archive_out = {
        "version": 1,
        "updated_at": at,
        "policy": "COMPACT_COLD_PROFILE_SUMMARIES_RETAINED_FOR_FUTURE_DNA_RESEARCH",
        "entries": archive,
    }
    dna_entries = {}
    for key, profile in {**archive, **hot}.items():
        fp = profile.get("fingerprint")
        if not isinstance(fp, dict):
            continue
        dna_entries[key] = {
            "profile_id": key,
            "chain": profile.get("chain"),
            "token_address": profile.get("token_address"),
            "symbols": (profile.get("symbols") or [])[-5:],
            "first_seen_at": profile.get("first_seen_at"),
            "last_seen_at": profile.get("last_seen_at"),
            "fingerprint": fp,
            "outcome": profile.get("outcome") or {"label": "UNLABELED"},
            "research_only": True,
        }
    dna = {
        "version": 1,
        "updated_at": at,
        "mode": "COIN_PROFILE_DNA_LIBRARY_RESEARCH_ONLY_V1",
        "automatic_trade": False,
        "production_effect": "NONE",
        "similarity_use": "FUTURE_VALIDATED_RESEARCH_ONLY_UNTIL_HOLDOUT_EVIDENCE_EXISTS",
        "truth_contract": {
            "no_hindsight_promotion": True,
            "missing_dimensions_remain_unobserved": True,
            "outcomes_never_rewrite_historical_snapshots": True,
            "hard_gates_never_weaken_from_profile_similarity": True,
        },
        "counts": {
            "profiles": len(dna_entries),
            "outcome_labeled": sum((x.get("outcome") or {}).get("label") != "UNLABELED" for x in dna_entries.values()),
            "fingerprint_coverage_ge_50pct": sum(float((x.get("fingerprint") or {}).get("feature_coverage_ratio") or 0) >= 0.5 for x in dna_entries.values()),
        },
        "profiles": dna_entries,
    }
    return latest, ledger, archive_out, dna


def run(root: Path = DATA) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    latest, ledger, archive, dna = build(root)
    _write(root / LATEST.name, latest)
    _write(root / LEDGER.name, ledger)
    _write(root / ARCHIVE.name, archive)
    _write(root / DNA_LIBRARY.name, dna)
    return {
        "profiles": latest["counts"]["hot_profiles"],
        "archived": latest["counts"]["archived_profiles"],
        "multi_source": latest["counts"]["multi_source_profiles"],
        "with_negative_evidence": latest["counts"]["profiles_with_negative_evidence"],
        "dna_profiles": dna["counts"]["profiles"],
    }


if __name__ == "__main__":
    print("COIN_INTELLIGENCE_PROFILE_OK", json.dumps(run(), separators=(",", ":")))
