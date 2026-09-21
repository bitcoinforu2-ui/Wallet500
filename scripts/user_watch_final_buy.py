from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
WATCH_STATE = ROOT / "data/unified-watch-state.json"
WATCH_REPORT = ROOT / "data/unified-watch-intelligence-report.json"
DYNAMIC = ROOT / "data/unified-dynamic-candidates.json"
STATE = ROOT / "data/user-watch-final-buy-state.json"
REPORT = ROOT / "data/user-watch-final-buy-report.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
POLICY_MODE = "USER_REQUESTED_UNIFIED_WATCH_FINAL_BUY_V1"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def outbox_event_id(event_type: str, identity: str, episode: int) -> str:
    material = f"{str(event_type).upper()}|{identity}|{int(episode)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def now_iso() -> str:
    return now_utc().isoformat()


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def num(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError, OverflowError):
        return default


def parse_dt(value: Any) -> datetime | None:
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
    except (TypeError, ValueError):
        return None


def age_seconds(value: Any, now: datetime) -> float | None:
    dt = parse_dt(value)
    if dt is None:
        return None
    return (now - dt).total_seconds()


def chain_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return ALIASES.get(raw, raw)


def norm(chain: str, value: Any) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def identity_key(row: dict) -> str:
    existing = str(row.get("identity_key") or "").strip()
    scope = str(row.get("execution_identity_scope") or "").upper()
    if scope == "EXACT_CEX_MARKET" or existing.startswith("cex:"):
        if existing.startswith("cex:"):
            return existing
        exchange = str(row.get("exchange") or "").lower().strip()
        market = str(row.get("currency_pair") or "").upper().strip()
        return f"cex:{exchange}:{market}" if exchange and market else ""
    chain = chain_name(row.get("chain") or row.get("network"))
    token = norm(chain, row.get("token_address") or row.get("token") or row.get("contract") or row.get("mint"))
    pair = norm(chain, row.get("pair_address") or row.get("pair") or row.get("exact_pair"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def eligible_targets(
    config: dict,
    dynamic: dict | None = None,
    watch_state: dict | None = None,
) -> list[dict]:
    rows = []
    seen = set()
    for row in config.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        if row.get("user_watch_final_buy_lane") is not True:
            continue
        if str(row.get("telegram_policy") or "").upper() != "FINAL_BUY_ONLY":
            continue
        if row.get("exact_identity_required") is not True or row.get("exact_pair_required") is not True:
            continue
        key = identity_key(row)
        if key and key not in seen:
            seen.add(key)
            rows.append(row)

    # Dynamic lanes can enter only the same strict FINAL BUY gate.
    # +25% CEX movement is an arming condition for revalidation, never a BUY by itself.
    for row in (dynamic or {}).get("candidates") or []:
        if not isinstance(row, dict):
            continue
        ctype = str(row.get("candidate_type") or "").upper()
        key = identity_key(row)
        if not key or key in seen:
            continue

        if ctype == "NEW_CHAIN_BOOTSTRAP":
            if row.get("bootstrap_final_buy_lane") is not True:
                continue
            seen.add(key)
            rows.append(row)
            continue

        if ctype not in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY"}:
            continue
        live = market_row(watch_state or {}, key)
        if not isinstance(live, dict) or live.get("quarter_wave_revalidation_armed") is not True:
            continue

        target = dict(row)
        target.update({
            "user_watch_final_buy_lane": True,
            "telegram_policy": "FINAL_BUY_ONLY",
            "exact_identity_required": ctype != "CEX_MARKET_DISCOVERY",
            "exact_pair_required": ctype != "CEX_MARKET_DISCOVERY",
            "exact_cex_market_required": ctype == "CEX_MARKET_DISCOVERY",
            "quarter_wave_revalidation_lane": True,
            "quarter_wave_anchor_price_usd": live.get("first_verified_price"),
            "quarter_wave_gain_from_anchor_pct": live.get("gain_from_first_verified_pct"),
            "quarter_wave_armed_at": live.get("quarter_wave_revalidation_armed_at"),
            "quarter_wave_trigger_price_usd": live.get("quarter_wave_revalidation_trigger_price"),
        })
        seen.add(key)
        rows.append(target)

    # Armed +25% CEX candidates remain in FINAL-BUY revalidation even after
    # they fall out of the current mover list. The exact identity comes from
    # the persisted Unified Watch market state.
    state_rows = (watch_state or {}).get("tokens") if isinstance(watch_state, dict) else {}
    for live in state_rows.values() if isinstance(state_rows, dict) else []:
        if not isinstance(live, dict):
            continue
        if live.get("dynamic_spot_candidate") is not True:
            continue
        if live.get("quarter_wave_revalidation_armed") is not True:
            continue
        key = identity_key(live)
        if not key or key in seen:
            continue
        target = {
            "candidate_type": str(live.get("candidate_type") or "GATE_SPOT_DISCOVERY").upper(),
            "symbol": str(live.get("symbol") or "CEX").upper(),
            "network": live.get("network"),
            "contract": live.get("contract"),
            "pair": live.get("pair"),
            "exchange": live.get("exchange"),
            "currency_pair": live.get("currency_pair"),
            "execution_identity_scope": live.get("execution_identity_scope"),
            "identity_key": live.get("identity_key"),
            "dex_url": live.get("dex_url") or "",
            "source": live.get("source") or "Persisted +25% CEX Revalidation",
            "source_url": live.get("source_url") or "",
            "first_seen_at": live.get("first_seen_at"),
            "discovery_price": live.get("discovery_price"),
            "user_watch_final_buy_lane": True,
            "telegram_policy": "FINAL_BUY_ONLY",
            "exact_identity_required": str(live.get("execution_identity_scope") or "").upper() != "EXACT_CEX_MARKET",
            "exact_pair_required": str(live.get("execution_identity_scope") or "").upper() != "EXACT_CEX_MARKET",
            "exact_cex_market_required": str(live.get("execution_identity_scope") or "").upper() == "EXACT_CEX_MARKET",
            "quarter_wave_revalidation_lane": True,
            "quarter_wave_anchor_price_usd": live.get("first_verified_price"),
            "quarter_wave_gain_from_anchor_pct": live.get("gain_from_first_verified_pct"),
            "quarter_wave_armed_at": live.get("quarter_wave_revalidation_armed_at"),
            "quarter_wave_trigger_price_usd": live.get("quarter_wave_revalidation_trigger_price"),
        }
        seen.add(key)
        rows.append(target)
    return rows


def market_row(state: dict, key: str) -> dict | None:
    rows = state.get("tokens") if isinstance(state, dict) else {}
    if not isinstance(rows, dict):
        return None
    for row in rows.values():
        if isinstance(row, dict) and str(row.get("identity_key") or "") == key:
            return row
    return None


def report_row(report: dict, key: str) -> dict | None:
    for row in (report.get("targets") or []) if isinstance(report, dict) else []:
        if isinstance(row, dict) and str(row.get("identity_key") or "") == key:
            return row
    return None


def _policy(config: dict) -> dict:
    p = dict(config.get("user_watch_final_buy_policy") or {})
    defaults = {
        "enabled": True,
        "max_source_spread_pct": 2.0,
        "max_snapshot_age_seconds": 2100,
        "min_liquidity_usd": 50000.0,
        "min_volume_h1_usd": 15000.0,
        "min_activity_h1": 50,
        "min_buy_sell_ratio": 1.20,
        "min_rebound_from_watch_low_pct": 5.0,
        "min_scan_price_gain_pct": 1.0,
        "max_scan_price_gain_pct": 25.0,
        "strong_min_fusion_score": 55.0,
        "strong_min_positive_families": 3,
        "relaxed_min_fusion_score": 30.0,
        "relaxed_min_positive_families": 2,
        "relaxed_min_wallet_or_holder_score": 3.0,
        "min_current_evidence": 2,
        "required_consecutive_qualified_scans": 2,
        "rearm_after_observable_misses": 2,
        "telegram_final_buy_only": False,
        "telegram_pre_buy_enabled": True,
        "automatic_trade": False,
        "cex_quarter_wave_fast_path_enabled": True,
        "cex_quarter_wave_min_turnover_usd": 20000.0,
        "cex_quarter_wave_min_relative_volume_multiple": 4.0,
        "cex_quarter_wave_max_gainer_rank": 15,
        "cex_quarter_wave_min_microstructure_score": 5.0,
        "cex_quarter_wave_min_current_evidence": 2,
        "cex_max_market_price_spread_pct": 2.0,
        "cex_quarter_wave_absolute_turnover_fallback_usd": 100000.0,
        "cex_quarter_wave_min_depth_1pct_usd": 3000.0,
        "cex_quarter_wave_max_orderbook_spread_pct": 1.5,
        "cex_quarter_wave_min_bid_ask_depth_ratio": 1.05,
        "cex_market_only_min_turnover_usd": 30000.0,
        "cex_market_only_min_relative_volume_multiple": 4.0,
        "cex_market_only_max_gainer_rank": 10,
        "cex_market_only_min_current_evidence": 2,
        "cex_market_only_min_depth_1pct_usd": 10000.0,
        "cex_market_only_max_orderbook_spread_pct": 1.0,
        "cex_market_only_min_bid_ask_depth_ratio": 1.10,
        "cex_breakout_continuation_enabled": True,
        "cex_breakout_min_turnover_usd": 150000.0,
        "cex_breakout_min_relative_volume_multiple": 4.0,
        "cex_breakout_max_gainer_rank": 8,
        "cex_breakout_min_depth_1pct_usd": 5000.0,
        "cex_breakout_max_orderbook_spread_pct": 0.75,
        "cex_breakout_extreme_min_turnover_usd": 500000.0,
        "cex_breakout_extreme_min_relative_volume_multiple": 6.0,
        "cex_breakout_extreme_max_gainer_rank": 3,
        "cex_breakout_extreme_min_depth_1pct_usd": 3000.0,
        "cex_breakout_extreme_max_orderbook_spread_pct": 0.50,
        "cex_breakout_min_scan_gain_pct": 0.50,
        "cex_breakout_min_rebound_pct": 5.0,
        "cex_breakout_min_holder_score": -7.0,
        "cex_breakout_min_bid_ask_depth_ratio": 0.50,
        "cex_breakout_min_current_evidence": 1,
        "hybrid_breakout_enabled": True,
        "hybrid_breakout_min_cex_turnover_usd": 100000.0,
        "hybrid_breakout_min_relative_volume_multiple": 4.0,
        "hybrid_breakout_max_gainer_rank": 5,
        "hybrid_breakout_min_dex_liquidity_usd": 150000.0,
        "hybrid_breakout_min_dex_volume_h1_usd": 100000.0,
        "hybrid_breakout_min_activity_h1": 500,
        "hybrid_breakout_min_buy_sell_ratio": 0.85,
        "hybrid_breakout_min_microstructure_score": 10.0,
        "hybrid_breakout_min_scan_gain_pct": 1.0,
        "hybrid_breakout_min_current_evidence": 2,
        "hybrid_breakout_min_holder_score": -7.0,
    }
    for k, v in defaults.items():
        p.setdefault(k, v)
    return p


def evaluate(
    target: dict,
    market: dict | None,
    observed: dict | None,
    prior: dict | None,
    policy: dict,
    *,
    now: datetime | None = None,
) -> tuple[dict, dict]:
    now = (now or now_utc()).astimezone(timezone.utc)
    prior = dict(prior or {})
    key = identity_key(target)
    blockers: list[str] = []
    proof: list[str] = []
    quarter_wave_lane = bool(target.get("quarter_wave_revalidation_lane"))
    quarter_wave_anchor = num(target.get("quarter_wave_anchor_price_usd"), 0.0) or 0.0
    quarter_wave_gain = num(target.get("quarter_wave_gain_from_anchor_pct"))

    if not key:
        blockers.append("EXACT_IDENTITY_MISSING")
    if market is None:
        blockers.append("MARKET_STATE_MISSING")
    if observed is None:
        blockers.append("WATCH_REPORT_ROW_MISSING")

    report_verified = bool(observed and observed.get("market_verified") is True)
    if not report_verified:
        blockers.append("EXACT_PAIR_NOT_VERIFIED_THIS_SCAN")

    report_age = age_seconds((observed or {}).get("observed_at") or (observed or {}).get("updated_at"), now)
    injected_report_age = num((observed or {}).get("_report_age_seconds"))
    if report_age is None:
        report_age = injected_report_age
    max_age = float(policy["max_snapshot_age_seconds"])
    if report_age is None or report_age < -120 or report_age > max_age:
        blockers.append("WATCH_REPORT_STALE_OR_UNTIMED")

    market_age = age_seconds((market or {}).get("observed_at"), now)
    if market_age is None or market_age < -120 or market_age > max_age:
        blockers.append("MARKET_SNAPSHOT_STALE_OR_UNTIMED")

    market_key = str((market or {}).get("identity_key") or "")
    if market is not None and market_key != key:
        blockers.append("MARKET_IDENTITY_MISMATCH")

    price = num((market or {}).get("price"), 0.0) or 0.0
    liquidity = num((market or {}).get("liquidity"), 0.0) or 0.0
    volume_h1 = num((market or {}).get("volume_h1"), 0.0) or 0.0
    buys = int(num((market or {}).get("buys_h1"), 0.0) or 0)
    sells = int(num((market or {}).get("sells_h1"), 0.0) or 0)
    activity = buys + sells
    ratio = (buys + 1.0) / (sells + 1.0)
    spread = num((market or {}).get("spread_pct"), 999.0) or 999.0
    cex_turnover = num((market or {}).get("cex_quote_volume_24h_usd"), 0.0) or 0.0
    cex_relative_multiple = num((market or {}).get("cex_relative_volume_multiple"), 0.0) or 0.0
    cex_rank_raw = num((market or {}).get("positive_gainer_rank"))
    cex_rank = int(cex_rank_raw) if cex_rank_raw is not None and cex_rank_raw > 0 else None
    cex_led = bool((market or {}).get("cex_led_revival"))
    cex_execution_verified = bool((market or {}).get("cex_execution_verified"))
    cex_execution_scope = str((market or {}).get("cex_execution_scope") or target.get("execution_identity_scope") or "").upper()
    single_source_degraded = bool((market or {}).get("single_source_degraded"))
    price_source_count = int(
        num((market or {}).get("price_source_count"), 1 if single_source_degraded else 2)
        or (1 if single_source_degraded else 2)
    )
    cex_market_price_spread = num((market or {}).get("cex_market_price_spread_pct"))
    cex_orderbook_spread = num((market or {}).get("cex_orderbook_spread_pct"), 999.0) or 999.0
    cex_depth_1pct = num((market or {}).get("cex_depth_1pct_usd"), 0.0) or 0.0
    cex_bid_ask_depth_ratio = num((market or {}).get("cex_bid_ask_depth_ratio"), 0.0) or 0.0
    cex_market_only = (
        str(target.get("execution_identity_scope") or "").upper() == "EXACT_CEX_MARKET"
        or key.startswith("cex:")
    )
    cex_price_coherent = bool(
        cex_market_only
        or (
            cex_execution_verified
            and (
                (price_source_count >= 2 and cex_market_price_spread is None)
                or (
                    cex_market_price_spread is not None
                    and cex_market_price_spread <= float(policy["cex_max_market_price_spread_pct"])
                )
            )
        )
    )

    if price <= 0:
        blockers.append("PRICE_MISSING")
    if spread > float(policy["max_source_spread_pct"]):
        blockers.append("PRICE_SOURCE_SPREAD_TOO_WIDE")
    if not cex_market_only and price_source_count < 2 and not cex_price_coherent:
        blockers.append("PRICE_SOURCE_REDUNDANCY_MISSING")
    if (
        not cex_market_only
        and cex_execution_verified
        and cex_market_price_spread is not None
        and cex_market_price_spread > float(policy["cex_max_market_price_spread_pct"])
    ):
        blockers.append("CEX_DEX_PRICE_DIVERGENCE")
    if liquidity < float(policy["min_liquidity_usd"]):
        blockers.append("LIQUIDITY_BELOW_FINAL_BUY_FLOOR")
    if volume_h1 < float(policy["min_volume_h1_usd"]):
        blockers.append("VOLUME_H1_TOO_LOW")
    if activity < int(policy["min_activity_h1"]):
        blockers.append("ACTIVITY_H1_TOO_LOW")
    if ratio < float(policy["min_buy_sell_ratio"]):
        blockers.append("BUY_FLOW_NOT_CONFIRMED")

    intel = (observed or {}).get("intelligence") if isinstance((observed or {}).get("intelligence"), dict) else {}
    status = str(intel.get("status") or "").upper()
    score = num(intel.get("score"), 0.0) or 0.0
    families = int(num(intel.get("families") or intel.get("independent_positive_families"), 0.0) or 0)
    evidence = int(num(intel.get("current_evidence_count"), 0.0) or 0)
    intel_age = num(intel.get("evidence_age_minutes"))
    hard_risks = [str(x) for x in (intel.get("hard_risks") or []) if str(x).strip()]
    family_scores = intel.get("family_scores") if isinstance(intel.get("family_scores"), dict) else {}
    wallet = num(family_scores.get("wallet_flow"), 0.0) or 0.0
    holder = num(family_scores.get("holder_network"), 0.0) or 0.0
    micro = num(family_scores.get("market_microstructure"), 0.0) or 0.0

    if status != "CURRENT":
        blockers.append("INTELLIGENCE_NOT_CURRENT")
    if intel_age is None or intel_age < 0 or intel_age * 60 > max_age:
        blockers.append("INTELLIGENCE_STALE_OR_UNTIMED")
    if evidence < int(policy["min_current_evidence"]):
        blockers.append("CURRENT_EVIDENCE_TOO_LOW")
    if hard_risks:
        blockers.append("HARD_RISK_PRESENT")
    if micro <= 0:
        blockers.append("MARKET_MICROSTRUCTURE_NOT_POSITIVE")

    strong = (
        score >= float(policy["strong_min_fusion_score"])
        and families >= int(policy["strong_min_positive_families"])
    )
    relaxed = (
        score >= float(policy["relaxed_min_fusion_score"])
        and families >= int(policy["relaxed_min_positive_families"])
        and max(wallet, holder) >= float(policy["relaxed_min_wallet_or_holder_score"])
    )
    if strong:
        proof.append(f"STRONG_FUSION_{score:.1f}_{families}F")
    elif relaxed:
        proof.append(f"FUSION_PLUS_WALLET_HOLDER_{score:.1f}_{families}F")
    else:
        blockers.append("FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET")

    cex_momentum_confirmed = bool(
        cex_relative_multiple >= float(policy["cex_quarter_wave_min_relative_volume_multiple"])
        or (
            cex_turnover >= float(policy["cex_quarter_wave_absolute_turnover_fallback_usd"])
            and cex_rank is not None
            and cex_rank <= int(policy["cex_quarter_wave_max_gainer_rank"])
        )
    )

    cex_quarter_wave_fast_path = bool(
        quarter_wave_lane
        and not cex_market_only
        and policy.get("cex_quarter_wave_fast_path_enabled") is True
        and report_verified
        and status == "CURRENT"
        and evidence >= int(policy["cex_quarter_wave_min_current_evidence"])
        and not hard_risks
        and micro >= float(policy["cex_quarter_wave_min_microstructure_score"])
        and spread <= float(policy["max_source_spread_pct"])
        and cex_execution_verified
        and cex_price_coherent
        and cex_depth_1pct >= float(policy["cex_quarter_wave_min_depth_1pct_usd"])
        and cex_orderbook_spread <= float(policy["cex_quarter_wave_max_orderbook_spread_pct"])
        and cex_bid_ask_depth_ratio >= float(policy["cex_quarter_wave_min_bid_ask_depth_ratio"])
        and cex_turnover >= float(policy["cex_quarter_wave_min_turnover_usd"])
        and cex_momentum_confirmed
        and cex_rank is not None
        and cex_rank <= int(policy["cex_quarter_wave_max_gainer_rank"])
    )

    cex_market_only_fast_path = bool(
        quarter_wave_lane
        and cex_market_only
        and report_verified
        and cex_execution_verified
        and status == "CURRENT"
        and intel_age is not None
        and 0 <= intel_age * 60 <= max_age
        and evidence >= int(policy["cex_market_only_min_current_evidence"])
        and not hard_risks
        and cex_turnover >= float(policy["cex_market_only_min_turnover_usd"])
        and cex_relative_multiple >= float(policy["cex_market_only_min_relative_volume_multiple"])
        and cex_rank is not None
        and cex_rank <= int(policy["cex_market_only_max_gainer_rank"])
        and cex_depth_1pct >= float(policy["cex_market_only_min_depth_1pct_usd"])
        and cex_orderbook_spread <= float(policy["cex_market_only_max_orderbook_spread_pct"])
        and cex_bid_ask_depth_ratio >= float(policy["cex_market_only_min_bid_ask_depth_ratio"])
    )

    if cex_quarter_wave_fast_path:
        bypass = {
            "LIQUIDITY_BELOW_FINAL_BUY_FLOOR",
            "VOLUME_H1_TOO_LOW",
            "ACTIVITY_H1_TOO_LOW",
            # This lane already requires positive executable CEX bid/ask depth,
            # so a thin DEX buy/sell count must not veto the CEX execution signal.
            "BUY_FLOW_NOT_CONFIRMED",
            "PRICE_SOURCE_REDUNDANCY_MISSING",
            "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET",
        }
        blockers = [b for b in blockers if b not in bypass]
        proof.append(
            f"CEX_QUARTER_WAVE_FAST_PATH_VOL_{cex_turnover:.0f}"
            f"_REL_{cex_relative_multiple:.2f}X_RANK_{cex_rank}"
        )

    if cex_market_only_fast_path:
        bypass = {
            "LIQUIDITY_BELOW_FINAL_BUY_FLOOR",
            "VOLUME_H1_TOO_LOW",
            "ACTIVITY_H1_TOO_LOW",
            "BUY_FLOW_NOT_CONFIRMED",
            "MARKET_MICROSTRUCTURE_NOT_POSITIVE",
            "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET",
        }
        blockers = [b for b in blockers if b not in bypass]
        proof.append(
            f"EXACT_CEX_MARKET_FAST_PATH_VOL_{cex_turnover:.0f}"
            f"_REL_{cex_relative_multiple:.2f}X_RANK_{cex_rank}"
        )
        proof.append(
            f"CEX_DEPTH_{cex_depth_1pct:.0f}_SPREAD_{cex_orderbook_spread:.3f}PCT"
            f"_BIDASK_{cex_bid_ask_depth_ratio:.2f}X"
        )

    previous_price = num(prior.get("last_price"))
    previous_low = num(prior.get("watch_low_price"))
    low = price if price > 0 and previous_low is None else previous_low
    if price > 0 and low is not None:
        low = min(low, price)
    rebound = ((price / low) - 1.0) * 100.0 if price > 0 and low and low > 0 else None
    scan_gain = ((price / previous_price) - 1.0) * 100.0 if price > 0 and previous_price and previous_price > 0 else None

    if previous_price is None:
        blockers.append("NEED_SECOND_VERIFIED_SCAN")
    if rebound is None or rebound < float(policy["min_rebound_from_watch_low_pct"]):
        blockers.append("REBOUND_FROM_WATCH_LOW_NOT_CONFIRMED")
    if scan_gain is None or scan_gain < float(policy["min_scan_price_gain_pct"]):
        blockers.append("SHORT_TERM_PRICE_RECLAIM_NOT_CONFIRMED")
    if scan_gain is not None and scan_gain > float(policy["max_scan_price_gain_pct"]):
        blockers.append("SHORT_TERM_CHASE_RISK")

    # Strong CEX continuation can substitute for weak DEX microstructure, but only
    # when the exact CEX market is executable, the move is still advancing, current
    # intelligence exists, and no hard risk is present. This catches PTB/R2/ASP-like
    # moves without turning a headline percentage into a BUY.
    cex_breakout_standard = bool(
        cex_turnover >= float(policy["cex_breakout_min_turnover_usd"])
        and cex_relative_multiple >= float(policy["cex_breakout_min_relative_volume_multiple"])
        and cex_rank is not None
        and cex_rank <= int(policy["cex_breakout_max_gainer_rank"])
        and cex_depth_1pct >= float(policy["cex_breakout_min_depth_1pct_usd"])
        and cex_orderbook_spread <= float(policy["cex_breakout_max_orderbook_spread_pct"])
    )
    cex_breakout_extreme = bool(
        cex_turnover >= float(policy["cex_breakout_extreme_min_turnover_usd"])
        and cex_relative_multiple >= float(policy["cex_breakout_extreme_min_relative_volume_multiple"])
        and cex_rank is not None
        and cex_rank <= int(policy["cex_breakout_extreme_max_gainer_rank"])
        and cex_depth_1pct >= float(policy["cex_breakout_extreme_min_depth_1pct_usd"])
        and cex_orderbook_spread <= float(policy["cex_breakout_extreme_max_orderbook_spread_pct"])
    )
    cex_breakout_continuation = bool(
        policy.get("cex_breakout_continuation_enabled") is True
        and quarter_wave_lane
        and not cex_market_only
        and report_verified
        and cex_execution_verified
        and cex_price_coherent
        and cex_bid_ask_depth_ratio >= float(policy["cex_breakout_min_bid_ask_depth_ratio"])
        and status == "CURRENT"
        and evidence >= int(policy["cex_breakout_min_current_evidence"])
        and not hard_risks
        and holder >= float(policy["cex_breakout_min_holder_score"])
        and (cex_breakout_standard or cex_breakout_extreme)
        and scan_gain is not None
        and scan_gain >= float(policy["cex_breakout_min_scan_gain_pct"])
        and rebound is not None
        and rebound >= float(policy["cex_breakout_min_rebound_pct"])
    )
    if cex_breakout_continuation:
        bypass = {
            "LIQUIDITY_BELOW_FINAL_BUY_FLOOR",
            "VOLUME_H1_TOO_LOW",
            "ACTIVITY_H1_TOO_LOW",
            "BUY_FLOW_NOT_CONFIRMED",
            "CURRENT_EVIDENCE_TOO_LOW",
            "MARKET_MICROSTRUCTURE_NOT_POSITIVE",
            "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET",
        }
        if scan_gain >= float(policy["cex_breakout_min_scan_gain_pct"]):
            bypass.add("SHORT_TERM_PRICE_RECLAIM_NOT_CONFIRMED")
        blockers = [b for b in blockers if b not in bypass]
        proof.append(
            f"CEX_BREAKOUT_CONTINUATION_VOL_{cex_turnover:.0f}"
            f"_REL_{cex_relative_multiple:.2f}X_RANK_{cex_rank}"
            f"_SCAN_{scan_gain:.2f}PCT"
        )

    # Hybrid continuation is for cases like R2: both the exact DEX pool and the
    # exact CEX market are strong, but a single DEX buy/sell ratio or rebound
    # heuristic would otherwise veto a real continuation. It never bypasses
    # hard risk, stale intelligence, price disagreement, weak execution, or the
    # two-scan confirmation requirement.
    hybrid_breakout_continuation = bool(
        policy.get("hybrid_breakout_enabled") is True
        and quarter_wave_lane
        and not cex_market_only
        and report_verified
        and cex_execution_verified
        and cex_price_coherent
        and spread <= float(policy["max_source_spread_pct"])
        and status == "CURRENT"
        and evidence >= int(policy["hybrid_breakout_min_current_evidence"])
        and not hard_risks
        and holder >= float(policy["hybrid_breakout_min_holder_score"])
        and micro >= float(policy["hybrid_breakout_min_microstructure_score"])
        and liquidity >= float(policy["hybrid_breakout_min_dex_liquidity_usd"])
        and volume_h1 >= float(policy["hybrid_breakout_min_dex_volume_h1_usd"])
        and activity >= int(policy["hybrid_breakout_min_activity_h1"])
        and ratio >= float(policy["hybrid_breakout_min_buy_sell_ratio"])
        and cex_turnover >= float(policy["hybrid_breakout_min_cex_turnover_usd"])
        and cex_relative_multiple >= float(policy["hybrid_breakout_min_relative_volume_multiple"])
        and cex_rank is not None
        and cex_rank <= int(policy["hybrid_breakout_max_gainer_rank"])
        and scan_gain is not None
        and scan_gain >= float(policy["hybrid_breakout_min_scan_gain_pct"])
    )
    if hybrid_breakout_continuation:
        bypass = {
            "BUY_FLOW_NOT_CONFIRMED",
            "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET",
            "REBOUND_FROM_WATCH_LOW_NOT_CONFIRMED",
        }
        blockers = [b for b in blockers if b not in bypass]
        proof.append(
            f"HYBRID_CEX_DEX_BREAKOUT_LIQ_{liquidity:.0f}"
            f"_VOL1H_{volume_h1:.0f}_ACT_{activity}"
            f"_REL_{cex_relative_multiple:.2f}X_RANK_{cex_rank}"
            f"_SCAN_{scan_gain:.2f}PCT"
        )

    observable = bool(
        market is not None
        and observed is not None
        and report_verified
        and market_age is not None
        and -120 <= market_age <= max_age
        and report_age is not None
        and -120 <= report_age <= max_age
        and market_key == key
    )

    unique_blockers = sorted(set(blockers))
    qualified = not unique_blockers
    prior_streak = int(prior.get("qualified_streak") or 0)
    streak = prior_streak + 1 if qualified else 0
    required_streak = max(1, int(policy["required_consecutive_qualified_scans"]))
    final_buy = qualified and streak >= required_streak

    armed = bool(prior.get("armed", True))
    miss_streak = int(prior.get("observable_miss_streak") or 0)
    if qualified:
        miss_streak = 0
    elif observable:
        miss_streak += 1
        if miss_streak >= max(1, int(policy["rearm_after_observable_misses"])):
            armed = True

    alert = bool(final_buy and armed)
    if alert:
        armed = False

    # Strict PRE-BUY: every current market/intelligence/safety gate passed,
    # with exactly one configured confirmation scan remaining before FINAL BUY.
    pre_buy_armed = bool(prior.get("pre_buy_armed", True))
    if (
        observable
        and not qualified
        and miss_streak >= max(1, int(policy["rearm_after_observable_misses"]))
    ):
        pre_buy_armed = True
    pre_buy = bool(
        policy.get("telegram_pre_buy_enabled") is True
        and required_streak > 1
        and qualified
        and not final_buy
        and streak == required_streak - 1
    )
    pre_buy_alert = bool(pre_buy and pre_buy_armed)
    if pre_buy_alert:
        pre_buy_armed = False

    if quarter_wave_lane:
        if quarter_wave_gain is None and quarter_wave_anchor > 0 and price > 0:
            quarter_wave_gain = ((price / quarter_wave_anchor) - 1.0) * 100.0
        proof.append(
            "QUARTER_WAVE_REVALIDATION_ARMED"
            + (f"_{quarter_wave_gain:.2f}PCT" if quarter_wave_gain is not None else "")
        )
    if ratio >= float(policy["min_buy_sell_ratio"]):
        proof.append(f"BUY_SELL_{ratio:.2f}X")
    if rebound is not None and rebound >= float(policy["min_rebound_from_watch_low_pct"]):
        proof.append(f"REBOUND_{rebound:.2f}PCT")
    if scan_gain is not None and float(policy["min_scan_price_gain_pct"]) <= scan_gain <= float(policy["max_scan_price_gain_pct"]):
        proof.append(f"SCAN_GAIN_{scan_gain:.2f}PCT")
    if liquidity >= float(policy["min_liquidity_usd"]):
        proof.append(f"LIQUIDITY_{liquidity:.0f}")
    if report_verified:
        proof.append("EXACT_PAIR_VERIFIED")

    result = {
        "identity_key": key,
        "symbol": str(target.get("symbol") or "").upper(),
        "state": "BUY_ZONE" if final_buy else ("QUALIFYING" if qualified else "WATCH"),
        "recommended_action": "BUY" if final_buy else "WAIT",
        "alert": alert,
        "pre_buy": pre_buy,
        "pre_buy_alert": pre_buy_alert,
        "observable": observable,
        "qualified_this_scan": qualified,
        "qualified_streak": streak,
        "required_streak": required_streak,
        "blockers": unique_blockers,
        "proof": list(dict.fromkeys(proof)),
        "quarter_wave_revalidation": {
            "enabled_for_target": quarter_wave_lane,
            "cex_fast_path": cex_quarter_wave_fast_path,
            "cex_market_only_fast_path": cex_market_only_fast_path,
            "cex_breakout_continuation": cex_breakout_continuation,
            "hybrid_breakout_continuation": hybrid_breakout_continuation,
            "anchor_price_usd": quarter_wave_anchor if quarter_wave_anchor > 0 else None,
            "gain_from_anchor_pct": round(quarter_wave_gain, 4) if quarter_wave_gain is not None else None,
            "armed_at": target.get("quarter_wave_armed_at"),
            "trigger_price_usd": target.get("quarter_wave_trigger_price_usd"),
            "trigger_is_buy_signal": False,
        },
        "market": {
            "price_usd": price,
            "liquidity_usd": liquidity,
            "volume_h1_usd": volume_h1,
            "buys_h1": buys,
            "sells_h1": sells,
            "buy_sell_ratio": round(ratio, 4),
            "activity_h1": activity,
            "spread_pct": spread,
            "cex_turnover_24h_usd": cex_turnover,
            "cex_relative_volume_multiple": cex_relative_multiple,
            "cex_gainer_rank": cex_rank,
            "cex_led_revival": cex_led,
            "cex_execution_verified": cex_execution_verified,
            "cex_execution_scope": cex_execution_scope,
            "price_source_count": price_source_count,
            "single_source_degraded": single_source_degraded,
            "cex_market_price_spread_pct": cex_market_price_spread,
            "cex_price_coherent": cex_price_coherent,
            "cex_orderbook_spread_pct": cex_orderbook_spread,
            "cex_depth_1pct_usd": cex_depth_1pct,
            "cex_bid_ask_depth_ratio": cex_bid_ask_depth_ratio,
            "scan_price_gain_pct": round(scan_gain, 4) if scan_gain is not None else None,
            "rebound_from_watch_low_pct": round(rebound, 4) if rebound is not None else None,
        },
        "intelligence": {
            "status": status,
            "score": score,
            "positive_families": families,
            "current_evidence_count": evidence,
            "evidence_age_minutes": intel_age,
            "hard_risks": hard_risks,
            "wallet_flow_score": wallet,
            "holder_network_score": holder,
            "market_microstructure_score": micro,
        },
        "truth_contract": {
            "exact_chain_contract_pair_required": not cex_market_only,
            "exact_cex_market_identity_required": cex_market_only,
            "two_scan_confirmation_required": required_streak >= 2,
            "telegram_final_buy_only": False,
            "telegram_pre_buy_enabled": bool(policy.get("telegram_pre_buy_enabled")),
            "pre_buy_requires_all_current_gates_passed": True,
            "pre_buy_is_one_confirmation_scan_before_final_buy": True,
            "manual_decision_only": True,
            "automatic_trade": False,
            "quarter_wave_revalidation_lane": quarter_wave_lane,
            "quarter_wave_trigger_is_not_buy": True,
            "all_hard_safety_gates_still_required": True,
            "contextual_execution_gates_may_be_satisfied_by_verified_alternate_path": True,
            "cex_fast_path_bypasses_only_replaceable_dex_and_fusion_gates": True,
            "cex_fast_path_still_requires_current_intelligence_no_hard_risk_microstructure_and_two_scans": True,
            "cex_market_only_fast_path_requires_fresh_current_intelligence": True,
            "cex_breakout_continuation_requires_current_intelligence": True,
            "cex_breakout_continuation_requires_exact_cex_execution": True,
            "cex_breakout_continuation_never_bypasses_hard_risk": True,
            "hybrid_breakout_requires_exact_cex_and_dex_execution": True,
            "hybrid_breakout_never_bypasses_hard_risk_or_price_coherence": True,
            "hybrid_breakout_keeps_two_scan_confirmation": True,
            "does_not_modify_veteran_real_alert_policy": True,
        },
    }

    next_state = {
        **prior,
        "identity_key": key,
        "symbol": result["symbol"],
        "last_seen_at": now.isoformat(),
        "last_price": price if price > 0 else prior.get("last_price"),
        "last_liquidity": liquidity,
        "last_volume_h1": volume_h1,
        "watch_low_price": low if low is not None else prior.get("watch_low_price"),
        "watch_high_price": max(num(prior.get("watch_high_price"), 0.0) or 0.0, price),
        "qualified_streak": streak,
        "observable_miss_streak": miss_streak,
        "armed": armed,
        "pre_buy_armed": pre_buy_armed,
        "last_state": result["state"],
        "last_blockers": unique_blockers,
    }
    if not next_state.get("first_seen_at"):
        next_state["first_seen_at"] = now.isoformat()
    if pre_buy_alert:
        next_state["last_pre_buy_alert_at"] = now.isoformat()
        next_state["last_pre_buy_alert_price"] = price
        next_state["pre_buy_episode_count"] = int(prior.get("pre_buy_episode_count") or 0) + 1

    if alert:
        next_state["last_alert_at"] = now.isoformat()
        next_state["last_alert_price"] = price
        next_state["buy_episode_count"] = int(prior.get("buy_episode_count") or 0) + 1

    return result, next_state


def telegram_message(target: dict, decision: dict) -> str:
    m = decision["market"]
    intel = decision["intelligence"]
    dex = str(target.get("dex_url") or "")
    if decision.get("pre_buy_alert") is True:
        return "\n".join([
            f"🟠⚡ רגע לפני קנייה / PRE-BUY — {decision['symbol']} — WALLET500",
            "כל השערים הנוכחיים עברו ✅",
            "חסרה רק סריקת אישור רצופה אחת לפני FINAL BUY.",
            f"Price USD: {m['price_usd']:.10f}",
            f"Liquidity USD: {m['liquidity_usd']:,.0f} | Vol 1H USD: {m['volume_h1_usd']:,.0f}",
            f"Buys/Sells 1H: {m['buys_h1']}/{m['sells_h1']} ({m['buy_sell_ratio']:.2f}x)",
            f"Rebound from watch low: {m['rebound_from_watch_low_pct']:.2f}%",
            f"Scan-to-scan price gain: {m['scan_price_gain_pct']:.2f}%",
            f"Intelligence Fusion: {intel['score']:.1f}/100 | {intel['positive_families']} positive families",
            "Proof: " + " | ".join(decision.get("proof") or []),
            "PRE-BUY = confirmation pending; this is not FINAL BUY yet.",
            "Manual decision only. No automatic trade.",
            f"CA: {target.get('contract')}",
            f"Pair: {target.get('pair')}",
            dex,
        ])
    return "\n".join([
        f"🟢🔥 קנייה / BUY — {decision['symbol']} — WALLET500",
        "Unified Watch FINAL BUY ✅",
        f"Price: ${m['price_usd']:.10f}",
        f"Liquidity: ${m['liquidity_usd']:,.0f} | Vol 1H: ${m['volume_h1_usd']:,.0f}",
        f"Buys/Sells 1H: {m['buys_h1']}/{m['sells_h1']} ({m['buy_sell_ratio']:.2f}x)",
        f"Rebound from watch low: {m['rebound_from_watch_low_pct']:.2f}%",
        f"Scan-to-scan price gain: {m['scan_price_gain_pct']:.2f}%",
        f"Intelligence Fusion: {intel['score']:.1f}/100 | {intel['positive_families']} positive families",
        "Proof: " + " | ".join(decision.get("proof") or []),
        (
            "New Chain Bootstrap Radar candidate."
            if str(target.get("candidate_type") or "").upper() == "NEW_CHAIN_BOOTSTRAP"
            else (
                "CEX +25% revalidation candidate; all FINAL BUY gates passed."
                if target.get("quarter_wave_revalidation_lane") is True
                else "Unified user watch candidate."
            )
        ),
        "Manual decision only. No automatic trade.",
        f"CA: {target.get('contract')}",
        f"Pair: {target.get('pair')}",
        dex,
    ])


def main() -> int:
    config = load(CONFIG, {})
    policy = _policy(config)
    if policy.get("enabled") is not True:
        write(REPORT, {
            "version": 1,
            "generated_at": now_iso(),
            "mode": POLICY_MODE,
            "status": "DISABLED",
            "targets": [],
        })
        return 0

    watch_state = load(WATCH_STATE, {})
    watch_report = load(WATCH_REPORT, {})
    dynamic = load(DYNAMIC, {"candidates": []})
    persistent = load(STATE, {"version": 1, "targets": {}})

    upstream = os.environ.get("WALLET500_MARKET_WATCH_OUTCOME", "success").strip().lower()
    if upstream != "success":
        write(STATE, persistent)
        write(REPORT, {
            "version": 1,
            "generated_at": now_iso(),
            "mode": POLICY_MODE,
            "status": "BLOCKED_UPSTREAM_MARKET_WATCH",
            "upstream_outcome": upstream,
            "configured_targets": len(eligible_targets(config, dynamic, watch_state)),
            "buy_zone_count": 0,
            "pre_buy_count": 0,
            "pre_buy_delivered_count": 0,
            "delivered_count": 0,
            "error_count": 0,
            "decisions": [],
            "truth_contract": {
                "fail_closed_on_upstream_failure": True,
                "telegram_final_buy_only": False,
                "telegram_pre_buy_enabled": bool(policy.get("telegram_pre_buy_enabled")),
                "automatic_trade": False,
            },
        })
        print(json.dumps({"status": "BLOCKED_UPSTREAM_MARKET_WATCH", "upstream_outcome": upstream}))
        return 0
    target_state = persistent.get("targets") if isinstance(persistent.get("targets"), dict) else {}
    target_state = dict(target_state)
    delivery_outbox = [
        dict(x) for x in (persistent.get("delivery_outbox") or [])
        if isinstance(x, dict) and x.get("event_id")
    ]
    existing_outbox_ids = {str(x.get("event_id")) for x in delivery_outbox}

    now = now_utc()
    top_report_age = age_seconds(watch_report.get("updated_at"), now)
    decisions: list[dict] = []
    queued_delivery_events: list[str] = []
    errors: list[dict] = []

    for target in eligible_targets(config, dynamic, watch_state):
        key = identity_key(target)
        m = market_row(watch_state, key)
        rr = report_row(watch_report, key)
        if rr is not None:
            rr = dict(rr)
            rr["_report_age_seconds"] = top_report_age
        decision, next_state = evaluate(
            target, m, rr, target_state.get(key), policy, now=now
        )

        if decision.get("pre_buy_alert") is True:
            episode = int(next_state.get("pre_buy_episode_count") or 0)
            event_id = outbox_event_id("UNIFIED_PRE_BUY", key, episode)
            if event_id not in existing_outbox_ids:
                delivery_outbox.append({
                    "event_id": event_id,
                    "alert_type": "UNIFIED_PRE_BUY",
                    "stream_key": f"UNIFIED_PRE_BUY:{key}",
                    "source_token": event_id,
                    "identity_key": key,
                    "symbol": decision.get("symbol"),
                    "created_at": now.isoformat(),
                    "episode": episode,
                    "message": telegram_message(target, decision),
                    "decision_state": decision.get("state"),
                    "manual_decision_only": True,
                    "automatic_trade": False,
                })
                existing_outbox_ids.add(event_id)
                queued_delivery_events.append(event_id)
            next_state["last_pre_buy_delivery_status"] = "PENDING_SHARED_LEDGER"
            next_state["last_pre_buy_delivery_event_id"] = event_id

        if decision.get("alert") is True:
            episode = int(next_state.get("buy_episode_count") or 0)
            event_id = outbox_event_id("UNIFIED_FINAL_BUY", key, episode)
            if event_id not in existing_outbox_ids:
                delivery_outbox.append({
                    "event_id": event_id,
                    "alert_type": "UNIFIED_FINAL_BUY",
                    "stream_key": f"UNIFIED_FINAL_BUY:{key}",
                    "source_token": event_id,
                    "identity_key": key,
                    "symbol": decision.get("symbol"),
                    "created_at": now.isoformat(),
                    "episode": episode,
                    "message": telegram_message(target, decision),
                    "decision_state": decision.get("state"),
                    "manual_decision_only": True,
                    "automatic_trade": False,
                })
                existing_outbox_ids.add(event_id)
                queued_delivery_events.append(event_id)
            next_state["last_delivery_status"] = "PENDING_SHARED_LEDGER"
            next_state["last_delivery_event_id"] = event_id
            next_state["delivery_state_source"] = "telegram-delivery-ledger"

        target_state[key] = next_state
        decisions.append(decision)

    delivery_outbox = delivery_outbox[-2000:]
    persistent = {
        "version": 2,
        "updated_at": now.isoformat(),
        "mode": POLICY_MODE,
        "targets": target_state,
        "delivery_outbox": delivery_outbox,
        "delivery_contract": {
            "sender": "PRODUCTION_TELEGRAM_SHARED_LEDGER_ONLY",
            "direct_telegram_from_scanner": False,
            "outbox_is_durable_until_ledger_dedupe": True,
        },
    }
    write(STATE, persistent)

    report = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": POLICY_MODE,
        "policy": policy,
        "configured_targets": len(eligible_targets(config, dynamic, watch_state)),
        "buy_zone_count": sum(1 for x in decisions if x.get("state") == "BUY_ZONE"),
        "pre_buy_count": sum(1 for x in decisions if x.get("pre_buy") is True),
        "pre_buy_delivered_count": 0,
        "pre_buy_delivered": [],
        "delivered_count": 0,
        "delivered": [],
        "queued_delivery_count": len(queued_delivery_events),
        "queued_delivery_event_ids": queued_delivery_events,
        "delivery_outbox_size": len(delivery_outbox),
        "error_count": len(errors),
        "errors": errors,
        "decisions": decisions,
        "truth_contract": {
            "source": "Unified Watch exact-pair state + current intelligence report",
            "user_requested_targets_new_chain_and_quarter_wave_cex_only": True,
            "new_chain_bootstrap_uses_same_strict_final_buy_gate": True,
            "quarter_wave_cex_uses_same_strict_final_buy_gate": True,
            "quarter_wave_trigger_gain_pct": 25.0,
            "quarter_wave_trigger_is_not_buy": True,
            "telegram_final_buy_only": False,
            "telegram_pre_buy_enabled": bool(policy.get("telegram_pre_buy_enabled")),
            "pre_buy_definition": "ALL_CURRENT_GATES_PASSED_AND_EXACTLY_ONE_CONFIRMATION_SCAN_REMAINS",
            "research_watch_notifications": False,
            "near_buy_notifications": True,
            "generic_near_buy_notifications": False,
            "automatic_trade": False,
            "direct_telegram_from_scanner": False,
            "delivery_via_shared_fail_closed_ledger": True,
            "veteran_production_real_alert_policy_unchanged": True,
        },
    }
    write(REPORT, report)
    print(json.dumps({
        "status": "OK" if not errors else "DELIVERY_ERROR",
        "mode": POLICY_MODE,
        "configured_targets": report["configured_targets"],
        "buy_zone_count": report["buy_zone_count"],
        "pre_buy_count": report["pre_buy_count"],
        "queued_delivery_count": report["queued_delivery_count"],
        "delivery_outbox_size": report["delivery_outbox_size"],
        "error_count": report["error_count"],
    }, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
