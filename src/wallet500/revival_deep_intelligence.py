from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import binance_web3_market as binance_web3
from . import pre_alert_forensics as forensics

MODE = "REVIVAL_AUTO_DEEP_INTELLIGENCE_V1"
STATE = "revival-deep-intelligence-state.json"
REPORT = "revival-deep-intelligence-report.json"
REGISTRY = "revival-wallet-registry.json"
FUSION = "close-watch-intelligence.json"
PASS_SCORE = 70.0
CRITICAL_SOURCES = {"holder_cluster", "exact_pair_market", "contract_security"}
EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _f(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _norm_chain(value: object) -> str:
    raw = str(value or "").strip().lower()
    return {"eth": "ethereum", "bnb": "bsc", "sol": "solana"}.get(raw, raw)


def _norm_addr(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def _candidate(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["chain"] = _norm_chain(meta.get("chain") or row.get("chain") or row.get("network"))
    out["token_address"] = str(meta.get("token_address") or row.get("token_address") or row.get("token") or "")
    out["pair_address"] = str(meta.get("pair_address") or row.get("pair_address") or row.get("dex_pair_address") or "")
    out["locked_pair_address"] = out["pair_address"]
    out["exact_pair_verified"] = bool(out["chain"] and out["token_address"] and out["pair_address"])
    out["pair_identity_locked"] = out["exact_pair_verified"]
    return out


def _key(row: dict[str, Any]) -> str:
    chain = _norm_chain(row.get("chain") or row.get("network"))
    token = _norm_addr(chain, row.get("token_address") or row.get("token"))
    pair = _norm_addr(chain, row.get("pair_address") or row.get("dex_pair_address"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def _source_health(name: str, ok: bool, *, critical: bool, reason: str = "") -> dict[str, Any]:
    return {"source": name, "ok": bool(ok), "critical": critical, "reason": reason or ("OK" if ok else "UNAVAILABLE")}


def _contract_security(chain: str, token: str) -> dict[str, Any]:
    try:
        audit = binance_web3.fetch_audit(chain, token)
    except Exception as exc:
        return {
            "available": False,
            "status": "UNAVAILABLE",
            "hard_blockers": [],
            "warnings": [f"CONTRACT_AUDIT_ERROR:{type(exc).__name__}"],
            "risk_level": None,
            "risk_flags": [],
        }
    if audit.get("available") is not True:
        return {
            "available": False,
            "status": "UNAVAILABLE",
            "hard_blockers": [],
            "warnings": ["CONTRACT_AUDIT_UNAVAILABLE"],
            "risk_level": None,
            "risk_flags": [],
        }
    level = str(audit.get("risk_level_enum") or audit.get("risk_level") or "UNKNOWN").upper()
    flags = [str(x) for x in (audit.get("risk_flags") or [])]
    severe_flags = [x for x in flags if x.startswith("BINANCE_AUDIT_RISK:")]
    hard = []
    if level in {"HIGH", "CRITICAL"}:
        hard.append(f"CONTRACT_SECURITY_{level}")
    if severe_flags:
        hard.append("CONTRACT_SECURITY_RISK_FLAG")
    warnings = [x for x in flags if x not in severe_flags]
    status = "BLOCK" if hard else ("CAUTION" if level in {"MEDIUM", "CAUTION"} or warnings else "PASS")
    return {
        "available": True,
        "status": status,
        "hard_blockers": sorted(set(hard)),
        "warnings": warnings,
        "risk_level": level,
        "risk_flags": flags,
        "buy_tax": audit.get("buy_tax"),
        "sell_tax": audit.get("sell_tax"),
        "is_verified": audit.get("is_verified"),
    }


def _fusion_context(out: Path, row: dict[str, Any]) -> dict[str, Any]:
    payload = _load(out / FUSION, {})
    rows = payload.get("tokens") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    wanted = _key(row)
    match = None
    for item in rows:
        if not isinstance(item, dict):
            continue
        probe = {
            "chain": item.get("chain") or item.get("network"),
            "token_address": item.get("token_address") or item.get("contract"),
            "pair_address": item.get("pair_address") or item.get("pair"),
        }
        if _key(probe) == wanted:
            match = item
            break
    if not match:
        return {"available": False, "status": "NOT_AVAILABLE", "hard_risks": [], "family_scores": {}}
    current = str(match.get("status") or "").upper() == "CURRENT"
    return {
        "available": current,
        "status": str(match.get("status") or "UNKNOWN").upper(),
        "score": _f(match.get("score")),
        "label": match.get("label"),
        "independent_positive_families": int(match.get("independent_positive_families") or 0),
        "family_scores": dict(match.get("family_scores") or {}),
        "hard_risks": [str(x) for x in (match.get("hard_risks") or [])],
        "evidence_age_minutes": match.get("evidence_age_minutes"),
    }


def _flow_quality(market: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(market, dict) or market.get("complete") is not True:
        return {"status": "UNAVAILABLE", "score": 0.0, "buy_sell_ratio_h1": None, "txns_h1": 0}
    buys = int(market.get("buys_h1") or 0)
    sells = int(market.get("sells_h1") or 0)
    txns = buys + sells
    ratio = (buys / sells) if sells > 0 else (999.0 if buys > 0 else 0.0)
    if txns < 20:
        status, score = "LOW_SAMPLE", 45.0
    elif ratio >= 1.20:
        status, score = "BUYERS_LEADING", 88.0
    elif ratio >= 1.05:
        status, score = "MILD_BUY_LEAD", 74.0
    elif ratio >= 0.85:
        status, score = "BALANCED", 60.0
    else:
        status, score = "SELLERS_LEADING", 35.0
    return {
        "status": status,
        "score": score,
        "buy_sell_ratio_h1": round(ratio, 4),
        "buys_h1": buys,
        "sells_h1": sells,
        "txns_h1": txns,
        "volume_h1_usd": market.get("volume_h1_usd"),
        "claim_boundary": "TRANSACTION_COUNT_IMBALANCE_NOT_PROOF_OF_ORGANIC_USD_FLOW",
    }


def _liquidity_quality(market: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(market, dict) or market.get("complete") is not True:
        return {"status": "UNAVAILABLE", "score": 0.0, "liquidity_usd": None, "hard_blockers": []}
    liq = _f(market.get("liquidity_usd"))
    if liq < 15_000:
        return {"status": "BELOW_REVIVAL_FLOOR", "score": 20.0, "liquidity_usd": liq, "hard_blockers": ["LIVE_LIQUIDITY_BELOW_15K"]}
    if liq >= 100_000:
        status, score = "DEEP", 95.0
    elif liq >= 50_000:
        status, score = "HEALTHY", 88.0
    elif liq >= 25_000:
        status, score = "ADEQUATE", 76.0
    else:
        status, score = "THIN_BUT_ABOVE_FLOOR", 62.0
    return {"status": status, "score": score, "liquidity_usd": liq, "hard_blockers": []}


def _security_score(security: dict[str, Any]) -> float:
    if security.get("available") is not True:
        return 0.0
    if security.get("status") == "BLOCK":
        return 20.0
    if security.get("status") == "CAUTION":
        return 65.0
    return 92.0


def _split_forensics_blockers(items: Iterable[object]) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    missing: list[str] = []
    for item in items:
        text = str(item)
        if any(word in text for word in ("MISSING", "INCOMPLETE", "STALE", "UNAVAILABLE")):
            missing.append(text)
        else:
            hard.append(text)
    return hard, missing


def _confirmation_score(base: dict[str, Any], flow: dict[str, Any], liquidity: dict[str, Any], security: dict[str, Any]) -> float:
    wallet = _f(base.get("wallet_forensics_score"))
    timing = _f(base.get("entry_timing_score"))
    score = (
        wallet * 0.30
        + timing * 0.25
        + _f(flow.get("score")) * 0.20
        + _f(liquidity.get("score")) * 0.15
        + _security_score(security) * 0.10
    )
    return round(max(0.0, min(100.0, score)), 1)


def investigate_candidates(
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
    out: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()
    state_path = out / STATE
    state = _load(state_path, {})
    history_map = state.get("history") if isinstance(state, dict) and isinstance(state.get("history"), dict) else {}
    cases = state.get("cases") if isinstance(state, dict) and isinstance(state.get("cases"), dict) else {}
    registry = _load(out / REGISTRY, {})
    results: list[dict[str, Any]] = []

    for raw, revival_meta in candidates:
        row = _candidate(raw, revival_meta)
        key = _key(row)
        history = [x for x in (history_map.get(key) or []) if isinstance(x, dict)]

        market = forensics.fetch_exact_pair_market(row)
        holder = forensics.refresh_holder_evidence(row)
        wallet_evidence = forensics.refresh_wallet_evidence(row)
        smart_money = forensics.smart_money_snapshot(row, wallet_evidence, registry)
        base = forensics.evaluate_candidate(
            row,
            holder,
            market,
            history,
            smart_money,
            mode=forensics.MODE_ENFORCE,
            now=now,
        )
        security = _contract_security(str(row.get("chain") or ""), str(row.get("token_address") or ""))
        fusion = _fusion_context(out, row)
        flow = _flow_quality(market)
        liquidity = _liquidity_quality(market)

        hard, critical_missing = _split_forensics_blockers(base.get("blockers") or [])
        hard.extend(str(x) for x in (security.get("hard_blockers") or []))
        hard.extend(str(x) for x in (liquidity.get("hard_blockers") or []))
        hard.extend(f"FUSION_HARD_RISK:{x}" for x in (fusion.get("hard_risks") or []))
        if security.get("available") is not True:
            critical_missing.append("CONTRACT_SECURITY_EVIDENCE_UNAVAILABLE")
        if not isinstance(market, dict) or market.get("complete") is not True:
            critical_missing.append("EXACT_PAIR_MARKET_EVIDENCE_UNAVAILABLE")
        if not isinstance(holder, dict) or holder.get("verification_complete") is not True:
            critical_missing.append("HOLDER_CLUSTER_EVIDENCE_UNAVAILABLE")

        hard = sorted(set(hard))
        critical_missing = sorted(set(critical_missing))
        score = _confirmation_score(base, flow, liquidity, security)
        timing_state = str((base.get("entry_timing") or {}).get("state") or "UNKNOWN")
        if hard:
            status = "REJECT"
            score = min(score, 39.0)
        elif critical_missing or timing_state == "WAIT_FOR_RETEST":
            status = "WATCH"
            score = min(score, 69.0)
        elif score >= PASS_SCORE and base.get("decision") == "ACTIONABLE":
            status = "PASS"
        else:
            status = "WATCH"

        decision = {
            "PASS": "BUY CANDIDATE — MANUAL",
            "WATCH": "WATCH — MANUAL REVIEW",
            "REJECT": "REJECT",
        }[status]
        source_health = [
            _source_health("holder_cluster", bool(isinstance(holder, dict) and holder.get("verification_complete") is True), critical=True),
            _source_health("exact_pair_market", bool(isinstance(market, dict) and market.get("complete") is True), critical=True),
            _source_health("contract_security", security.get("available") is True, critical=True),
            _source_health("wallet_context", wallet_evidence is not None, critical=False),
            _source_health("intelligence_fusion", fusion.get("available") is True, critical=False),
        ]
        result = {
            "key": key,
            "evaluated_at": now_iso,
            "chain": row.get("chain"),
            "token_address": row.get("token_address"),
            "pair_address": row.get("pair_address"),
            "symbol": row.get("base_token_symbol") or row.get("symbol"),
            "revival_score": _f(revival_meta.get("revival_score")),
            "confirmation_score": score,
            "status": status,
            "decision": decision,
            "actionable": status == "PASS",
            "automatic_trade": False,
            "hard_blockers": hard,
            "critical_missing": critical_missing,
            "source_health": source_health,
            "wallet_intel": {
                "status": (base.get("holder_cluster") or {}).get("status", "MISSING"),
                "score": base.get("wallet_forensics_score"),
                "smart_money": (base.get("smart_money_persistence") or {}).get("status", "UNAVAILABLE"),
                "bundle_risk": (base.get("bundle_analysis") or {}).get("level", "UNKNOWN"),
            },
            "flow_quality": flow,
            "liquidity_quality": liquidity,
            "price_structure": base.get("entry_timing") or {},
            "contract_security": security,
            "intelligence_context": fusion,
            "forensics": base,
        }
        results.append(result)

        snapshot = base.get("evidence_snapshot") if isinstance(base.get("evidence_snapshot"), dict) else None
        if snapshot:
            history_map[key] = (history + [snapshot])[-96:]
        prior = cases.get(key) if isinstance(cases.get(key), dict) else {}
        t0_price = prior.get("t0_price_usd")
        if t0_price is None and isinstance(market, dict):
            t0_price = market.get("price_usd")
        cases[key] = {
            "first_investigated_at": prior.get("first_investigated_at") or now_iso,
            "last_investigated_at": now_iso,
            "symbol": result["symbol"],
            "chain": result["chain"],
            "token_address": result["token_address"],
            "pair_address": result["pair_address"],
            "t0_price_usd": t0_price,
            "latest_price_usd": (market or {}).get("price_usd") if isinstance(market, dict) else None,
            "revival_score": result["revival_score"],
            "confirmation_score": result["confirmation_score"],
            "status": status,
            "feature_snapshot": {
                "wallet_forensics_score": base.get("wallet_forensics_score"),
                "entry_timing_score": base.get("entry_timing_score"),
                "flow_quality": flow.get("status"),
                "liquidity_quality": liquidity.get("status"),
                "contract_security": security.get("status"),
                "fusion_status": fusion.get("status"),
                "hard_blockers": hard,
                "critical_missing": critical_missing,
            },
        }

    state_payload = {
        "version": 1,
        "updated_at": now_iso,
        "history": history_map,
        "cases": cases,
        "learning_contract": {
            "forward_snapshots_only": True,
            "no_hindsight": True,
            "no_single_token_auto_tuning": True,
            "automatic_threshold_changes": False,
            "intended_outcomes": ["1h", "6h", "24h", "72h", "max_upside", "drawdown", "liquidity_delta"],
        },
    }
    report = {
        "version": 1,
        "mode": MODE,
        "generated_at": now_iso,
        "candidate_count": len(candidates),
        "pass_count": sum(r["status"] == "PASS" for r in results),
        "watch_count": sum(r["status"] == "WATCH" for r in results),
        "reject_count": sum(r["status"] == "REJECT" for r in results),
        "results": results,
        "truth_contract": {
            "deep_check_before_revival_actionable_alert": True,
            "revival_score_separate_from_confirmation_score": True,
            "critical_source_failure_cannot_pass": True,
            "hard_blocker_overrides_score": True,
            "social_news_context_is_advisory_until_exact_pair_current_evidence_exists": True,
            "buy_sell_counts_not_claimed_as_organic_usd_flow": True,
            "manual_decision_only": True,
            "automatic_trade": False,
            "no_single_token_auto_tuning": True,
        },
    }
    _write(state_path, state_payload)
    _write(out / REPORT, report)
    return report


def result_index(report: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(report, dict):
        return {}
    return {str(x.get("key")): x for x in (report.get("results") or []) if isinstance(x, dict) and x.get("key")}
