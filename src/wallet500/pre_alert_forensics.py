from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MODE_SHADOW = "shadow"
MODE_ENFORCE = "enforce"
VALID_MODES = {MODE_SHADOW, MODE_ENFORCE}
DEFAULT_MAX_EVIDENCE_AGE_SECONDS = 40 * 60
DEFAULT_MAX_HISTORY = 96

EVM_CHAINS = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _parse_dt(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _f(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(row: dict[str, Any], *keys: str):
    """Return first non-None value; numeric zero is evidence, not missing data."""
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _norm(chain: object, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if str(chain or "").lower() in EVM_CHAINS else raw


def pair_key(row: dict[str, Any]) -> str:
    chain = str(row.get("chain") or "").strip().lower()
    token = _norm(chain, row.get("token_address") or row.get("token") or row.get("mint"))
    pair = _norm(chain, row.get("pair_address") or row.get("locked_pair_address"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def _rows(payload: Any, key: str = "rows") -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _evidence_fresh(checked_at: object, now: datetime, max_age_seconds: int) -> bool:
    dt = _parse_dt(checked_at)
    if not dt:
        return False
    age = (now - dt).total_seconds()
    return -120 <= age <= max_age_seconds


def _market_from_row(row: dict[str, Any], checked_at: object = None) -> dict[str, Any]:
    return {
        "source": "CANONICAL_DECISION_SNAPSHOT",
        "checked_at": checked_at or row.get("generated_at") or row.get("updated_at"),
        "complete": bool(
            row.get("exact_pair_verified") is True
            and _f(row.get("price_usd")) is not None
            and _f(_first_present(row, "execution_pool_liquidity_usd", "liquidity_usd")) is not None
        ),
        "price_usd": _f(row.get("price_usd")),
        "liquidity_usd": _f(_first_present(row, "execution_pool_liquidity_usd", "liquidity_usd")),
        "volume_h1_usd": _f(_first_present(row, "dex_volume_h1", "volume_h1")),
        "price_change_h1_pct": _f(_first_present(row, "price_change_h1_pct", "price_change_h1")),
        "price_change_h6_pct": _f(_first_present(row, "price_change_h6_pct", "price_change_h6")),
        "price_change_h24_pct": _f(_first_present(row, "price_change_h24_pct", "price_change_h24")),
        "buys_h1": int(row.get("buys_h1") or 0),
        "sells_h1": int(row.get("sells_h1") or 0),
    }


def _dexscreener_chain(chain: object) -> str:
    c = str(chain or "").strip().lower()
    return {"eth": "ethereum", "bnb": "bsc"}.get(c, c)


def fetch_exact_pair_market(row: dict[str, Any], timeout: float = 8.0) -> dict[str, Any] | None:
    chain = _dexscreener_chain(row.get("chain"))
    pair = str(row.get("pair_address") or "").strip()
    if not chain or not pair:
        return None
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair}"
    request = urllib.request.Request(url, headers={"User-Agent": "Wallet500/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    pairs = payload.get("pairs") if isinstance(payload, dict) else None
    if not isinstance(pairs, list):
        pair_obj = payload.get("pair") if isinstance(payload, dict) else None
        pairs = [pair_obj] if isinstance(pair_obj, dict) else []
    wanted = _norm(chain, pair)
    match = next(
        (
            x
            for x in pairs
            if isinstance(x, dict) and _norm(chain, x.get("pairAddress")) == wanted
        ),
        None,
    )
    if not match:
        return None
    liquidity = match.get("liquidity") if isinstance(match.get("liquidity"), dict) else {}
    volume = match.get("volume") if isinstance(match.get("volume"), dict) else {}
    changes = match.get("priceChange") if isinstance(match.get("priceChange"), dict) else {}
    txns = match.get("txns") if isinstance(match.get("txns"), dict) else {}
    h1 = txns.get("h1") if isinstance(txns.get("h1"), dict) else {}
    return {
        "source": "DEXSCREENER_EXACT_PAIR_LIVE",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "complete": _f(match.get("priceUsd")) is not None and _f(liquidity.get("usd")) is not None,
        "price_usd": _f(match.get("priceUsd")),
        "liquidity_usd": _f(liquidity.get("usd")),
        "volume_h1_usd": _f(volume.get("h1")),
        "price_change_h1_pct": _f(changes.get("h1")),
        "price_change_h6_pct": _f(changes.get("h6")),
        "price_change_h24_pct": _f(changes.get("h24")),
        "buys_h1": int(h1.get("buys") or 0),
        "sells_h1": int(h1.get("sells") or 0),
        "dex_id": match.get("dexId"),
        "pair_address": match.get("pairAddress"),
        "url": match.get("url"),
    }


def _holder_index(payload: Any) -> dict[str, dict[str, Any]]:
    return {pair_key(row): row for row in _rows(payload) if pair_key(row)}


def _registry_index(payload: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    wallet_map: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict):
        for row in payload.get("wallets") or []:
            if not isinstance(row, dict):
                continue
            wallet = str(row.get("wallet") or row.get("address") or "").strip()
            if wallet:
                wallet_map[wallet] = row
        bridges = [x for x in (payload.get("event_bridge") or []) if isinstance(x, dict)]
    else:
        bridges = []
    return wallet_map, bridges


def _wallet_candidate_index(payload: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return out
    for lane in ("solana", "evm"):
        for row in payload.get(lane) or []:
            if isinstance(row, dict) and pair_key(row):
                out[pair_key(row)] = row
    return out


def refresh_holder_evidence(row: dict[str, Any]) -> dict[str, Any] | None:
    """Run the existing exact-chain holder/cluster analyzer only for a near-send target."""
    try:
        from .holder_cluster_gate import analyze
        result = analyze(row)
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def refresh_wallet_evidence(row: dict[str, Any], signatures_limit: int = 12) -> dict[str, Any] | None:
    """Collect verified exact-pair signers for Smart Money overlap without inferring trade side."""
    try:
        from .wallet_candidate_discovery import (
            discover_evm_candidate_wallets,
            discover_solana_candidate_wallets,
        )
        chain = str(row.get("chain") or "").lower()
        candidate = dict(row)
        if candidate.get("exact_pair_verified") is True and candidate.get("pair_address"):
            candidate.setdefault("locked_pair_address", candidate.get("pair_address"))
            candidate.setdefault("pair_identity_locked", True)
        if chain == "solana":
            from .adapters.solana import SolanaAdapter
            from .config import Settings
            adapter = SolanaAdapter(Settings().solana_rpc_url)
            return discover_solana_candidate_wallets(adapter, candidate, signatures_limit)
        if chain in EVM_CHAINS:
            return discover_evm_candidate_wallets(candidate, signatures_limit)
    except Exception:
        return None
    return None


def smart_money_snapshot(
    row: dict[str, Any],
    wallet_evidence: dict[str, Any] | None,
    registry_payload: Any,
) -> dict[str, Any]:
    wallet_map, bridges = _registry_index(registry_payload)
    token = _norm(row.get("chain"), row.get("token_address") or row.get("token") or row.get("mint"))
    pair = _norm(row.get("chain"), row.get("pair_address"))
    recent_wallets = {
        str(x.get("address") or x.get("wallet") or "").strip()
        for x in ((wallet_evidence or {}).get("wallets") or [])
        if isinstance(x, dict) and x.get("verified") is True
    }
    qualified_recent = []
    for wallet in sorted(recent_wallets):
        reg = wallet_map.get(wallet) or {}
        tier = (reg.get("tier_current") or {}).get("tier") if isinstance(reg.get("tier_current"), dict) else None
        if tier in {"ELITE", "STRONG"}:
            qualified_recent.append({"wallet": wallet, "tier": tier})
    bridge_qualified: set[str] = set()
    for bridge in bridges:
        if _norm(row.get("chain"), bridge.get("token_address")) != token:
            continue
        if _norm(row.get("chain"), bridge.get("pair_address")) != pair:
            continue
        for item in bridge.get("wallets") or []:
            if not isinstance(item, dict) or item.get("eligible_to_influence_event") is not True:
                continue
            wallet = str(item.get("wallet") or "").strip()
            if wallet:
                bridge_qualified.add(wallet)
    returning = sorted(bridge_qualified & recent_wallets)
    if returning:
        status = "HISTORICALLY_QUALIFIED_RECENT_PAIR_TOUCH"
    elif qualified_recent:
        status = "QUALIFIED_RECENT_PAIR_TOUCH"
    elif bridge_qualified:
        status = "HISTORICALLY_QUALIFIED_NO_RECENT_TOUCH_OBSERVED"
    elif recent_wallets:
        status = "RECENT_SIGNERS_NO_QUALIFIED_SMART_MONEY_MATCH"
    else:
        status = "INSUFFICIENT_RECENT_WALLET_EVIDENCE"
    return {
        "status": status,
        "recent_verified_pair_signers": len(recent_wallets),
        "qualified_recent_signers": qualified_recent[:10],
        "historically_qualified_pre_event_buyers": len(bridge_qualified),
        "historically_qualified_recent_pair_touch": returning[:10],
        "side_inference": "NOT_CLAIMED_FROM_SIGNER_TOUCH_ALONE",
        "confidence": 0.9 if returning else (0.75 if qualified_recent or bridge_qualified else 0.35 if recent_wallets else 0.0),
    }


def _snapshot_from_evidence(
    now: datetime,
    holder: dict[str, Any] | None,
    market: dict[str, Any] | None,
    smart_money: dict[str, Any] | None,
) -> dict[str, Any]:
    owners: dict[str, float] = {}
    cex_pct = 0.0
    if isinstance(holder, dict):
        for h in holder.get("holders") or []:
            if not isinstance(h, dict) or h.get("excluded_from_whale_concentration"):
                continue
            owner = str(h.get("owner") or "").strip()
            pct = _f(h.get("pct"))
            if owner and pct is not None:
                owners[owner] = pct
        cex_pct = float(holder.get("cex_custody_pct") or 0.0)
    return {
        "at": now.isoformat(),
        "price_usd": (market or {}).get("price_usd"),
        "liquidity_usd": (market or {}).get("liquidity_usd"),
        "adjusted_top10_pct": (holder or {}).get("adjusted_real_top10_pct", (holder or {}).get("top10_pct")),
        "cex_custody_pct": cex_pct,
        "real_holder_pct": owners,
        "smart_money_status": (smart_money or {}).get("status"),
        "qualified_recent_signers": len((smart_money or {}).get("qualified_recent_signers") or []),
    }


def _history_reference(history: list[dict[str, Any]], now: datetime, hours: float) -> dict[str, Any] | None:
    target = now - timedelta(hours=hours)
    candidates = []
    for snap in history:
        if not isinstance(snap, dict):
            continue
        dt = _parse_dt(snap.get("at"))
        if dt and dt <= target:
            candidates.append((dt, snap))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def _flow_window(current: dict[str, Any], reference: dict[str, Any] | None) -> dict[str, Any]:
    if not reference:
        return {"status": "INSUFFICIENT_HISTORY", "method": "SNAPSHOT_HOLDER_BALANCE_DELTA"}
    cur = current.get("real_holder_pct") if isinstance(current.get("real_holder_pct"), dict) else {}
    old = reference.get("real_holder_pct") if isinstance(reference.get("real_holder_pct"), dict) else {}
    wallets = set(cur) | set(old)
    deltas = [(wallet, float(cur.get(wallet, 0.0)) - float(old.get(wallet, 0.0))) for wallet in wallets]
    positive = sum(delta for _, delta in deltas if delta > 0)
    negative = sum(delta for _, delta in deltas if delta < 0)
    top10_delta = (_f(current.get("adjusted_top10_pct")) or 0.0) - (_f(reference.get("adjusted_top10_pct")) or 0.0)
    cex_delta = (_f(current.get("cex_custody_pct")) or 0.0) - (_f(reference.get("cex_custody_pct")) or 0.0)
    if top10_delta >= 1.0 and positive >= 1.0:
        status = "ACCUMULATION"
    elif top10_delta <= -1.0 and abs(negative) >= 1.0:
        status = "DISTRIBUTION"
    else:
        status = "STABLE_MIXED"
    movers = sorted(deltas, key=lambda x: abs(x[1]), reverse=True)[:5]
    return {
        "status": status,
        "method": "SNAPSHOT_HOLDER_BALANCE_DELTA",
        "holder_top10_delta_pct": round(top10_delta, 4),
        "cex_custody_delta_pct": round(cex_delta, 4),
        "gross_positive_holder_delta_pct": round(positive, 4),
        "gross_negative_holder_delta_pct": round(negative, 4),
        "largest_holder_share_changes": [{"wallet": w, "delta_pct": round(d, 4)} for w, d in movers],
        "reference_at": reference.get("at"),
    }


def whale_flow_snapshot(
    history: list[dict[str, Any]], current: dict[str, Any], now: datetime
) -> dict[str, Any]:
    return {
        "method": "SNAPSHOT_HOLDER_BALANCE_DELTA_NOT_TRANSACTION_NETFLOW",
        "h1": _flow_window(current, _history_reference(history, now, 1)),
        "h6": _flow_window(current, _history_reference(history, now, 6)),
        "h24": _flow_window(current, _history_reference(history, now, 24)),
    }


def _entry_timing(
    market: dict[str, Any] | None,
    history: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    if not isinstance(market, dict) or market.get("complete") is not True:
        return {"score": 0, "state": "UNKNOWN", "complete": False, "reasons": ["LIVE_EXACT_PAIR_MARKET_EVIDENCE_MISSING"]}
    score = 100
    reasons: list[str] = []
    h1 = _f(market.get("price_change_h1_pct"))
    h6 = _f(market.get("price_change_h6_pct"))
    h24 = _f(market.get("price_change_h24_pct"))
    if h1 is not None:
        if h1 >= 30:
            score -= 45
            reasons.append("PRICE_ALREADY_EXTENDED_H1_GE_30PCT")
        elif h1 >= 20:
            score -= 30
            reasons.append("PRICE_EXTENDED_H1_GE_20PCT")
        elif h1 >= 12:
            score -= 15
            reasons.append("PRICE_FAST_H1_GE_12PCT")
    if h6 is not None:
        if h6 >= 60:
            score -= 30
            reasons.append("PRICE_ALREADY_EXTENDED_H6_GE_60PCT")
        elif h6 >= 35:
            score -= 18
            reasons.append("PRICE_EXTENDED_H6_GE_35PCT")
    if h24 is not None and h24 >= 100:
        score -= 30
        reasons.append("PRICE_ALREADY_EXTENDED_H24_GE_100PCT")
    ref24 = _history_reference(history, now, 24)
    ref6 = _history_reference(history, now, 6)
    price = _f(market.get("price_usd"))
    for label, ref, threshold, penalty in (("H6_BASELINE", ref6, 35.0, 20), ("H24_BASELINE", ref24, 60.0, 30)):
        old_price = _f((ref or {}).get("price_usd"))
        if price and old_price and old_price > 0:
            gain = (price / old_price - 1.0) * 100.0
            if gain >= threshold:
                score -= penalty
                reasons.append(f"PRICE_EXTENDED_VS_{label}_{gain:.1f}PCT")
    score = max(0, min(100, score))
    state = "EARLY_VALID" if score >= 75 else ("CAUTION" if score >= 55 else "WAIT_FOR_RETEST")
    return {
        "score": score,
        "state": state,
        "complete": True,
        "reasons": reasons,
        "price_change_h1_pct": h1,
        "price_change_h6_pct": h6,
        "price_change_h24_pct": h24,
    }


def _wallet_score(holder: dict[str, Any] | None) -> int:
    if not isinstance(holder, dict) or holder.get("verification_complete") is not True:
        return 0
    score = 100
    top10 = _f(holder.get("adjusted_real_top10_pct", holder.get("top10_pct"))) or 0.0
    top5 = _f(holder.get("adjusted_real_top5_pct", holder.get("top5_pct"))) or 0.0
    top1 = _f(holder.get("adjusted_real_top1_pct", holder.get("top1_pct"))) or 0.0
    if top1 > 20:
        score -= 35
    elif top1 > 12:
        score -= 15
    if top5 > 50:
        score -= 30
    elif top5 > 35:
        score -= 12
    if top10 > 65:
        score -= 35
    elif top10 > 50:
        score -= 15
    if holder.get("status") == "REVIEW":
        score -= 25
    if holder.get("status") == "BLOCK":
        score = 0
    return max(0, min(100, score))


def _bundle_risk(holder: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(holder, dict):
        return {"level": "UNKNOWN", "confidence": 0.0, "reasons": ["HOLDER_EVIDENCE_MISSING"]}
    blockable = holder.get("blockable_cluster_risks") or []
    corroborated = holder.get("corroborated_cluster_risks") or []
    funding = holder.get("verified_native_funding_edges") or []
    linked = holder.get("linked_cluster_candidates") or []
    if blockable:
        return {"level": "HIGH", "confidence": 0.95, "reasons": ["CORROBORATED_BLOCKABLE_LINKED_CLUSTER"], "clusters": len(blockable)}
    if corroborated or (linked and funding):
        return {"level": "MEDIUM", "confidence": 0.8, "reasons": ["CORROBORATED_OR_FUNDED_LINKED_WALLETS"], "clusters": len(corroborated or linked)}
    chain = str(holder.get("chain") or "").lower()
    if holder.get("verification_complete") is True and chain in EVM_CHAINS:
        return {"level": "LOW", "confidence": 0.7, "reasons": [], "clusters": 0}
    if holder.get("verification_complete") is True:
        return {
            "level": "UNKNOWN",
            "confidence": 0.35,
            "reasons": ["HOLDER_DISTRIBUTION_COMPLETE_BUT_BUNDLE_LINKAGE_NOT_PROVEN"],
            "clusters": len(linked),
        }
    return {"level": "UNKNOWN", "confidence": 0.25, "reasons": ["CLUSTER_EVIDENCE_INCOMPLETE"], "clusters": len(linked)}


def evaluate_candidate(
    row: dict[str, Any],
    holder: dict[str, Any] | None,
    market: dict[str, Any] | None,
    history: list[dict[str, Any]] | None = None,
    smart_money: dict[str, Any] | None = None,
    *,
    mode: str = MODE_SHADOW,
    now: datetime | None = None,
    max_evidence_age_seconds: int = DEFAULT_MAX_EVIDENCE_AGE_SECONDS,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    history = [x for x in (history or []) if isinstance(x, dict)]
    mode = mode if mode in VALID_MODES else MODE_SHADOW
    reasons: list[str] = []
    blockers: list[str] = []

    holder_fresh = bool(
        isinstance(holder, dict)
        and _evidence_fresh(holder.get("checked_at"), now, max_evidence_age_seconds)
    )
    holder_complete = bool(
        isinstance(holder, dict)
        and holder.get("verification_complete") is True
        and holder_fresh
    )
    market_fresh = bool(
        isinstance(market, dict)
        and market.get("complete") is True
        and _evidence_fresh(market.get("checked_at"), now, max_evidence_age_seconds)
    )

    if not holder_complete:
        blockers.append("HOLDER_CLUSTER_EVIDENCE_MISSING_INCOMPLETE_OR_STALE")
    elif str(holder.get("status") or "").upper() != "PASS":
        blockers.append(f"HOLDER_CLUSTER_STATUS_{str(holder.get('status') or 'UNKNOWN').upper()}")
    if not market_fresh:
        blockers.append("LIVE_EXACT_PAIR_MARKET_EVIDENCE_MISSING_OR_STALE")

    bundle = _bundle_risk(holder)
    if bundle.get("level") == "HIGH":
        blockers.append("HIGH_CORROBORATED_BUNDLE_CLUSTER_RISK")
    elif bundle.get("level") == "MEDIUM":
        reasons.append("MEDIUM_BUNDLE_CLUSTER_RISK_REVIEW")

    timing = _entry_timing(market if market_fresh else None, history, now)
    if timing.get("state") == "WAIT_FOR_RETEST":
        reasons.append("ENTRY_TIMING_STRETCHED_WAIT_FOR_RETEST")

    wallet_score = _wallet_score(holder if holder_fresh else None)
    current_snapshot = _snapshot_from_evidence(now, holder if holder_fresh else None, market if market_fresh else None, smart_money)
    whale_flow = whale_flow_snapshot(history, current_snapshot, now)

    if blockers:
        decision = "RESEARCH_ONLY"
    elif timing.get("state") == "WAIT_FOR_RETEST":
        decision = "WAIT_FOR_RETEST"
    else:
        decision = "ACTIONABLE"

    would_block = decision != "ACTIONABLE"
    send_allowed = True if mode == MODE_SHADOW else not would_block
    confidence_parts = [
        1.0 if holder_complete else 0.0,
        1.0 if market_fresh else 0.0,
        min(1.0, float((smart_money or {}).get("confidence") or 0.0)),
        1.0 if bundle.get("level") != "UNKNOWN" else 0.0,
    ]
    confidence = round(sum(confidence_parts) / len(confidence_parts) * 100.0, 1)

    return {
        "key": pair_key(row),
        "chain": row.get("chain"),
        "token_address": row.get("token_address") or row.get("token") or row.get("mint"),
        "pair_address": row.get("pair_address"),
        "evaluated_at": now.isoformat(),
        "mode": mode,
        "decision": decision,
        "actionable": decision == "ACTIONABLE",
        "would_block": would_block,
        "send_allowed": send_allowed,
        "confidence": confidence,
        "wallet_forensics_score": wallet_score,
        "entry_timing_score": timing.get("score"),
        "critical_evidence_complete": holder_complete and market_fresh,
        "holder_cluster": {
            "status": (holder or {}).get("status", "MISSING"),
            "verification_complete": bool((holder or {}).get("verification_complete")),
            "fresh": holder_fresh,
            "checked_at": (holder or {}).get("checked_at"),
            "gross_top10_pct": (holder or {}).get("gross_top10_pct"),
            "adjusted_top10_pct": (holder or {}).get("adjusted_real_top10_pct", (holder or {}).get("top10_pct")),
            "largest_adjusted_holder_pct": (holder or {}).get("adjusted_real_top1_pct", (holder or {}).get("top1_pct")),
            "cex_custody_pct": (holder or {}).get("cex_custody_pct"),
            "known_infrastructure_pct": (holder or {}).get("known_infrastructure_pct"),
            "unknown_holder_pct_observed": (holder or {}).get("unknown_holder_pct_observed"),
            "reasons": list((holder or {}).get("reasons") or []),
        },
        "bundle_analysis": bundle,
        "whale_flow": whale_flow,
        "smart_money_persistence": smart_money or {
            "status": "UNAVAILABLE",
            "confidence": 0.0,
            "side_inference": "NOT_CLAIMED",
        },
        "entry_timing": timing,
        "market_snapshot": market or {"complete": False, "source": "UNAVAILABLE"},
        "blockers": list(dict.fromkeys(blockers)),
        "reasons": list(dict.fromkeys(reasons)),
        "evidence_snapshot": current_snapshot,
    }


def result_index(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    return {
        str(row.get("key")): row
        for row in (payload.get("results") or [])
        if isinstance(row, dict) and row.get("key")
    }


def gate_allows_send(row: dict[str, Any], report: Any, mode: str | None = None) -> tuple[bool, dict[str, Any] | None]:
    configured_mode = str(mode or (report.get("mode") if isinstance(report, dict) else "") or MODE_SHADOW).lower()
    if configured_mode not in VALID_MODES:
        configured_mode = MODE_SHADOW
    result = result_index(report).get(pair_key(row))
    if configured_mode == MODE_SHADOW:
        return True, result
    if not result:
        return False, None
    return bool(result.get("send_allowed") is True and result.get("decision") == "ACTIONABLE"), result


def build_delivery_payload(real_payload: Any, report: dict[str, Any]) -> dict[str, Any]:
    payload = dict(real_payload) if isinstance(real_payload, dict) else {}
    source_alerts = _rows(real_payload, "alerts")
    mode = str(report.get("mode") or MODE_SHADOW).lower()
    by_key = result_index(report)
    if mode == MODE_ENFORCE:
        alerts = [
            row
            for row in source_alerts
            if (by_key.get(pair_key(row)) or {}).get("decision") == "ACTIONABLE"
            and (by_key.get(pair_key(row)) or {}).get("send_allowed") is True
        ]
    else:
        alerts = list(source_alerts)
    payload["alerts"] = alerts
    payload["pre_alert_forensics"] = {
        "mode": mode,
        "report": "pre-alert-forensics-report.json",
        "source_real_alert_count": len(source_alerts),
        "delivery_real_alert_count": len(alerts),
        "suppressed_real_alert_count": len(source_alerts) - len(alerts),
        "shadow_only": mode == MODE_SHADOW,
    }
    return payload


def run(output_dir: str | None = None) -> dict[str, Any]:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    mode = str(os.getenv("PRE_ALERT_FORENSICS_MODE", MODE_SHADOW)).strip().lower()
    if mode not in VALID_MODES:
        mode = MODE_SHADOW
    max_age = max(60, int(os.getenv("PRE_ALERT_FORENSICS_MAX_AGE_SECONDS", str(DEFAULT_MAX_EVIDENCE_AGE_SECONDS))))
    max_history = max(24, int(os.getenv("PRE_ALERT_FORENSICS_MAX_HISTORY", str(DEFAULT_MAX_HISTORY))))
    live_market = os.getenv("PRE_ALERT_FORENSICS_LIVE_MARKET", "1").strip().lower() not in {"0", "false", "no"}
    live_holder_refresh = os.getenv("PRE_ALERT_FORENSICS_LIVE_HOLDER_REFRESH", "1").strip().lower() not in {"0", "false", "no"}
    live_wallet_refresh = os.getenv("PRE_ALERT_FORENSICS_LIVE_WALLET_REFRESH", "1").strip().lower() not in {"0", "false", "no"}
    max_live_refreshes = max(0, int(os.getenv("PRE_ALERT_FORENSICS_MAX_LIVE_REFRESHES", "3")))
    wallet_signatures = max(1, int(os.getenv("PRE_ALERT_FORENSICS_WALLET_SIGNATURES", "12")))

    real_payload = _load(out / os.getenv("WALLET500_REAL_ALERT_INPUT", "real-alerts.json"), {})
    holder_payload = _load(out / "holder-cluster-gate.json", {})
    wallet_payload = _load(out / "wallet-candidates.json", {})
    registry_payload = _load(out / "revival-wallet-registry.json", {})
    state_path = out / "pre-alert-forensics-state.json"
    report_path = out / "pre-alert-forensics-report.json"
    state = _load(state_path, {})
    histories = state.get("history") if isinstance(state, dict) and isinstance(state.get("history"), dict) else {}

    generated_at = real_payload.get("generated_at") if isinstance(real_payload, dict) else None
    real_rows = _rows(real_payload, "alerts")
    pre_wave_rows = _rows(real_payload, "pre_wave_alerts")
    targets = []
    seen = set()
    for row in real_rows + pre_wave_rows:
        key = pair_key(row)
        if key and key not in seen:
            seen.add(key)
            targets.append(row)

    holder_by_key = _holder_index(holder_payload)
    wallet_by_key = _wallet_candidate_index(wallet_payload)
    now = datetime.now(timezone.utc)
    results = []
    snapshot_status = {}
    holder_refreshes = 0
    wallet_refreshes = 0

    for row in targets:
        key = pair_key(row)
        holder = holder_by_key.get(key)
        persisted_holder_fresh = bool(holder and _evidence_fresh(holder.get("checked_at"), now, max_age))
        if live_holder_refresh and (not persisted_holder_fresh or holder.get("verification_complete") is not True) and holder_refreshes < max_live_refreshes:
            refreshed_holder = refresh_holder_evidence(row)
            holder_refreshes += 1
            if refreshed_holder:
                holder = refreshed_holder
        fallback_market = _market_from_row(row, generated_at)
        market = fetch_exact_pair_market(row) if live_market else None
        if not market:
            market = fallback_market
        wallet_evidence = wallet_by_key.get(key)
        if live_wallet_refresh and not wallet_evidence and wallet_refreshes < max_live_refreshes:
            refreshed_wallet = refresh_wallet_evidence(row, wallet_signatures)
            wallet_refreshes += 1
            if refreshed_wallet:
                wallet_evidence = refreshed_wallet
        smart_money = smart_money_snapshot(row, wallet_evidence, registry_payload)
        history = [x for x in (histories.get(key) or []) if isinstance(x, dict)]
        result = evaluate_candidate(
            row,
            holder,
            market,
            history,
            smart_money,
            mode=mode,
            now=now,
            max_evidence_age_seconds=max_age,
        )
        result["alert_stage"] = "REAL_ALERT" if row in real_rows else "PRE_WAVE"
        results.append(result)

        snapshot = result["evidence_snapshot"]
        updated_history = (history + [snapshot])[-max_history:]
        histories[key] = updated_history
        snapshot_status[key] = {
            "snapshots": len(updated_history),
            "latest_at": snapshot.get("at"),
        }

    state_payload = {
        "version": 1,
        "updated_at": now.isoformat(),
        "history": histories,
        "snapshot_status": snapshot_status,
    }
    report = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": mode,
        "source": "real-alerts.json + holder-cluster-gate.json + wallet-candidates.json + revival-wallet-registry.json",
        "targets": len(targets),
        "real_alert_targets": len(real_rows),
        "pre_wave_targets": len(pre_wave_rows),
        "actionable": sum(r.get("decision") == "ACTIONABLE" for r in results),
        "would_block": sum(bool(r.get("would_block")) for r in results if r.get("alert_stage") == "REAL_ALERT"),
        "truth_contract": {
            "shadow_does_not_suppress_current_real_alerts": mode == MODE_SHADOW,
            "enforce_requires_actionable_pre_alert_forensics": mode == MODE_ENFORCE,
            "research_only_never_telegram": True,
            "holder_cluster_evidence_required_and_fresh_in_enforce": True,
            "exact_pair_market_evidence_required_and_fresh_in_enforce": True,
            "smart_money_signer_touch_does_not_claim_buy_sell_side": True,
            "whale_flow_is_snapshot_balance_delta_not_transaction_netflow": True,
            "entry_timing_is_separate_from_token_quality": True,
            "automatic_trade": False,
        },
        "results": results,
    }
    delivery_payload = build_delivery_payload(real_payload, report)
    _write(state_path, state_payload)
    _write(report_path, report)
    _write(out / "pre-alert-forensics-real-alerts.json", delivery_payload)
    print(json.dumps({
        "mode": mode,
        "targets": len(targets),
        "real_alert_targets": len(real_rows),
        "actionable": report["actionable"],
        "would_block": report["would_block"],
        "holder_refreshes": holder_refreshes,
        "wallet_refreshes": wallet_refreshes,
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
