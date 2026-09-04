from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "candidate-evidence-envelope.json"
VERSION = 1
MODE = "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1"
MIN_MARKET_AGE_DAYS = 180
MIN_EXECUTION_LIQUIDITY_USD = 50_000.0

SOURCE_MAX_AGE_SECONDS = {
    "revival": 2 * 3600,
    "holder": 2 * 3600,
    "wallet": 2 * 3600,
    "registry": 2 * 3600,
    "precursor": 90 * 60,
    "waking": 90 * 60,
    "cex": 45 * 60,
    "pre_t0": 2 * 3600,
}
STRONG_PRECURSOR = {"HIGH_CONVICTION_PRECURSOR", "PRE_BREAKOUT_CANDIDATE", "EARLY_REVIVAL_WATCH"}
STRONG_WAKING = {"WAKING_CONFIRMED_RESEARCH", "WAKING_STRONG_RESEARCH"}


def _load(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return int(default)


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _freshness(payload: dict, source: str, now: datetime) -> dict:
    stamp = next((payload.get(k) for k in ("generated_at", "updated_at", "source_generated_at") if payload.get(k)), None)
    parsed = _parse_dt(stamp)
    age = None if parsed is None else max(0.0, (now - parsed).total_seconds())
    max_age = SOURCE_MAX_AGE_SECONDS[source]
    return {
        "generated_at": stamp,
        "age_seconds": None if age is None else round(age, 1),
        "max_age_seconds": max_age,
        "fresh": age is not None and age <= max_age,
    }


def _rows(payload: Any, *keys: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            return [row for row in value.values() if isinstance(row, dict)]
    return []


def _token(row: dict) -> str:
    return str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()


def _pair(row: dict) -> str:
    return str(row.get("pair_address") or row.get("dex_pair_address") or row.get("exact_pair") or "").strip()


def _index(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        token = _token(row)
        if token:
            out[token] = row
    return out


def _registry_bridge_index(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in _rows(payload, "event_bridge"):
        token = _token(row)
        if not token:
            continue
        previous = out.get(token)
        if previous is None or str(row.get("waking_t0") or "") > str(previous.get("waking_t0") or ""):
            out[token] = row
    return out


def _pre_t0_index(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    source_rows = []
    source_rows.extend(_rows(payload, "active_deep_watch"))
    source_rows.extend(_rows(payload, "records"))
    for row in source_rows:
        token, pair = _token(row), _pair(row)
        if token and pair:
            out[f"{token}|{pair.lower()}"] = row
    return out


def _holder_lane(row: dict | None, fresh: bool) -> dict:
    row = row or {}
    truth = str(row.get("holder_truth_status") or "").upper()
    verified = bool(
        fresh
        and row.get("growth_eligible") is True
        and row.get("holder_count") is not None
        and "VERIFIED" in truth
    )
    ready24 = row.get("holder_growth_24h_ready") is True
    ready7 = row.get("holder_growth_7d_ready") is True
    growth24 = row.get("holder_growth_24h_count")
    growth7 = row.get("holder_growth_7d_count")
    positive = verified and ((ready24 and _num(growth24) > 0) or (ready7 and _num(growth7) > 0))
    return {
        "verified": verified,
        "positive": positive,
        "status": truth or "MISSING",
        "source": row.get("source") or row.get("provider"),
        "metrics": {
            "holder_count": row.get("holder_count"),
            "growth_24h_ready": ready24,
            "growth_24h_count": growth24,
            "growth_24h_pct": row.get("holder_growth_24h_pct"),
            "growth_7d_ready": ready7,
            "growth_7d_count": growth7,
            "growth_7d_pct": row.get("holder_growth_7d_pct"),
        },
    }


def _wallet_lane(row: dict | None, expected_pair: str, fresh: bool) -> dict:
    row = row or {}
    coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
    windows = row.get("windows") if isinstance(row.get("windows"), dict) else {}
    h1 = windows.get("h1") if isinstance(windows.get("h1"), dict) else {}
    row_pair = _pair(row)
    pair_ok = bool(expected_pair and row_pair and row_pair.lower() == expected_pair.lower())
    minimum_resolution = _num(coverage.get("minimum_resolution_pct"), 80)
    resolution = _num(coverage.get("last_run_resolution_pct"), 0)
    verified = bool(
        fresh
        and pair_ok
        and coverage.get("coverage_quality") == "ACCEPTABLE"
        and coverage.get("coverage_gap") is not True
        and resolution >= minimum_resolution
    )
    resolved = _int(h1.get("resolved_swaps"))
    first_buyers = _int(h1.get("first_seen_buyers_since_monitor_t0"))
    accumulating = _int(h1.get("net_accumulating_wallets"))
    distributing = _int(h1.get("net_distributing_wallets"))
    ratio = _num(h1.get("wallet_buy_sell_ratio"), 0)
    positive = bool(
        verified
        and resolved >= 6
        and first_buyers >= 3
        and accumulating >= 3
        and accumulating - distributing >= 1
        and ratio >= 1.15
    )
    return {
        "verified": verified,
        "positive": positive,
        "pair_match": pair_ok,
        "status": "VERIFIED_ACCUMULATION" if positive else ("VERIFIED_NO_ACCUMULATION" if verified else "MISSING_OR_PARTIAL"),
        "metrics": {
            "resolution_pct": coverage.get("last_run_resolution_pct"),
            "resolved_swaps_h1": resolved,
            "unique_traders_h1": h1.get("unique_traders"),
            "first_seen_buyers_h1": first_buyers,
            "net_accumulating_wallets_h1": accumulating,
            "net_distributing_wallets_h1": distributing,
            "wallet_buy_sell_ratio_h1": ratio,
        },
    }


def _smart_money_lane(row: dict | None, expected_pair: str, fresh: bool) -> dict:
    row = row or {}
    row_pair = _pair(row)
    pair_ok = bool(expected_pair and row_pair and row_pair.lower() == expected_pair.lower())
    verified = bool(fresh and pair_ok and row)
    qualified = _int(row.get("historically_qualified_pre_waking_buyers"))
    return {
        "verified": verified,
        "positive": verified and qualified > 0,
        "status": "QUALIFIED_PRE_WAKING_BUYERS_PRESENT" if verified and qualified > 0 else ("VERIFIED_NONE" if verified else "MISSING"),
        "metrics": {
            "verified_wallets_seen": row.get("verified_wallets_seen"),
            "historically_qualified_pre_waking_buyers": qualified if verified else None,
            "waking_t0": row.get("waking_t0"),
        },
    }


def _cex_lane(row: dict | None, expected_pair: str, fresh: bool) -> dict:
    row = row or {}
    row_pair = _pair(row)
    pair_ok = bool(expected_pair and row_pair and row_pair.lower() == expected_pair.lower())
    identity_ok = row.get("identity_status") == "DEX_VERIFIED" or row.get("identity_verified") is True
    age_ok = row.get("market_age_verified") is True and _int(row.get("market_age_min_days")) >= MIN_MARKET_AGE_DAYS
    verified = bool(fresh and pair_ok and identity_ok and age_ok)
    score = _num(row.get("cex_revival_score"))
    confirmations = _int(row.get("coherent_confirmations"))
    positive = verified and score >= 35 and confirmations >= 2
    return {
        "verified": verified,
        "positive": positive,
        "status": "VERIFIED_CEX_REVIVAL" if positive else ("VERIFIED_NO_SIGNAL" if verified else "MISSING"),
        "metrics": {"score": score if row else None, "coherent_confirmations": confirmations if row else None},
    }


def _precursor_lane(row: dict | None, expected_pair: str, fresh: bool) -> dict:
    row = row or {}
    identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    row_pair = _pair(row)
    pair_ok = bool(expected_pair and row_pair and row_pair.lower() == expected_pair.lower())
    verified = bool(fresh and pair_ok and identity.get("exact_mint_verified") is True and identity.get("exact_pair_verified") is True)
    status = str(row.get("status") or "")
    return {
        "verified": verified,
        "positive": verified and status in STRONG_PRECURSOR,
        "status": status or "MISSING",
        "metrics": {
            "confidence_adjusted_score": row.get("confidence_adjusted_score"),
            "available_evidence_score": row.get("normalized_score_available_evidence"),
            "evidence_coverage_pct": row.get("evidence_coverage_pct"),
        },
    }


def _waking_lane(row: dict | None, expected_pair: str, fresh: bool) -> dict:
    row = row or {}
    row_pair = _pair(row)
    pair_ok = bool(expected_pair and row_pair and row_pair.lower() == expected_pair.lower())
    status = str(row.get("confirmation_status") or "")
    verified = bool(fresh and pair_ok and row)
    return {
        "verified": verified,
        "positive": verified and status in STRONG_WAKING,
        "status": status or "MISSING",
        "metrics": {"confirmation_score": row.get("confirmation_score")},
    }


def _social_lane(precursor: dict | None, waking: dict | None, precursor_fresh: bool, waking_fresh: bool) -> dict:
    precursor = precursor or {}
    waking = waking or {}
    p_snapshot = precursor.get("evidence_snapshot") if isinstance(precursor.get("evidence_snapshot"), dict) else {}
    p_social = p_snapshot.get("social") if isinstance(p_snapshot.get("social"), dict) else {}
    w_channels = waking.get("channels") if isinstance(waking.get("channels"), dict) else {}
    w_social = w_channels.get("social") if isinstance(w_channels.get("social"), dict) else {}
    candidates = []
    if precursor_fresh and p_social.get("verified") is True:
        candidates.append(p_social)
    if waking_fresh and w_social.get("verified") is True:
        candidates.append(w_social)
    if not candidates:
        return {"verified": False, "positive": False, "status": "MISSING", "metrics": {}}
    best = max(candidates, key=lambda row: _num(row.get("score")))
    signals = best.get("signals") if isinstance(best.get("signals"), list) else []
    score = _num(best.get("score"))
    return {
        "verified": True,
        "positive": score >= 55 or bool(signals),
        "status": "VERIFIED_MULTI_SOURCE_SOCIAL",
        "source": best.get("source"),
        "metrics": {"score": score, "signals": signals},
    }


def _concentration_lane(row: dict | None, fresh: bool) -> dict:
    row = row or {}
    families = row.get("families") if isinstance(row.get("families"), dict) else {}
    concentration = families.get("concentration") if isinstance(families.get("concentration"), dict) else {}
    verified = bool(fresh and concentration.get("verified") is True)
    return {
        "verified": verified,
        "positive": False,
        "role": "RISK_CONTEXT_ONLY_NEVER_POSITIVE_ALPHA",
        "status": concentration.get("status") or "MISSING",
        "metrics": {
            "top1_pct": concentration.get("top1_pct"),
            "top5_pct": concentration.get("top5_pct"),
            "top10_pct": concentration.get("top10_pct"),
            "top20_pct": concentration.get("top20_pct"),
            "concentration_risk_score": concentration.get("concentration_risk_score"),
        },
    }


def _risk_blockers(revival: dict, pre_t0: dict | None, pre_t0_fresh: bool) -> list[str]:
    blockers: list[str] = []
    components = revival.get("revival_score_components") if isinstance(revival.get("revival_score_components"), dict) else {}
    liquidity_change = components.get("liquidity_change_pct")
    if liquidity_change is not None and _num(liquidity_change) <= -75:
        blockers.append("LIQUIDITY_COLLAPSE_75PCT")
    status = str(revival.get("watch_status") or "")
    if status in {"FAILED_SURVIVAL", "PUMP_DUMP_RISK", "LATE_MOVE_DO_NOT_CHASE"}:
        blockers.append(status)
    concentration = _concentration_lane(pre_t0, pre_t0_fresh)
    risk = _num((concentration.get("metrics") or {}).get("concentration_risk_score"), 0)
    if concentration.get("verified") is True and risk >= 90:
        blockers.append("EXTREME_CONCENTRATION_RISK")
    return sorted(set(blockers))


def build(data_dir: Path = DATA, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    revival = _load(data_dir / "revival-1000-latest.json", {})
    holder = _load(data_dir / "revival-holder-latest.json", {})
    wallet = _load(data_dir / "revival-prewaking-wallet-evidence.json", {})
    registry = _load(data_dir / "revival-wallet-registry.json", {})
    precursor = _load(data_dir / "revival-precursor-latest.json", {})
    waking = _load(data_dir / "waking-confirmation-latest.json", {})
    cex = _load(data_dir / "cex-revival-radar.json", {})
    pre_t0 = _load(data_dir / "revival-pre-t0-evidence.json", {})

    sources = {
        "revival": _freshness(revival, "revival", now),
        "holder": _freshness(holder, "holder", now),
        "wallet": _freshness(wallet, "wallet", now),
        "registry": _freshness(registry, "registry", now),
        "precursor": _freshness(precursor, "precursor", now),
        "waking": _freshness(waking, "waking", now),
        "cex": _freshness(cex, "cex", now),
        "pre_t0": _freshness(pre_t0, "pre_t0", now),
    }

    holder_idx = _index(_rows(holder, "coins", "tokens"))
    wallet_idx = _index(_rows(wallet, "tokens"))
    registry_idx = _registry_bridge_index(registry if isinstance(registry, dict) else {})
    precursor_idx = _index(_rows(precursor, "targets"))
    waking_idx = _index(_rows(waking, "targets"))
    cex_idx = _index(_rows(cex, "alerts"))
    pre_idx = _pre_t0_index(pre_t0 if isinstance(pre_t0, dict) else {})

    candidates = []
    for revival_row in _rows(revival, "coins"):
        token = _token(revival_row)
        pair = _pair(revival_row)
        if not token or not pair:
            continue
        exact_identity = revival_row.get("network_verified") is True and str(revival_row.get("network") or "").lower() == "solana"
        exact_pair = revival_row.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
        age_days = _int(revival_row.get("market_age_min_days"), 0)
        age_ok = revival_row.get("market_age_verified") is True and age_days >= MIN_MARKET_AGE_DAYS
        liquidity = _num(revival_row.get("dex_pair_liquidity_usd"), 0)
        liquidity_ok = liquidity >= MIN_EXECUTION_LIQUIDITY_USD
        revival_score = _num(revival_row.get("revival_score_verified"), 0)
        watch_status = str(revival_row.get("watch_status") or "")
        market_positive = watch_status == "WAKING_MARKET_ONLY" or revival_score >= 65

        holder_lane = _holder_lane(holder_idx.get(token), sources["holder"]["fresh"])
        wallet_lane = _wallet_lane(wallet_idx.get(token), pair, sources["wallet"]["fresh"])
        smart_lane = _smart_money_lane(registry_idx.get(token), pair, sources["registry"]["fresh"])
        cex_lane = _cex_lane(cex_idx.get(token), pair, sources["cex"]["fresh"])
        precursor_lane = _precursor_lane(precursor_idx.get(token), pair, sources["precursor"]["fresh"])
        waking_lane = _waking_lane(waking_idx.get(token), pair, sources["waking"]["fresh"])
        social_lane = _social_lane(precursor_idx.get(token), waking_idx.get(token), sources["precursor"]["fresh"], sources["waking"]["fresh"])
        pre_row = pre_idx.get(f"{token}|{pair.lower()}")
        concentration_lane = _concentration_lane(pre_row, sources["pre_t0"]["fresh"])

        components = revival_row.get("revival_score_components") if isinstance(revival_row.get("revival_score_components"), dict) else {}
        pair_survival_verified = exact_pair and components.get("same_pair_as_previous") is True
        pair_survival_positive = pair_survival_verified and _num(components.get("liquidity_change_pct"), 0) > -50
        independent = {
            "HOLDER_GROWTH": holder_lane,
            "WALLET_ACCUMULATION": wallet_lane,
            "SMART_MONEY": smart_lane,
            "CEX_REVIVAL": cex_lane,
            "VERIFIED_SOCIAL": social_lane,
        }
        verified_lanes = sorted(name for name, lane in independent.items() if lane.get("verified") is True)
        positive_lanes = sorted(name for name, lane in independent.items() if lane.get("positive") is True)
        risk_blockers = _risk_blockers(revival_row, pre_row, sources["pre_t0"]["fresh"])
        base_truth_ok = bool(exact_identity and exact_pair and age_ok and liquidity_ok and sources["revival"]["fresh"] and not risk_blockers)
        verified_family_count = (2 if exact_identity and exact_pair else 0) + len(verified_lanes)
        evidence_ready = bool(base_truth_ok and market_positive and positive_lanes and verified_family_count >= 3)

        if evidence_ready:
            status = "EVIDENCE_READY"
        elif base_truth_ok and market_positive:
            status = "VERIFIED_WATCH"
        elif base_truth_ok:
            status = "DEEP_WATCH"
        else:
            status = "BLOCKED_TRUTH"

        blockers = []
        if not sources["revival"]["fresh"]:
            blockers.append("REVIVAL_SOURCE_STALE")
        if not exact_identity:
            blockers.append("EXACT_IDENTITY_REQUIRED")
        if not exact_pair:
            blockers.append("EXACT_PAIR_REQUIRED")
        if not age_ok:
            blockers.append("MARKET_AGE_180D_REQUIRED")
        if not liquidity_ok:
            blockers.append("EXECUTION_LIQUIDITY_LT_50K")
        blockers.extend(risk_blockers)
        if base_truth_ok and not market_positive:
            blockers.append("MARKET_STRUCTURE_NOT_WAKING")
        if base_truth_ok and market_positive and not positive_lanes:
            blockers.append("NO_INDEPENDENT_POSITIVE_EVIDENCE")

        candidates.append({
            "key": f"solana:{token}:{pair.lower()}",
            "chain": "solana",
            "network": "solana",
            "token_address": token,
            "symbol": revival_row.get("symbol"),
            "pair_address": pair,
            "dex_url": revival_row.get("dex_link"),
            "status": status,
            "production_effect": False,
            "automatic_buy": False,
            "truth": {
                "exact_identity_verified": exact_identity,
                "exact_pair_verified": exact_pair,
                "market_age_verified_180d_plus": age_ok,
                "market_age_days": age_days if age_ok else None,
                "execution_pool_liquidity_usd": liquidity,
                "execution_liquidity_floor_passed": liquidity_ok,
                "revival_source_fresh": sources["revival"]["fresh"],
            },
            "market": {
                "revival_score_verified": revival_score,
                "watch_status": watch_status,
                "market_positive": market_positive,
                "price_usd": revival_row.get("price_usd"),
                "liquidity_usd": liquidity,
                "volume_24h_usd": revival_row.get("dex_pair_volume_24h_usd"),
                "drawdown_from_ath_pct": revival_row.get("drawdown_from_ath_pct"),
                "liquidity_change_pct": components.get("liquidity_change_pct"),
                "pair_volume_change_pct": components.get("pair_volume_change_pct"),
            },
            "families": {
                "holder_growth": holder_lane,
                "wallet_accumulation": wallet_lane,
                "smart_money": smart_lane,
                "cex_revival": cex_lane,
                "precursor": precursor_lane,
                "waking_confirmation": waking_lane,
                "social": social_lane,
                "pair_survival": {
                    "verified": pair_survival_verified,
                    "positive": pair_survival_positive,
                    "status": "SURVIVED_PREVIOUS_EXACT_PAIR" if pair_survival_verified else "PENDING",
                },
                "concentration": concentration_lane,
            },
            "coverage": {
                "verified_independent_lanes": verified_lanes,
                "positive_independent_lanes": positive_lanes,
                "verified_independent_count": len(verified_lanes),
                "positive_independent_count": len(positive_lanes),
                "verified_family_count": verified_family_count,
                "evidence_ready": evidence_ready,
            },
            "blockers": sorted(set(blockers)),
        })

    priority = {"EVIDENCE_READY": 0, "VERIFIED_WATCH": 1, "DEEP_WATCH": 2, "BLOCKED_TRUTH": 3}
    candidates.sort(key=lambda row: (
        priority.get(row["status"], 9),
        -_int((row.get("coverage") or {}).get("positive_independent_count")),
        -_num((row.get("market") or {}).get("revival_score_verified")),
        -_num((row.get("market") or {}).get("liquidity_usd")),
    ))

    counts = {
        "universe_with_exact_pair": len(candidates),
        "evidence_ready": sum(1 for row in candidates if row["status"] == "EVIDENCE_READY"),
        "verified_watch": sum(1 for row in candidates if row["status"] == "VERIFIED_WATCH"),
        "deep_watch": sum(1 for row in candidates if row["status"] == "DEEP_WATCH"),
        "blocked_truth": sum(1 for row in candidates if row["status"] == "BLOCKED_TRUTH"),
        "with_verified_holder_growth_lane": sum(1 for row in candidates if row["families"]["holder_growth"]["verified"]),
        "with_positive_holder_growth": sum(1 for row in candidates if row["families"]["holder_growth"]["positive"]),
        "with_verified_wallet_lane": sum(1 for row in candidates if row["families"]["wallet_accumulation"]["verified"]),
        "with_positive_wallet_accumulation": sum(1 for row in candidates if row["families"]["wallet_accumulation"]["positive"]),
        "with_positive_smart_money": sum(1 for row in candidates if row["families"]["smart_money"]["positive"]),
        "with_positive_cex": sum(1 for row in candidates if row["families"]["cex_revival"]["positive"]),
    }

    return {
        "version": VERSION,
        "mode": MODE,
        "generated_at": now.isoformat(),
        "production_change": False,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "minimum_execution_pool_liquidity_usd": MIN_EXECUTION_LIQUIDITY_USD,
            "exact_identity_required": True,
            "exact_pair_required": True,
            "missing_evidence_never_positive": True,
            "stale_evidence_never_positive": True,
            "concentration_is_risk_context_only": True,
            "evidence_ready_is_research_promotion_not_buy_signal": True,
            "no_hindsight": True,
        },
        "source_freshness": sources,
        "counts": counts,
        "candidates": candidates,
    }


def run(data_dir: Path = DATA) -> dict:
    payload = build(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / OUTPUT.name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({"counts": payload["counts"], "source_freshness": payload["source_freshness"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
