from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .policy import (
    CANONICAL_MIN_EXECUTION_LIQUIDITY_USD,
    CANONICAL_MIN_MARKET_AGE_DAYS,
)

DATA = Path("data")
OUTPUT = DATA / "confluence-matrix.json"
MODE = "RESEARCH_ONLY_CONFLUENCE_MATRIX_V1"

# Static prior selected after competitor/architecture review. These are not
# learned probabilities. They are a ranking prior until forward holdout data is
# sufficient to validate a learned ranking model.
WEIGHTS: dict[str, float] = {
    "wallet_alpha": 22.0,
    "market_microstructure": 18.0,
    "execution_copyability": 14.0,
    "holder_growth": 8.0,
    "funding_cluster_independence": 5.0,
    "social_narrative": 9.0,
    "official_catalyst": 8.0,
    "independent_confirmation": 7.0,
    "cex_acceleration": 4.0,
    "price_anti_chase": 5.0,
}
PREDICTIVE_LANES = {
    "wallet_alpha",
    "market_microstructure",
    "holder_growth",
    "funding_cluster_independence",
    "social_narrative",
    "official_catalyst",
    "independent_confirmation",
    "cex_acceleration",
    "price_anti_chase",
}
FRESHNESS_SECONDS = {
    "cross-signal-fusion-v2.json": 1_800,
    "real-alerts.json": 3_600,
    "candidate-evidence-envelope.json": 3_600,
    "holder-concentration-shadow.json": 21_600,
    "paid-order-truth.json": 7_200,
    "catalyst-wire-live.json": 7_200,
    "cex-revival-radar.json": 7_200,
    "funding-cluster-intelligence.json": 7_200,
}

EVM = {
    "ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "linea", "zksync", "mantle",
    "scroll", "blast",
}


