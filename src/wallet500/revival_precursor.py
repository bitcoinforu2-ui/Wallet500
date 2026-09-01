from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
WAKING = DATA / "waking-confirmation-latest.json"
WHALE = DATA / "whale-flow-evidence.json"
DERIVATIVES = DATA / "derivatives-evidence.json"
LATEST = DATA / "revival-precursor-latest.json"
STATE = DATA / "revival-precursor-state.json"

MODE = "RESEARCH_ONLY_REVIVAL_PRECURSOR_V1"
CONTRACT = "REVIVAL_PRECURSOR_V1"
NETWORK = "solana"

FAMILY_WEIGHTS = {
    "market_structure": 30.0,
    "holder_wallet_accumulation": 25.0,
    "social_attention": 15.0,
    "whale_smart_money": 15.0,
    "derivatives_cex": 15.0,
}


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _n(value: Any, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _verified_channel(row: dict | None) -> bool:
    return isinstance(row, dict) and row.get("verified") is True


def _evidence_map(payload: dict, key: str) -> dict[str, dict]:
    rows = payload.get(key) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return {}
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        mint = str(row.get("token_address") or row.get("token") or "")
        if mint:
            out[mint] = row
    return out


def score_market_structure(coin: dict) -> tuple[float, list[str]]:
    score = 0.0
    signals: list[str] = []
    dd = _n(coin.get("drawdown_from_ath_pct"))
    c24 = _n(coin.get("change_24h_pct"), 0.0) or 0.0
    c7 = _n(coin.get("change_7d_pct"), 0.0) or 0.0
    c30 = _n(coin.get("change_30d_pct"), 0.0) or 0.0
    rs24 = _n(coin.get("relative_strength_24h_vs_universe_pp"))
    rs7 = _n(coin.get("relative_strength_7d_vs_universe_pp"))
    comp = coin.get("revival_score_components") or {}
    same_pair = comp.get("same_pair_as_previous") is True
    liq_change = _n(comp.get("liquidity_change_pct"))
    vol_change = _n(comp.get("pair_volume_change_pct"))
    liq = _n(coin.get("dex_pair_liquidity_usd"), 0.0) or 0.0
    volume = _n(coin.get("dex_pair_volume_24h_usd"), 0.0) or 0.0

    if dd is not None and 65 <= dd <= 95:
        score += 20
        signals.append("DEEP_DRAWDOWN_SETUP")
        if 75 <= dd <= 90:
            score += 5
            signals.append("DRAWDOWN_CORE_ZONE")

    if -5 <= c24 <= 18:
        score += 12
        signals.append("EARLY_24H_NOT_EXTENDED")
    elif 18 < c24 < 35:
        score += 5
        signals.append("24H_MOVE_ALREADY_ADVANCING")
    elif c24 >= 35:
        score -= 18
        signals.append("LATE_24H_CHASE_RISK")

    if 0 < c7 <= 35:
        score += 10
        signals.append("EARLY_7D_AWAKENING")
    elif c7 > 70:
        score -= 8
        signals.append("7D_EXTENSION_RISK")

    if -20 <= c30 <= 45:
        score += 5

    if rs24 is not None and rs24 >= 5:
        score += 10
        signals.append("RELATIVE_STRENGTH_24H")
    if rs7 is not None and rs7 >= 10:
        score += 8
        signals.append("RELATIVE_STRENGTH_7D")

    if same_pair:
        score += 10
        signals.append("EXACT_PAIR_SURVIVED_PRIOR_SNAPSHOT")
    if liq_change is not None:
        if liq_change >= 0:
            score += 8
            signals.append("LIQUIDITY_STABLE_OR_RISING")
        elif liq_change <= -25:
            score -= 12
            signals.append("LIQUIDITY_DRAIN")
    if vol_change is not None and vol_change >= 20:
        score += 6
        signals.append("PAIR_VOLUME_ACCELERATION")
    if liq >= 250_000:
        score += 4
        signals.append("LIQUIDITY_GE_250K")
    if volume >= 1_000_000:
        score += 2

    return round(_clamp(score), 2), signals


def score_holder_wallet(channels: dict) -> tuple[float | None, list[str], list[str]]:
    holders = channels.get("holders") if isinstance(channels, dict) else None
    wallets = channels.get("wallets") if isinstance(channels, dict) else None
    signals: list[str] = []
    missing: list[str] = []
    parts = []
    if _verified_channel(holders):
        hs = _clamp(_n(holders.get("score"), 0.0) or 0.0)
        parts.append((hs, 0.45))
        signals.extend(list(holders.get("signals") or []))
    else:
        missing.append("HOLDER_GROWTH")
    if _verified_channel(wallets):
        ws = _clamp(_n(wallets.get("score"), 0.0) or 0.0)
        parts.append((ws, 0.55))
        signals.extend(list(wallets.get("signals") or []))
    else:
        missing.append("UNIQUE_WALLET_GROWTH")
    if not parts:
        return None, signals, missing
    weight = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / weight
    return round(_clamp(score), 2), signals, missing


def score_social(channels: dict) -> tuple[float | None, list[str], list[str]]:
    social = channels.get("social") if isinstance(channels, dict) else None
    if not _verified_channel(social):
        return None, [], ["SOCIAL_MULTI_SOURCE"]
    metrics = social.get("metrics") or {}
    sources = int(_n(metrics.get("sources"), 0) or 0)
    authors = int(_n(metrics.get("authors"), 0) or 0)
    raw = _clamp(_n(social.get("score"), 0.0) or 0.0)
    signals = list(social.get("signals") or [])
    # Attention is supporting evidence only; single-source hype is deliberately capped.
    if sources < 2 or authors < 3:
        raw = min(raw, 35.0)
        signals.append("SOCIAL_SINGLE_SOURCE_OR_LOW_AUTHOR_DIVERSITY")
    if any("SOCIAL_COUNT_VS_PREVIOUS_" in str(x) for x in signals):
        signals.append("SOCIAL_VELOCITY_MEASURED")
    return round(raw, 2), signals, []


def score_whale(row: dict | None) -> tuple[float | None, list[str], list[str]]:
    if not isinstance(row, dict) or row.get("verified") is not True or row.get("exact_mint_verified") is not True:
        return None, [], ["WHALE_SMART_MONEY_EXACT_MINT"]
    score = 0.0
    signals: list[str] = []
    whale_24h = _n(row.get("whale_netflow_usd_24h"))
    whale_7d = _n(row.get("whale_netflow_usd_7d"))
    smart_count = _n(row.get("smart_wallet_accumulator_count"))
    smart_net = _n(row.get("smart_wallet_netflow_usd_24h"))
    if whale_24h is not None and whale_24h > 0:
        score += min(35.0, 10.0 + math.log10(max(1.0, whale_24h)) * 4.0)
        signals.append("WHALE_NETFLOW_24H_POSITIVE")
    if whale_7d is not None and whale_7d > 0:
        score += min(25.0, 8.0 + math.log10(max(1.0, whale_7d)) * 3.0)
        signals.append("WHALE_NETFLOW_7D_POSITIVE")
    if smart_count is not None and smart_count >= 3:
        score += min(20.0, smart_count * 2.5)
        signals.append("MULTIPLE_SMART_WALLET_ACCUMULATORS")
    if smart_net is not None and smart_net > 0:
        score += 20.0
        signals.append("SMART_WALLET_NETFLOW_POSITIVE")
    return round(_clamp(score), 2), signals, []


def score_derivatives(row: dict | None) -> tuple[float | None, list[str], list[str]]:
    if not isinstance(row, dict) or row.get("verified") is not True or row.get("canonical_token_mapping_verified") is not True:
        return None, [], ["DERIVATIVES_CANONICAL_MAPPING"]
    score = 0.0
    signals: list[str] = []
    oi_change = _n(row.get("open_interest_change_24h_pct"))
    oi_usd = _n(row.get("open_interest_usd"))
    funding = _n(row.get("funding_rate_pct"))
    exchanges = _n(row.get("derivatives_exchange_count"))
    spot_exchanges = _n(row.get("spot_cex_count"))
    if oi_change is not None:
        if 10 <= oi_change <= 80:
            score += 35.0
            signals.append("OI_EXPANDING_WITHIN_EARLY_BAND")
        elif oi_change > 80:
            score += 20.0
            signals.append("OI_EXPANSION_EXTREME_CAUTION")
        elif oi_change < -20:
            signals.append("OI_CONTRACTION")
    if oi_usd is not None and oi_usd >= 1_000_000:
        score += 15.0
        signals.append("OPEN_INTEREST_GE_1M")
    if exchanges is not None and exchanges >= 2:
        score += min(20.0, exchanges * 4.0)
        signals.append("MULTI_EXCHANGE_DERIVATIVES")
    if spot_exchanges is not None and spot_exchanges >= 3:
        score += min(15.0, spot_exchanges * 2.0)
        signals.append("CEX_BREADTH")
    if funding is not None:
        if abs(funding) <= 0.05:
            score += 15.0
            signals.append("FUNDING_NOT_CROWDED")
        elif abs(funding) >= 0.20:
            score -= 15.0
            signals.append("FUNDING_CROWDING_RISK")
    return round(_clamp(score), 2), signals, []


def combine(families: dict[str, dict], coin: dict) -> dict:
    weighted = 0.0
    available_weight = 0.0
    strong = []
    missing = []
    for name, weight in FAMILY_WEIGHTS.items():
        f = families[name]
        score = f.get("score")
        if score is None:
            missing.extend(f.get("missing") or [name])
            continue
        available_weight += weight
        weighted += weight * _clamp(float(score)) / 100.0
        if float(score) >= 55:
            strong.append(name)
    coverage = 100.0 * available_weight / sum(FAMILY_WEIGHTS.values())
    normalized = 100.0 * weighted / available_weight if available_weight else 0.0
    confidence_adjusted = normalized * coverage / 100.0

    c24 = _n(coin.get("change_24h_pct"), 0.0) or 0.0
    c7 = _n(coin.get("change_7d_pct"), 0.0) or 0.0
    market_score = families["market_structure"].get("score") or 0
    flow_score = families["holder_wallet_accumulation"].get("score")
    independent_confirmation = any(
        (families[x].get("score") or 0) >= 45
        for x in ("social_attention", "whale_smart_money", "derivatives_cex")
    )

    if c24 >= 35 or c7 >= 85:
        status = "LATE_MOVE_DO_NOT_CHASE"
    elif coverage >= 75 and normalized >= 75 and len(strong) >= 4 and market_score >= 60:
        status = "HIGH_CONVICTION_PRECURSOR"
    elif coverage >= 60 and normalized >= 65 and market_score >= 55 and (flow_score or 0) >= 45 and independent_confirmation:
        status = "PRE_BREAKOUT_CANDIDATE"
    elif coverage >= 45 and normalized >= 52 and market_score >= 50:
        status = "EARLY_REVIVAL_WATCH"
    else:
        status = "INSUFFICIENT_PRECURSOR_EVIDENCE"

    return {
        "status": status,
        "normalized_score_available_evidence": round(normalized, 2),
        "confidence_adjusted_score": round(confidence_adjusted, 2),
        "evidence_coverage_pct": round(coverage, 2),
        "strong_families": strong,
        "missing_evidence": sorted(set(missing)),
    }


def evaluate(coin: dict, waking: dict | None = None, whale: dict | None = None, derivatives: dict | None = None) -> dict:
    channels = (waking or {}).get("channels") or {}
    market_score, market_signals = score_market_structure(coin)
    hw_score, hw_signals, hw_missing = score_holder_wallet(channels)
    social_score, social_signals, social_missing = score_social(channels)
    whale_score, whale_signals, whale_missing = score_whale(whale)
    deriv_score, deriv_signals, deriv_missing = score_derivatives(derivatives)
    families = {
        "market_structure": {"score": market_score, "signals": market_signals, "missing": []},
        "holder_wallet_accumulation": {"score": hw_score, "signals": hw_signals, "missing": hw_missing},
        "social_attention": {"score": social_score, "signals": social_signals, "missing": social_missing},
        "whale_smart_money": {"score": whale_score, "signals": whale_signals, "missing": whale_missing},
        "derivatives_cex": {"score": deriv_score, "signals": deriv_signals, "missing": deriv_missing},
    }
    decision = combine(families, coin)
    return {
        "network": NETWORK,
        "token_address": coin.get("token_address"),
        "symbol": coin.get("symbol"),
        "name": coin.get("name"),
        "coingecko_id": coin.get("id"),
        "pair_address": coin.get("dex_pair_address"),
        "price_usd": coin.get("price_usd"),
        "drawdown_from_ath_pct": coin.get("drawdown_from_ath_pct"),
        "change_24h_pct": coin.get("change_24h_pct"),
        "change_7d_pct": coin.get("change_7d_pct"),
        "change_30d_pct": coin.get("change_30d_pct"),
        "relative_strength_24h_vs_universe_pp": coin.get("relative_strength_24h_vs_universe_pp"),
        "relative_strength_7d_vs_universe_pp": coin.get("relative_strength_7d_vs_universe_pp"),
        "revival_score_verified": coin.get("revival_score_verified"),
        "waking_confirmation_status": (waking or {}).get("confirmation_status"),
        "families": families,
        **decision,
        "production_portfolio_impact": "NONE",
    }


def run(output_dir: str = "data") -> dict:
    global DATA, REVIVAL, WAKING, WHALE, DERIVATIVES, LATEST, STATE
    DATA = Path(output_dir)
    REVIVAL = DATA / "revival-1000-latest.json"
    WAKING = DATA / "waking-confirmation-latest.json"
    WHALE = DATA / "whale-flow-evidence.json"
    DERIVATIVES = DATA / "derivatives-evidence.json"
    LATEST = DATA / "revival-precursor-latest.json"
    STATE = DATA / "revival-precursor-state.json"
    DATA.mkdir(parents=True, exist_ok=True)

    revival = _load(REVIVAL, {})
    waking = _load(WAKING, {})
    whale = _load(WHALE, {})
    derivatives = _load(DERIVATIVES, {})

    if revival.get("network") != NETWORK or revival.get("production_portfolio_impact") != "NONE":
        raise RuntimeError("REVIVAL_PRECURSOR_SOURCE_CONTRACT_REJECTED")
    if waking and (waking.get("network") != NETWORK or waking.get("production_portfolio_impact") != "NONE"):
        raise RuntimeError("WAKING_PRECURSOR_SOURCE_CONTRACT_REJECTED")

    waking_map = _evidence_map(waking, "targets")
    whale_map = _evidence_map(whale, "observations")
    derivative_map = _evidence_map(derivatives, "observations")

    rows = []
    for coin in revival.get("coins") or []:
        if not isinstance(coin, dict):
            continue
        if coin.get("watch_status") not in {"WAKING_MARKET_ONLY", "DEEP_WATCH"}:
            continue
        mint = str(coin.get("token_address") or "")
        rows.append(evaluate(coin, waking_map.get(mint), whale_map.get(mint), derivative_map.get(mint)))

    priority = {
        "HIGH_CONVICTION_PRECURSOR": 0,
        "PRE_BREAKOUT_CANDIDATE": 1,
        "EARLY_REVIVAL_WATCH": 2,
        "LATE_MOVE_DO_NOT_CHASE": 3,
        "INSUFFICIENT_PRECURSOR_EVIDENCE": 4,
    }
    rows.sort(key=lambda x: (priority.get(x["status"], 9), -float(x["confidence_adjusted_score"])))
    now = datetime.now(timezone.utc).isoformat()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    payload = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "network": NETWORK,
        "generated_at": now,
        "source_revival_generated_at": revival.get("generated_at"),
        "source_waking_generated_at": waking.get("generated_at") if isinstance(waking, dict) else None,
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "family_weights": FAMILY_WEIGHTS,
        "truth_rules": [
            "missing evidence is never converted to a positive score",
            "social attention is supporting evidence and cannot by itself create a pre-breakout candidate",
            "whale/smart-money evidence must be exact-mint verified",
            "derivatives evidence must have canonical token mapping; symbol-only matches cannot score",
            "late 24h/7d moves are classified as do-not-chase even when other signals are strong",
            "this layer is research/shadow only and cannot change production portfolio decisions",
        ],
        "counts": {"targets": len(rows), **counts},
        "targets": rows,
    }
    _write(LATEST, payload)
    _write(STATE, {"version": 1, "updated_at": now, "last_counts": payload["counts"]})
    print("REVIVAL_PRECURSOR_V1_OK", payload["counts"])
    return payload


if __name__ == "__main__":
    run()