def _load(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value if value is not None else default))
    except (TypeError, ValueError):
        return int(default)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _payload_timestamp(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in ("generated_at", "updated_at", "created_at", "observed_at", "timestamp"):
        if payload.get(key):
            return payload.get(key)
    return None


def _freshness(payload: Any, max_age_seconds: int, now: datetime) -> dict[str, Any]:
    raw = _payload_timestamp(payload)
    dt = _ts(raw)
    age = (now - dt).total_seconds() if dt else None
    fresh = age is not None and -120 <= age <= max_age_seconds
    return {
        "timestamp": raw,
        "age_seconds": round(age, 1) if age is not None else None,
        "max_age_seconds": max_age_seconds,
        "fresh": fresh,
    }


def _norm_chain(value: Any) -> str:
    chain = str(value or "").strip().lower()
    return {
        "eth": "ethereum",
        "bnb": "bsc",
        "binance-smart-chain": "bsc",
        "arbitrum-one": "arbitrum",
    }.get(chain, chain)


def _norm_addr(chain: str, value: Any) -> str:
    addr = str(value or "").strip()
    if chain in EVM:
        return addr.lower()
    return addr


def _identity(row: dict[str, Any]) -> tuple[str, str, str]:
    chain = _norm_chain(row.get("chain") or row.get("network"))
    token = _norm_addr(
        chain,
        row.get("token_address") or row.get("token") or row.get("mint") or row.get("contract"),
    )
    pair = _norm_addr(
        chain,
        row.get("pair_address") or row.get("entry_pair_address") or row.get("dex_pair_address"),
    )
    return chain, token, pair


def _key(chain: str, token: str, pair: str = "") -> str:
    if not chain or not token:
        return ""
    return f"{chain}:{token}:{pair}" if pair else f"{chain}:{token}"


def _rows(payload: Any, *preferred: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for name in (*preferred, "tokens", "candidates", "alerts", "verified_watch", "rows", "coins", "targets", "items"):
        value = payload.get(name)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _all_real_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    for name in ("alerts", "verified_watch", "dormant_no_activity", "identity_pending"):
        value = payload.get(name)
        if isinstance(value, list):
            out.extend(x for x in value if isinstance(x, dict))
    return out


def _index(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    exact: dict[str, dict[str, Any]] = {}
    token: dict[str, dict[str, Any]] = {}
    for row in rows:
        chain, tok, pair = _identity(row)
        if not chain or not tok:
            continue
        token[_key(chain, tok)] = row
        if pair:
            exact[_key(chain, tok, pair)] = row
    return exact, token


def _lookup(
    indexes: tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]],
    chain: str,
    token: str,
    pair: str,
) -> dict[str, Any]:
    exact, token_index = indexes
    if pair:
        row = exact.get(_key(chain, token, pair))
        if row is not None:
            return row
    return token_index.get(_key(chain, token), {})


def _lane(
    *,
    name: str,
    score: float | None,
    available: bool,
    source: str | None,
    coverage_factor: float = 1.0,
    detail: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weight = WEIGHTS[name]
    cf = _clamp(coverage_factor * 100.0) / 100.0 if available else 0.0
    return {
        "available": bool(available),
        "score": round(_clamp(score or 0.0), 2) if available else None,
        "weight": weight,
        "coverage_factor": round(cf, 4),
        "effective_weight": round(weight * cf, 4),
        "source": source,
        "detail": detail,
        "evidence": evidence or {},
    }


def _channel_score(channel: Any) -> tuple[bool, float, float]:
    if not isinstance(channel, dict) or channel.get("available") is not True:
        return False, 0.0, 0.0
    score = _clamp(_num(channel.get("score")))
    confidence = channel.get("confidence")
    cf = _clamp(_num(confidence, 1.0) * 100.0) / 100.0 if confidence is not None else 1.0
    return True, score, cf


def _wallet_lane(fusion_row: dict[str, Any]) -> dict[str, Any]:
    channels = fusion_row.get("channels") if isinstance(fusion_row.get("channels"), dict) else {}
    wa, ws, wc = _channel_score(channels.get("wallets"))
    sa, ss, sc = _channel_score(channels.get("smart_money"))
    if not wa and not sa:
        return _lane(
            name="wallet_alpha", score=None, available=False, source="cross-signal-fusion-v2.json",
            detail="No verified wallet/smart-money channel yet.",
        )
    weighted = 0.0
    denom = 0.0
    coverage = 0.0
    if wa:
        weighted += ws * 0.75
        denom += 0.75
        coverage += 0.75 * wc
    if sa:
        weighted += ss * 0.25
        denom += 0.25
        coverage += 0.25 * sc
    return _lane(
        name="wallet_alpha",
        score=weighted / denom if denom else 0.0,
        available=True,
        source="cross-signal-fusion-v2.json",
        coverage_factor=coverage,
        detail="Wallet behavior and smart-money evidence; provider labels never count as ground-truth PnL.",
        evidence={"wallets": channels.get("wallets"), "smart_money": channels.get("smart_money")},
    )


def _market_lane(fusion_row: dict[str, Any]) -> dict[str, Any]:
    channels = fusion_row.get("channels") if isinstance(fusion_row.get("channels"), dict) else {}
    available, score, cf = _channel_score(channels.get("market"))
    return _lane(
        name="market_microstructure", score=score, available=available,
        source="cross-signal-fusion-v2.json", coverage_factor=cf,
        detail="Exact-pair market activity and persistence.",
        evidence={"channel": channels.get("market"), "change": fusion_row.get("change")},
    )


def _holder_lane(fusion_row: dict[str, Any]) -> dict[str, Any]:
    channels = fusion_row.get("channels") if isinstance(fusion_row.get("channels"), dict) else {}
    available, score, cf = _channel_score(channels.get("holders"))
    return _lane(
        name="holder_growth", score=score, available=available,
        source="cross-signal-fusion-v2.json", coverage_factor=cf,
        detail="Holder growth only; concentration is handled separately as risk.",
        evidence={"channel": channels.get("holders"), "change": fusion_row.get("change")},
    )


def _social_lane(fusion_row: dict[str, Any]) -> dict[str, Any]:
    channels = fusion_row.get("channels") if isinstance(fusion_row.get("channels"), dict) else {}
    channel = channels.get("narrative")
    available, score, cf = _channel_score(channel)
    if isinstance(channel, dict) and available:
        raw_conf = _num(channel.get("confidence"), 1.0)
        cf = _clamp(raw_conf * 100.0) / 100.0 if raw_conf <= 1 else _clamp(raw_conf) / 100.0
    return _lane(
        name="social_narrative", score=score, available=available,
        source="cross-signal-fusion-v2.json", coverage_factor=cf,
        detail="Organic/narrative acceleration is confidence-weighted and cannot override hard truth.",
        evidence={"channel": channel},
    )


def _confirmation_lane(fusion_row: dict[str, Any]) -> dict[str, Any]:
    count = _int(fusion_row.get("positive_family_count"))
    if count <= 0:
        score = 0.0
    elif count == 1:
        score = 38.0
    elif count == 2:
        score = 72.0
    else:
        score = 100.0
    return _lane(
        name="independent_confirmation", score=score, available=True,
        source="cross-signal-fusion-v2.json",
        detail=f"{count} independent positive signal families.",
        evidence={"positive_family_count": count},
    )


def _anti_chase_lane(fusion_row: dict[str, Any]) -> dict[str, Any]:
    risk = fusion_row.get("risk") if isinstance(fusion_row.get("risk"), dict) else {}
    late = risk.get("late_move")
    if late is None:
        return _lane(
            name="price_anti_chase", score=None, available=False, source="cross-signal-fusion-v2.json",
            detail="Late-move state unavailable.",
        )
    return _lane(
        name="price_anti_chase", score=0.0 if late is True else 100.0, available=True,
        source="cross-signal-fusion-v2.json",
        detail="Rewards early structure; late visible moves are penalized separately too.",
        evidence={"late_move": late},
    )


def _execution_liquidity(row: dict[str, Any]) -> tuple[float | None, str | None]:
    for field in (
        "execution_pool_liquidity_usd",
        "execution_liquidity_usd",
        "dex_pair_liquidity_usd",
        "dex_liquidity_usd",
    ):
        if row.get(field) is not None:
            return _num(row.get(field)), field
    exact = (
        row.get("exact_pair_verified") is True
        or row.get("pair_identity_locked") is True
        or row.get("identity_status") == "DEX_VERIFIED"
    )
    if exact and row.get("liquidity_usd") is not None:
        return _num(row.get("liquidity_usd")), "liquidity_usd"
    return None, None


def _copyability_score(liquidity: float, row: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    if liquidity < CANONICAL_MIN_EXECUTION_LIQUIDITY_USD:
        base = 0.0
    elif liquidity < 25_000:
        base = 35.0
    elif liquidity < 50_000:
        base = 55.0
    elif liquidity < 100_000:
        base = 70.0
    elif liquidity < 250_000:
        base = 85.0
    else:
        base = 95.0

    impact = None
    for key in ("price_impact_pct", "slippage_pct", "estimated_slippage_pct", "execution_price_impact_pct"):
        if row.get(key) is not None:
            impact = max(0.0, _num(row.get(key)))
            break
    penalty = min(35.0, impact * 7.0) if impact is not None else 0.0
    score = max(0.0, base - penalty)
    return score, {"liquidity_usd": liquidity, "impact_pct": impact, "impact_penalty": round(penalty, 2)}


def _execution_lane(
    chain: str,
    token: str,
    pair: str,
    sources: dict[str, dict[str, Any]],
    indexes: dict[str, tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]],
    freshness: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    for filename in ("real-alerts.json", "candidate-evidence-envelope.json", "cex-revival-radar.json"):
        if not freshness.get(filename, {}).get("fresh"):
            continue
        row = _lookup(indexes.get(filename, ({}, {})), chain, token, pair)
        if not row:
            continue
        liquidity, field = _execution_liquidity(row)
        if liquidity is None:
            continue
        if liquidity < CANONICAL_MIN_EXECUTION_LIQUIDITY_USD:
            blockers.append("EXECUTION_LIQUIDITY_LT_15K")
        score, evidence = _copyability_score(liquidity, row)
        evidence.update({"field": field, "pair_address": _identity(row)[2] or pair})
        return (
            _lane(
                name="execution_copyability", score=score, available=True, source=filename,
                detail="Execution/copyability is kept separate from predictive alpha.",
                evidence=evidence,
            ),
            blockers,
        )
    return (
        _lane(
            name="execution_copyability", score=None, available=False, source=None,
            detail="No fresh exact-pair execution-depth evidence.",
        ),
        blockers,
    )


def _catalyst_lane(
    chain: str,
    token: str,
    pair: str,
    payload: dict[str, Any],
    is_fresh: bool,
) -> dict[str, Any]:
    if not is_fresh:
        return _lane(
            name="official_catalyst", score=None, available=False, source="catalyst-wire-live.json",
            detail="Catalyst source stale or unavailable.",
        )
    best: dict[str, Any] | None = None
    for event in _rows(payload, "events"):
        ec, et, ep = _identity(event)
        if ec != chain or et != token:
            continue
        if pair and ep and ep != pair:
            continue
        if (
            event.get("alert_eligible") is not True
            or event.get("symbol_contract_link_verified") is not True
            or event.get("identity_guard_status") != "PASS"
        ):
            continue
        if best is None or _num(event.get("impact_score")) > _num(best.get("impact_score")):
            best = event
    if best is None:
        return _lane(
            name="official_catalyst", score=None, available=False, source="catalyst-wire-live.json",
            detail="No identity-verified official catalyst.",
        )
    return _lane(
        name="official_catalyst", score=_num(best.get("impact_score")), available=True,
        source="catalyst-wire-live.json",
        detail=str(best.get("event_type") or "OFFICIAL_CATALYST"),
        evidence={
            "event_id": best.get("event_id"),
            "event_type": best.get("event_type"),
            "observed_at": best.get("observed_at"),
            "source_id": best.get("source_id"),
            "source_url": best.get("source_url"),
        },
    )


def _cex_lane(
    chain: str,
    token: str,
    pair: str,
    indexes: dict[str, tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]],
    freshness: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    filename = "cex-revival-radar.json"
    if not freshness.get(filename, {}).get("fresh"):
        return _lane(
            name="cex_acceleration", score=None, available=False, source=filename,
            detail="CEX lane stale or unavailable.",
        )
    row = _lookup(indexes.get(filename, ({}, {})), chain, token, pair)
    if not row:
        return _lane(
            name="cex_acceleration", score=None, available=False, source=filename,
            detail="No exact CEX identity match.",
        )
    exact_ok = (
        row.get("identity_registry_verified") is True
        and row.get("identity_status") == "DEX_VERIFIED"
        and row.get("dex_activity_verified") is True
    )
    if not exact_ok:
        return _lane(
            name="cex_acceleration", score=None, available=False, source=filename,
            detail="CEX observation exists but exact identity/activity proof is incomplete.",
            evidence={"identity_status": row.get("identity_status")},
        )
    confirmations = _int(row.get("coherent_confirmations"))
    cf = min(1.0, confirmations / 3.0) if confirmations > 0 else 0.34
    return _lane(
        name="cex_acceleration", score=_num(row.get("cex_revival_score")), available=True,
        source=filename, coverage_factor=cf,
        detail=f"{confirmations} coherent CEX confirmations.",
        evidence={"coherent_confirmations": confirmations, "exchanges": row.get("exchanges")},
    )


def _funding_lane(
    chain: str,
    token: str,
    pair: str,
    indexes: dict[str, tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]],
    freshness: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], float]:
    filename = "funding-cluster-intelligence.json"
    if not freshness.get(filename, {}).get("fresh"):
        return (
            _lane(
                name="funding_cluster_independence", score=None, available=False, source=filename,
                detail="Funding-origin graph not connected yet; absence lowers confidence, not alpha.",
            ),
            0.0,
        )
    row = _lookup(indexes.get(filename, ({}, {})), chain, token, pair)
    if not row:
        return (
            _lane(
                name="funding_cluster_independence", score=None, available=False, source=filename,
                detail="No verified funding graph for this token.",
            ),
            0.0,
        )
    independent = _num(row.get("independence_score"))
    if independent <= 1:
        independent *= 100
    shared_pct = _num(row.get("shared_funding_pct"))
    penalty = min(12.0, shared_pct / 100.0 * 12.0)
    return (
        _lane(
            name="funding_cluster_independence", score=independent, available=True, source=filename,
            detail="Independent funding origins reduce coordinated-wallet false positives.",
            evidence={
                "independence_score": independent,
                "shared_funding_pct": shared_pct,
                "independent_funders": row.get("independent_funders"),
                "shared_clusters": row.get("shared_clusters"),
            },
        ),
        penalty,
    )


def _holder_concentration_risk(
    chain: str,
    token: str,
    pair: str,
    indexes: dict[str, tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]],
    freshness: dict[str, dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    filename = "holder-concentration-shadow.json"
    if not freshness.get(filename, {}).get("fresh"):
        return 0.0, {"available": False, "source": filename}
    row = _lookup(indexes.get(filename, ({}, {})), chain, token, pair)
    if not row or row.get("verified") is not True or row.get("contract_match") is not True:
        return 0.0, {"available": False, "source": filename}
    raw = _clamp(_num(row.get("concentration_risk_score")))
    penalty = raw / 100.0 * 12.0
    return penalty, {
        "available": True,
        "source": filename,
        "concentration_risk_score": raw,
        "top1_pct": row.get("top1_pct"),
        "top10_pct": row.get("top10_pct"),
        "semantics": row.get("semantics"),
    }


def _paid_promotion_risk(
    chain: str,
    token: str,
    pair: str,
    payload: dict[str, Any],
    is_fresh: bool,
) -> tuple[float, dict[str, Any]]:
    filename = "paid-order-truth.json"
    if not is_fresh:
        return 0.0, {"available": False, "source": filename}
    for row in _rows(payload, "verified_paid_tokens"):
        rc, rt, rp = _identity(row)
        if rc == chain and rt == token and (not pair or not rp or rp == pair):
            return 5.0, {
                "available": True,
                "source": filename,
                "verified_active_paid_order": True,
                "order_type": row.get("order_type") or row.get("type"),
            }
    return 0.0, {"available": True, "source": filename, "verified_active_paid_order": False}


def _fusion_risk(fusion_row: dict[str, Any]) -> tuple[float, list[str], dict[str, Any]]:
    risk = fusion_row.get("risk") if isinstance(fusion_row.get("risk"), dict) else {}
    manipulation = _clamp(_num(risk.get("manipulation")))
    manip_penalty = manipulation / 100.0 * 12.0
    late = risk.get("late_move") is True
    late_penalty = 18.0 if late else 0.0
    hard = [str(x) for x in (risk.get("hard_blockers") or []) if str(x)]
    return manip_penalty + late_penalty, hard, {
        "manipulation_score": manipulation,
        "manipulation_penalty": round(manip_penalty, 2),
        "late_move": late,
        "late_move_penalty": late_penalty,
        "hard_blockers": hard,
    }


def _weighted_score(lanes: dict[str, dict[str, Any]], names: set[str]) -> tuple[float, float]:
    numerator = 0.0
    denominator = 0.0
    for name in names:
        lane = lanes[name]
        if lane.get("available") is not True:
            continue
        ew = _num(lane.get("effective_weight"))
        if ew <= 0:
            continue
        numerator += _num(lane.get("score")) * ew
        denominator += ew
    return (numerator / denominator if denominator else 0.0), denominator


def _why_now(lanes: dict[str, dict[str, Any]]) -> list[str]:
    labels = {
        "wallet_alpha": "WALLET_ALPHA",
        "market_microstructure": "MARKET_MICROSTRUCTURE",
        "holder_growth": "HOLDER_GROWTH",
        "social_narrative": "SOCIAL_NARRATIVE",
        "official_catalyst": "OFFICIAL_CATALYST",
        "independent_confirmation": "INDEPENDENT_CONFIRMATION",
        "cex_acceleration": "CEX_ACCELERATION",
        "price_anti_chase": "EARLY_PRICE_STRUCTURE",
    }
    ranked: list[tuple[float, str]] = []
    for name, label in labels.items():
        lane = lanes[name]
        if lane.get("available") is True and _num(lane.get("score")) >= 60:
            ranked.append((_num(lane.get("score")) * _num(lane.get("effective_weight")), f"{label}_{_int(lane.get('score'))}"))
    ranked.sort(reverse=True)
    return [label for _, label in ranked[:5]]


def build(data_dir: Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)

    filenames = list(FRESHNESS_SECONDS)
    sources = {name: _load(data_dir / name, {}) for name in filenames}
    freshness = {
        name: _freshness(sources[name], FRESHNESS_SECONDS[name], now)
        for name in filenames
    }

    fusion_payload = sources["cross-signal-fusion-v2.json"]
    fusion_fresh = freshness["cross-signal-fusion-v2.json"]["fresh"]
    fusion_rows = _rows(fusion_payload, "tokens") if fusion_fresh else []

    indexes: dict[str, tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]] = {}
    for filename, payload in sources.items():
        if filename == "real-alerts.json":
            rs = _all_real_rows(payload)
        else:
            rs = _rows(payload)
        indexes[filename] = _index(rs)

    rows_out: list[dict[str, Any]] = []
    for fusion_row in fusion_rows:
        chain, token, pair = _identity(fusion_row)
        if not chain or not token:
            continue

        lanes: dict[str, dict[str, Any]] = {}
        lanes["wallet_alpha"] = _wallet_lane(fusion_row)
        lanes["market_microstructure"] = _market_lane(fusion_row)
        execution, exec_blockers = _execution_lane(chain, token, pair, sources, indexes, freshness)
        lanes["execution_copyability"] = execution
        lanes["holder_growth"] = _holder_lane(fusion_row)
        funding, funding_penalty = _funding_lane(chain, token, pair, indexes, freshness)
        lanes["funding_cluster_independence"] = funding
        lanes["social_narrative"] = _social_lane(fusion_row)
        lanes["official_catalyst"] = _catalyst_lane(
            chain, token, pair, sources["catalyst-wire-live.json"],
            freshness["catalyst-wire-live.json"]["fresh"],
        )
        lanes["independent_confirmation"] = _confirmation_lane(fusion_row)
        lanes["cex_acceleration"] = _cex_lane(chain, token, pair, indexes, freshness)
        lanes["price_anti_chase"] = _anti_chase_lane(fusion_row)

        alpha, alpha_weight = _weighted_score(lanes, PREDICTIVE_LANES)
        total_effective_weight = sum(
            _num(lane.get("effective_weight"))
            for lane in lanes.values()
            if lane.get("available") is True
        )
        confidence = _clamp(total_effective_weight)
        copyability = _num(lanes["execution_copyability"].get("score")) if lanes["execution_copyability"].get("available") else 0.0

        fusion_penalty, fusion_blockers, fusion_risk_detail = _fusion_risk(fusion_row)
        concentration_penalty, concentration_detail = _holder_concentration_risk(
            chain, token, pair, indexes, freshness
        )
        paid_penalty, paid_detail = _paid_promotion_risk(
            chain, token, pair, sources["paid-order-truth.json"],
            freshness["paid-order-truth.json"]["fresh"],
        )
        risk_penalty = min(
            40.0,
            fusion_penalty + concentration_penalty + paid_penalty + funding_penalty,
        )
        hard_blockers = sorted(set(fusion_blockers + exec_blockers))

        confidence_multiplier = 0.55 + 0.45 * (confidence / 100.0)
        copy_multiplier = 0.70 + 0.30 * (copyability / 100.0) if lanes["execution_copyability"].get("available") else 0.70
        priority = max(0.0, alpha * confidence_multiplier * copy_multiplier - risk_penalty)
        if hard_blockers:
            priority = 0.0

        if hard_blockers:
            status = "BLOCKED"
        elif priority >= 72 and confidence >= 55:
            status = "HIGH_CONFLUENCE"
        elif priority >= 50 and confidence >= 35:
            status = "BUILDING_CONFLUENCE"
        else:
            status = "LOW_CONFIDENCE"

        missing = [name for name, lane in lanes.items() if lane.get("available") is not True]
        risk_reasons: list[str] = []
        if fusion_risk_detail["late_move"]:
            risk_reasons.append("LATE_MOVE")
        if fusion_risk_detail["manipulation_penalty"] > 0:
            risk_reasons.append("MANIPULATION_RISK")
        if concentration_penalty > 0:
            risk_reasons.append("HOLDER_CONCENTRATION_RISK")
        if paid_penalty > 0:
            risk_reasons.append("VERIFIED_PAID_PROMOTION")
        if funding_penalty > 0:
            risk_reasons.append("SHARED_FUNDING_CLUSTER")

        rows_out.append({
            "chain": chain,
            "token_address": token,
            "pair_address": pair or None,
            "symbol": fusion_row.get("symbol"),
            "dex_url": fusion_row.get("dex_url"),
            "source_status": fusion_row.get("source_status"),
            "discovery_tier": fusion_row.get("discovery_tier"),
            "confluence_status": status,
            "priority_score": round(priority, 2),
            "signal_alpha_score": round(alpha, 2),
            "copyability_score": round(copyability, 2) if lanes["execution_copyability"].get("available") else None,
            "confidence_pct": round(confidence, 2),
            "predictive_weight_observed": round(alpha_weight, 2),
            "risk_penalty": round(risk_penalty, 2),
            "hard_blockers": hard_blockers,
            "risk_reasons": risk_reasons,
            "missing_lanes": missing,
            "lanes": lanes,
            "risk": {
                "fusion": fusion_risk_detail,
                "holder_concentration": {
                    **concentration_detail,
                    "penalty": round(concentration_penalty, 2),
                },
                "paid_promotion": {
                    **paid_detail,
                    "penalty": round(paid_penalty, 2),
                },
                "funding_cluster_penalty": round(funding_penalty, 2),
                "total_penalty": round(risk_penalty, 2),
                "penalty_cap": 40.0,
            },
            "why_now": _why_now(lanes),
            "what_blocks": hard_blockers + risk_reasons + [f"MISSING_{x.upper()}" for x in missing],
            "source_change": fusion_row.get("change"),
            "source_fusion_score": fusion_row.get("fusion_score"),
            "production_effect": False,
            "automatic_buy": False,
        })

    rows_out.sort(
        key=lambda x: (
            x.get("confluence_status") != "BLOCKED",
            _num(x.get("priority_score")),
            _num(x.get("confidence_pct")),
        ),
        reverse=True,
    )

    counts: dict[str, int] = {
        "tokens": len(rows_out),
        "high_confluence": sum(x["confluence_status"] == "HIGH_CONFLUENCE" for x in rows_out),
        "building_confluence": sum(x["confluence_status"] == "BUILDING_CONFLUENCE" for x in rows_out),
        "low_confidence": sum(x["confluence_status"] == "LOW_CONFIDENCE" for x in rows_out),
        "blocked": sum(x["confluence_status"] == "BLOCKED" for x in rows_out),
    }
    fresh_count = sum(1 for x in freshness.values() if x["fresh"])
    payload = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": MODE,
        "production_change": False,
        "automatic_buy": False,
        "canonical_policy": {
            "minimum_market_age_days": CANONICAL_MIN_MARKET_AGE_DAYS,
            "minimum_execution_liquidity_usd": CANONICAL_MIN_EXECUTION_LIQUIDITY_USD,
            "exact_identity_required": True,
            "exact_pair_required": True,
        },
        "weight_contract": {
            "weights": WEIGHTS,
            "sum": round(sum(WEIGHTS.values()), 6),
            "static_prior_until_forward_holdout_validation": True,
            "learned_weights_may_rank_only_after_validation": True,
            "learned_weights_never_weaken_hard_gates": True,
            "missing_lane_reduces_confidence_not_observed_alpha": True,
            "execution_copyability_is_not_predictive_alpha": True,
            "risk_penalties_are_separate_from_positive_alpha": True,
        },
        "risk_contract": {
            "late_move_max_penalty": 18.0,
            "manipulation_max_penalty": 12.0,
            "holder_concentration_max_penalty": 12.0,
            "paid_promotion_penalty": 5.0,
            "shared_funding_cluster_max_penalty": 12.0,
            "total_penalty_cap": 40.0,
            "hard_blocker_forces_priority_zero": True,
        },
        "truth_contract": {
            "research_only": True,
            "no_hindsight": True,
            "point_in_time_source_freshness_required": True,
            "stale_source_never_positive": True,
            "missing_source_never_fabricated": True,
            "provider_pnl_never_ground_truth": True,
            "official_catalyst_requires_exact_identity_guard": True,
            "paid_promotion_never_positive_alpha": True,
            "holder_concentration_never_positive_alpha": True,
            "funding_graph_is_missing_until_verified": True,
        },
        "source_health": freshness,
        "source_health_summary": {
            "fresh": fresh_count,
            "total": len(freshness),
            "primary_fusion_fresh": fusion_fresh,
        },
        "counts": counts,
        "tokens": rows_out,
    }
    if not fusion_fresh:
        payload["system_state"] = "PRIMARY_FUSION_STALE_FAIL_CLOSED"
    else:
        payload["system_state"] = "READY_RESEARCH_RANKING"
    return payload


def run(data_dir: Path = DATA) -> dict[str, Any]:
    payload = build(data_dir)
    _write(data_dir / OUTPUT.name, payload)
    print(json.dumps({
        "mode": payload["mode"],
        "system_state": payload["system_state"],
        "counts": payload["counts"],
        "weights_sum": payload["weight_contract"]["sum"],
    }, indent=2))
    return payload


if __name__ == "__main__":
    run()
