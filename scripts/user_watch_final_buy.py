from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
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
CLOSE_INTELLIGENCE = ROOT / "data/close-watch-intelligence.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
POLICY_MODE = "USER_REQUESTED_UNIFIED_WATCH_FINAL_BUY_V1"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
    matches = [
        row for row in rows.values()
        if isinstance(row, dict) and str(row.get("identity_key") or "") == key
    ]
    if not matches:
        return None

    # The same exact identity can arrive through configured/public-alpha/CEX lanes.
    # Never let dict insertion order select an old snapshot over a fresher exact row.
    def freshness(row: dict) -> tuple:
        observed = parse_dt(row.get("observed_at"))
        observed_ts = observed.timestamp() if observed is not None else float("-inf")
        dynamic_spot = 1 if row.get("dynamic_spot_candidate") is True else 0
        cex_context = 1 if (
            row.get("cex_execution_verified") is True
            or (num(row.get("cex_quote_volume_24h_usd"), 0.0) or 0.0) > 0
        ) else 0
        return (observed_ts, dynamic_spot, cex_context)

    return max(matches, key=freshness)


def report_row(report: dict, key: str) -> dict | None:
    for row in (report.get("targets") or []) if isinstance(report, dict) else []:
        if isinstance(row, dict) and str(row.get("identity_key") or "") == key:
            return row
    return None


def close_intelligence_row(doc: dict, key: str) -> dict | None:
    for row in (doc.get("tokens") or []) if isinstance(doc, dict) else []:
        if isinstance(row, dict) and str(row.get("identity_key") or "") == key:
            return row
    return None


def observed_with_fresh_intelligence_fallback(
    observed: dict | None,
    market: dict | None,
    intelligence: dict | None,
    key: str,
    *,
    now: datetime,
    max_age_seconds: float,
) -> dict | None:
    """Repair only report-publication lag using two fresh exact-identity sources.

    Unified Watch state is written only after the live exact pair/market fetch succeeds;
    close-watch intelligence is independently fused by exact identity. If both are fresh
    and agree on the exact key, they may replace a missing/stale report row. This never
    bypasses liquidity, activity, hard-risk, anti-chase, execution-quality, or two-scan
    confirmation gates in evaluate().
    """
    if not isinstance(market, dict) or not isinstance(intelligence, dict):
        return observed
    if str(market.get("identity_key") or "") != key:
        return observed
    if str(intelligence.get("identity_key") or "") != key:
        return observed
    if str(intelligence.get("status") or "").upper() != "CURRENT":
        return observed
    if (num(market.get("price"), 0.0) or 0.0) <= 0:
        return observed

    market_age = age_seconds(market.get("observed_at"), now)
    intel_time = intelligence.get("updated_at") or intelligence.get("freshest_event_at")
    intel_age = age_seconds(intel_time, now)
    if (
        market_age is None or market_age < -120 or market_age > max_age_seconds
        or intel_age is None or intel_age < -120 or intel_age > max_age_seconds
    ):
        return observed

    existing_intel = (
        observed.get("intelligence")
        if isinstance(observed, dict) and isinstance(observed.get("intelligence"), dict)
        else {}
    )
    existing_report_age = age_seconds(
        (observed or {}).get("observed_at") or (observed or {}).get("updated_at"),
        now,
    )
    if existing_report_age is None:
        existing_report_age = num((observed or {}).get("_report_age_seconds"))
    existing_intel_age_minutes = num(existing_intel.get("evidence_age_minutes"))
    existing_is_fresh = bool(
        isinstance(observed, dict)
        and observed.get("market_verified") is True
        and existing_report_age is not None
        and -120 <= existing_report_age <= max_age_seconds
        and str(existing_intel.get("status") or "").upper() == "CURRENT"
        and existing_intel_age_minutes is not None
        and 0 <= existing_intel_age_minutes * 60 <= max_age_seconds
    )
    if existing_is_fresh:
        return observed

    repaired = dict(observed or {})
    repaired.update({
        "identity_key": key,
        "symbol": market.get("symbol") or repaired.get("symbol"),
        "market_verified": True,
        "observed_at": market.get("observed_at"),
        "updated_at": market.get("observed_at"),
        "_fresh_state_intelligence_fallback": True,
        "_fresh_state_intelligence_fallback_source": "UNIFIED_WATCH_STATE_PLUS_CLOSE_WATCH_INTELLIGENCE",
        "intelligence": {
            **intelligence,
            "families": intelligence.get(
                "families",
                intelligence.get("independent_positive_families"),
            ),
        },
    })
    return repaired


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
        # Cumulative anti-chase guard: a small positive scan after a large
        # multi-scan rebound is not a fresh entry. Require a real reset/reclaim
        # unless the exact CEX move is an exceptional top-rank breakout.
        "late_entry_guard_enabled": True,
        "late_entry_max_rebound_without_reset_pct": 30.0,
        "late_entry_reset_pullback_pct": 8.0,
        "late_entry_reclaim_min_scan_gain_pct": 1.0,
        # A reset/reclaim is a short-lived timing credential, not a permanent
        # permission slip for every later positive scan.
        "late_entry_reset_valid_seconds": 3600,
        # PRE-BUY is one warning per opportunity episode. A FINAL BUY must stay
        # near that warning in both price and time, otherwise a fresh reset and
        # reclaim must create a new episode before another PRE-BUY can be sent.
        "pre_buy_episode_ttl_seconds": 3600,
        "pre_buy_max_price_drift_pct": 8.0,
        "pre_buy_rearm_requires_fresh_reset": True,
        "strong_min_fusion_score": 55.0,
        "strong_min_positive_families": 3,
        "relaxed_min_fusion_score": 30.0,
        "relaxed_min_positive_families": 2,
        "relaxed_min_wallet_or_holder_score": 3.0,
        "min_current_evidence": 2,
        "required_consecutive_qualified_scans": 2,
        # A fast hot-candidate recheck may happen inside the same production
        # workflow. It is allowed to shorten the 15-minute scheduler delay, but
        # a second qualified observation must still be separated in real time so
        # an immediate duplicate read cannot manufacture confirmation.
        "min_qualified_scan_spacing_seconds": 180,
        "hot_recheck_delay_seconds": 180,
        "hot_recheck_max_targets": 8,
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
        "cex_market_only_min_depth_1pct_usd": 10000.0,
        "cex_market_only_max_orderbook_spread_pct": 1.0,
        "cex_market_only_min_bid_ask_depth_ratio": 1.10,
        "cex_market_only_min_current_evidence": 2,
        "cex_market_only_min_microstructure_score": 5.0,
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
        "hybrid_breakout_absolute_turnover_fallback_usd": 250000.0,
        "hybrid_breakout_absolute_turnover_max_gainer_rank": 8,
        "hybrid_breakout_max_gainer_rank": 8,
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
    spread_raw = num((market or {}).get("spread_pct"))
    spread = 999.0 if spread_raw is None else spread_raw
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
    cex_orderbook_spread_raw = num((market or {}).get("cex_orderbook_spread_pct"))
    cex_orderbook_spread = (
        999.0 if cex_orderbook_spread_raw is None else cex_orderbook_spread_raw
    )
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
        # Exact-CEX execution can replace DEX execution evidence, but it must
        # never replace current intelligence. Missing/stale intelligence is a
        # fail-closed condition even for the fastest market-only lane.
        and status == "CURRENT"
        and intel_age is not None
        and 0 <= intel_age * 60 <= max_age
        and evidence >= int(policy["cex_market_only_min_current_evidence"])
        and micro >= float(policy["cex_market_only_min_microstructure_score"])
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
            # Fusion score/confluence may be replaced by verified exact-CEX
            # execution, but freshness/evidence/microstructure blockers above
            # are deliberately non-bypassable.
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
    previous_market_at = parse_dt(prior.get("last_market_observed_at"))
    current_market_at = parse_dt((market or {}).get("observed_at"))
    legacy_stale_prior = bool(
        previous_market_at is None
        and "MARKET_SNAPSHOT_STALE_OR_UNTIMED" in (prior.get("last_blockers") or [])
    )
    if legacy_stale_prior or (
        previous_price is not None
        and previous_market_at is not None
        and current_market_at is not None
        and (
            current_market_at < previous_market_at
            or (current_market_at - previous_market_at).total_seconds() > max_age
        )
    ):
        # A known-stale lane/source handoff is not a real scan-to-scan move.
        previous_price = None
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

    # A candidate can look calm scan-to-scan while still being badly extended
    # over the preceding hours (PHA: +38% from the watch low with only +1.69%
    # on the latest scan). Track the episode high and require a meaningful
    # pullback followed by a positive reclaim before treating that as a fresh
    # entry. A reset is only armed after an extension episode has actually
    # existed, so an unrelated old pullback cannot pre-authorize a future chase.
    prior_high = num(prior.get("watch_high_price"), 0.0) or 0.0
    pullback_from_watch_high = (
        max(0.0, (1.0 - (price / prior_high)) * 100.0)
        if price > 0 and prior_high > 0
        else None
    )
    late_entry_extended = bool(
        quarter_wave_lane
        and rebound is not None
        and rebound >= float(policy["late_entry_max_rebound_without_reset_pct"])
    )
    extension_seen_prior = bool(prior.get("late_entry_extension_seen"))
    extension_seen = bool(extension_seen_prior or late_entry_extended)
    reset_seen_prior = bool(prior.get("late_entry_reset_seen"))
    reset_seen_at_prior = parse_dt(prior.get("late_entry_reset_seen_at"))
    reset_valid_seconds = max(1.0, float(policy.get("late_entry_reset_valid_seconds", 3600)))
    reset_age_seconds = (
        (now - reset_seen_at_prior).total_seconds()
        if reset_seen_at_prior is not None
        else None
    )
    # Legacy state only stored a boolean/depth, so it cannot prove WHEN the
    # pullback happened. Fail it closed instead of reusing an hours-old reset.
    reset_prior_valid = bool(
        reset_seen_prior
        and reset_seen_at_prior is not None
        and reset_age_seconds is not None
        and 0 <= reset_age_seconds <= reset_valid_seconds
    )
    reset_now = bool(
        extension_seen
        and pullback_from_watch_high is not None
        and pullback_from_watch_high >= float(policy["late_entry_reset_pullback_pct"])
    )
    reset_seen = bool(reset_prior_valid or reset_now)
    reset_seen_at = now if reset_now else (reset_seen_at_prior if reset_prior_valid else None)
    reset_depth_prior = (
        num(prior.get("late_entry_reset_max_pullback_pct"), 0.0) or 0.0
        if reset_prior_valid
        else 0.0
    )
    reset_depth = max(
        reset_depth_prior,
        pullback_from_watch_high if reset_now and pullback_from_watch_high is not None else 0.0,
    )
    late_entry_reset_reclaim = bool(
        reset_prior_valid
        and scan_gain is not None
        and scan_gain >= float(policy["late_entry_reclaim_min_scan_gain_pct"])
    )

    # PRE-BUY episode guard. The old implementation re-armed PRE-BUY after two
    # ordinary misses and reused a historical reset forever. That allowed the
    # same exact pair to emit another PRE-BUY much higher in the same move.
    last_pre_buy_at = parse_dt(prior.get("last_pre_buy_alert_at"))
    last_pre_buy_price = num(prior.get("last_pre_buy_alert_price"), 0.0) or 0.0
    pre_buy_episode_age_seconds = (
        (now - last_pre_buy_at).total_seconds()
        if last_pre_buy_at is not None
        else None
    )
    pre_buy_price_drift_pct = (
        ((price / last_pre_buy_price) - 1.0) * 100.0
        if price > 0 and last_pre_buy_price > 0
        else None
    )
    pre_buy_episode_ttl = max(1.0, float(policy.get("pre_buy_episode_ttl_seconds", 3600)))
    pre_buy_max_price_drift = max(0.0, float(policy.get("pre_buy_max_price_drift_pct", 8.0)))
    fresh_reset_after_prebuy = bool(
        last_pre_buy_at is not None
        and reset_seen_at_prior is not None
        and reset_seen_at_prior > last_pre_buy_at
        and reset_prior_valid
        and late_entry_reset_reclaim
    )
    open_pre_buy_episode = bool(last_pre_buy_at is not None and not prior.get("last_alert_at"))
    if open_pre_buy_episode and not fresh_reset_after_prebuy:
        if (
            pre_buy_episode_age_seconds is not None
            and pre_buy_episode_age_seconds > pre_buy_episode_ttl
        ):
            blockers.append("PRE_BUY_EPISODE_EXPIRED_REQUIRES_RESET")
        if (
            pre_buy_price_drift_pct is not None
            and pre_buy_price_drift_pct > pre_buy_max_price_drift
        ):
            blockers.append("PRE_BUY_PRICE_CHASE_FROM_ALERT")
        if int(prior.get("pre_buy_episode_count") or 0) > 1:
            blockers.append("PRE_BUY_DUPLICATE_EPISODE_REQUIRES_RESET")

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

    # Preserve the deliberately strict PTB-like exception: a genuinely extreme
    # exact-CEX breakout (top rank, very high relative volume, tight spread and
    # executable depth) may continue without waiting for an 8% reset. Ordinary
    # +25% revalidation/fast-path momentum does not get this exception.
    late_entry_exceptional_continuation = bool(
        cex_breakout_extreme
        and cex_execution_verified
        and cex_price_coherent
        and not hard_risks
        and scan_gain is not None
        and scan_gain >= float(policy["cex_breakout_min_scan_gain_pct"])
    )
    late_entry_chase_risk = bool(
        policy.get("late_entry_guard_enabled") is True
        and late_entry_extended
        and not late_entry_reset_reclaim
        and not late_entry_exceptional_continuation
    )
    if late_entry_chase_risk:
        blockers.append("EXTENDED_MOVE_WAIT_FOR_RESET")

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
    hybrid_cex_momentum_confirmed = bool(
        cex_relative_multiple >= float(policy["hybrid_breakout_min_relative_volume_multiple"])
        or (
            cex_turnover >= float(policy["hybrid_breakout_absolute_turnover_fallback_usd"])
            and cex_rank is not None
            and cex_rank <= int(policy["hybrid_breakout_absolute_turnover_max_gainer_rank"])
        )
    )
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
        and hybrid_cex_momentum_confirmed
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
    required_streak = max(1, int(policy["required_consecutive_qualified_scans"]))
    min_scan_spacing = max(0.0, float(policy.get("min_qualified_scan_spacing_seconds", 180)))
    last_qualified_at = parse_dt(prior.get("last_qualified_scan_at"))
    qualified_spacing_seconds = (
        (now - last_qualified_at).total_seconds()
        if last_qualified_at is not None
        else None
    )
    spacing_satisfied = bool(
        prior_streak <= 0
        or last_qualified_at is None
        or qualified_spacing_seconds is None
        or qualified_spacing_seconds >= min_scan_spacing
    )
    counted_qualified_scan = bool(qualified and (prior_streak <= 0 or spacing_satisfied))
    if qualified:
        streak = prior_streak + 1 if counted_qualified_scan else prior_streak
    else:
        streak = 0
    final_buy = qualified and spacing_satisfied and streak >= required_streak

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
    # Ordinary misses may re-arm FINAL BUY monitoring, but they must never
    # manufacture a second PRE-BUY in the same opportunity episode.
    if (
        policy.get("pre_buy_rearm_requires_fresh_reset", True) is True
        and fresh_reset_after_prebuy
    ):
        pre_buy_armed = True
    pre_buy = bool(
        policy.get("telegram_pre_buy_enabled") is True
        and required_streak > 1
        and qualified
        and not final_buy
        and streak == required_streak - 1
    )
    # Delivery state is monotonic within an exact-identity episode.
    # Once FINAL BUY was successfully delivered, later scan noise must never
    # downgrade the same chain+CA+pair back to PRE-BUY. A future episode may
    # re-arm FINAL BUY after observable misses, but PRE-BUY remains suppressed
    # until an explicit episode reset contract is introduced.
    final_buy_already_delivered = bool(prior.get("last_alert_at"))
    pre_buy_alert = bool(
        pre_buy
        and pre_buy_armed
        and not final_buy_already_delivered
    )
    if pre_buy_alert:
        pre_buy_armed = False

    if quarter_wave_lane:
        if quarter_wave_gain is None and quarter_wave_anchor > 0 and price > 0:
            quarter_wave_gain = ((price / quarter_wave_anchor) - 1.0) * 100.0
        proof.append(
            "QUARTER_WAVE_REVALIDATION_ARMED"
            + (f"_{quarter_wave_gain:.2f}PCT" if quarter_wave_gain is not None else "")
        )
    if late_entry_reset_reclaim:
        proof.append(
            f"ENTRY_RESET_RECLAIM_DEPTH_{reset_depth:.2f}PCT"
            f"_SCAN_{scan_gain:.2f}PCT"
        )
    elif late_entry_exceptional_continuation:
        proof.append("ENTRY_EXTREME_CEX_CONTINUATION_EXCEPTION")
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

    execution_path = (
        "HYBRID_CEX_DEX_BREAKOUT" if hybrid_breakout_continuation else
        "CEX_BREAKOUT_CONTINUATION" if cex_breakout_continuation else
        "CEX_QUARTER_WAVE_FAST_PATH" if cex_quarter_wave_fast_path else
        "EXACT_CEX_MARKET_FAST_PATH" if cex_market_only_fast_path else
        "FUSION_STRONG" if strong else
        "FUSION_RELAXED" if relaxed else
        "STANDARD"
    )
    fusion_bypassed = bool(
        execution_path in {
            "HYBRID_CEX_DEX_BREAKOUT",
            "CEX_BREAKOUT_CONTINUATION",
            "CEX_QUARTER_WAVE_FAST_PATH",
            "EXACT_CEX_MARKET_FAST_PATH",
        }
        and not (strong or relaxed)
    )

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
        "confirmation_spacing": {
            "min_seconds": min_scan_spacing,
            "elapsed_since_last_qualified_seconds": (
                round(qualified_spacing_seconds, 3)
                if qualified_spacing_seconds is not None
                else None
            ),
            "satisfied": spacing_satisfied,
            "counted_this_scan": counted_qualified_scan,
        },
        "blockers": unique_blockers,
        "proof": list(dict.fromkeys(proof)),
        "entry_timing": {
            "late_entry_guard_enabled": bool(policy.get("late_entry_guard_enabled")),
            "extended_move": late_entry_extended,
            "max_rebound_without_reset_pct": float(policy["late_entry_max_rebound_without_reset_pct"]),
            "pullback_from_watch_high_pct": (
                round(pullback_from_watch_high, 4)
                if pullback_from_watch_high is not None
                else None
            ),
            "reset_pullback_required_pct": float(policy["late_entry_reset_pullback_pct"]),
            "reset_seen": reset_seen,
            "reset_seen_at": reset_seen_at.isoformat() if reset_seen_at is not None else None,
            "reset_valid_seconds": reset_valid_seconds,
            "reset_reclaim_confirmed": late_entry_reset_reclaim,
            "exceptional_cex_continuation": late_entry_exceptional_continuation,
            "chase_risk_blocked": late_entry_chase_risk,
        },
        "pre_buy_episode": {
            "last_alert_at": prior.get("last_pre_buy_alert_at"),
            "last_alert_price": last_pre_buy_price if last_pre_buy_price > 0 else None,
            "age_seconds": (
                round(pre_buy_episode_age_seconds, 3)
                if pre_buy_episode_age_seconds is not None
                else None
            ),
            "price_drift_pct": (
                round(pre_buy_price_drift_pct, 4)
                if pre_buy_price_drift_pct is not None
                else None
            ),
            "max_price_drift_pct": pre_buy_max_price_drift,
            "ttl_seconds": pre_buy_episode_ttl,
            "fresh_reset_reclaim": fresh_reset_after_prebuy,
            "episode_count": int(prior.get("pre_buy_episode_count") or 0),
        },
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
            "execution_path": execution_path,
            "fusion_gate_bypassed": fusion_bypassed,
        },
        "truth_contract": {
            "exact_chain_contract_pair_required": not cex_market_only,
            "exact_cex_market_identity_required": cex_market_only,
            "two_scan_confirmation_required": required_streak >= 2,
            "minimum_confirmation_spacing_seconds": min_scan_spacing,
            "fast_recheck_never_bypasses_confirmation_spacing": True,
            "telegram_final_buy_only": False,
            "telegram_pre_buy_enabled": bool(policy.get("telegram_pre_buy_enabled")),
            "pre_buy_requires_all_current_gates_passed": True,
            "pre_buy_is_one_confirmation_scan_before_final_buy": True,
            "pre_buy_fast_recheck_requires_real_time_spacing": True,
            "pre_buy_never_after_delivered_final_buy_same_episode": True,
            "pre_buy_rearm_requires_fresh_reset_reclaim": True,
            "pre_buy_price_chase_guard_enabled": True,
            "pre_buy_episode_ttl_enabled": True,
            "late_entry_reset_credential_expires": True,
            "manual_decision_only": True,
            "automatic_trade": False,
            "quarter_wave_revalidation_lane": quarter_wave_lane,
            "quarter_wave_trigger_is_not_buy": True,
            "all_hard_safety_gates_still_required": True,
            "contextual_execution_gates_may_be_satisfied_by_verified_alternate_path": True,
            "cex_fast_path_bypasses_only_replaceable_dex_and_fusion_gates": True,
            "cex_fast_path_still_requires_current_intelligence_no_hard_risk_microstructure_and_two_scans": True,
            "late_entry_chase_guard_blocks_extended_rebounds_without_reset_reclaim": True,
            "late_entry_extreme_cex_exception_requires_existing_strict_extreme_breakout_gate": True,
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
        "last_market_observed_at": (market or {}).get("observed_at") or prior.get("last_market_observed_at"),
        "last_price": price if price > 0 else prior.get("last_price"),
        "last_liquidity": liquidity,
        "last_volume_h1": volume_h1,
        "last_buy_sell_ratio": round(ratio, 6),
        "last_buys_h1": buys,
        "last_sells_h1": sells,
        "last_activity_h1": activity,
        "watch_low_price": low if low is not None else prior.get("watch_low_price"),
        "watch_high_price": max(num(prior.get("watch_high_price"), 0.0) or 0.0, price),
        "late_entry_extension_seen": False if alert else extension_seen,
        "late_entry_reset_seen": False if alert else reset_seen,
        "late_entry_reset_seen_at": (
            None
            if alert
            else (reset_seen_at.isoformat() if reset_seen_at is not None else None)
        ),
        "late_entry_reset_max_pullback_pct": 0.0 if alert else reset_depth,
        "qualified_streak": streak,
        "last_qualified_scan_at": (
            now.isoformat()
            if counted_qualified_scan
            else prior.get("last_qualified_scan_at")
        ),
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



def targeted_risk_event(
    target: dict,
    decision: dict,
    prior: dict | None,
    policy: dict,
    now: datetime,
) -> dict | None:
    """Return a user-requested position-protection event for an exact target."""
    if target.get("targeted_telegram_watch") is not True:
        return None

    allowed = {
        str(x or "").strip().upper()
        for x in (target.get("targeted_telegram_events") or [])
        if str(x or "").strip()
    }
    if not ({"RISK_WARNING", "BREAKDOWN", "SELL_RISK"} & allowed):
        return None

    blockers = {str(x) for x in (decision.get("blockers") or [])}
    integrity_blockers = {
        "EXACT_PAIR_NOT_VERIFIED_THIS_SCAN",
        "MARKET_SNAPSHOT_STALE_OR_UNTIMED",
        "MARKET_IDENTITY_MISMATCH",
        "PRICE_MISSING",
    }
    if blockers & integrity_blockers:
        return None

    market = decision.get("market") if isinstance(decision.get("market"), dict) else {}
    intel = decision.get("intelligence") if isinstance(decision.get("intelligence"), dict) else {}
    prior = dict(prior or {})

    price = num(market.get("price_usd"), 0.0) or 0.0
    liquidity = num(market.get("liquidity_usd"), 0.0) or 0.0
    volume_h1 = num(market.get("volume_h1_usd"), 0.0) or 0.0
    ratio = num(market.get("buy_sell_ratio"), 0.0) or 0.0
    buys = int(num(market.get("buys_h1"), 0.0) or 0)
    sells = int(num(market.get("sells_h1"), 0.0) or 0)
    prev_price = num(prior.get("last_price"), 0.0) or 0.0
    prev_liquidity = num(prior.get("last_liquidity"), 0.0) or 0.0
    prev_volume_h1 = num(prior.get("last_volume_h1"), 0.0) or 0.0
    prev_ratio = num(prior.get("last_buy_sell_ratio"))
    prev_buys = int(num(prior.get("last_buys_h1"), 0.0) or 0)
    prev_sells = int(num(prior.get("last_sells_h1"), 0.0) or 0)
    scan_change = num(market.get("scan_price_gain_pct"))

    if price <= 0 or prev_price <= 0:
        return None
    if scan_change is None:
        scan_change = (price / prev_price - 1.0) * 100.0

    rp = target.get("targeted_risk_policy")
    rp = rp if isinstance(rp, dict) else {}
    warning_drop = max(0.5, float(rp.get("price_drop_warning_pct", 3.0)))
    breakdown_drop = max(warning_drop, float(rp.get("price_drop_breakdown_pct", 8.0)))
    flow_warning_ratio = max(
        0.1,
        float(rp.get("flow_warning_ratio", policy.get("min_buy_sell_ratio", 1.2))),
    )
    flow_deterioration_pct = max(5.0, float(rp.get("flow_deterioration_pct", 15.0)))
    volume_acceleration_multiple = max(
        1.05,
        float(rp.get("volume_acceleration_multiple", target.get("volume_acceleration_multiple", 1.5))),
    )
    sell_count_acceleration_multiple = max(
        1.05, float(rp.get("sell_count_acceleration_multiple", 1.35))
    )
    buy_count_deceleration_pct = min(
        90.0, max(5.0, float(rp.get("buy_count_deceleration_pct", 25.0)))
    )
    near_floor_headroom_pct = min(
        25.0, max(0.5, float(rp.get("liquidity_near_floor_headroom_pct", 5.0)))
    )
    min_warning_groups = max(2, int(rp.get("min_warning_evidence_groups", 2)))
    liquidity_drop_threshold = max(
        1.0,
        float(rp.get("liquidity_drop_breakdown_pct", target.get("liquidity_drop_pct", 20.0))),
    )
    cooldown_seconds = max(300.0, float(rp.get("cooldown_seconds", 1800.0)))
    re_alert_drop = max(
        1.0,
        float(
            rp.get(
                "realert_additional_price_drop_pct",
                rp.get("relert_additional_price_drop_pct", 8.0),
            )
        ),
    )

    reasons: list[str] = []
    evidence_groups: set[str] = set()
    severe = False
    risk_score = 0.0

    hard_risks = [str(x) for x in (intel.get("hard_risks") or []) if str(x).strip()]
    if hard_risks:
        severe = True
        risk_score += 5.0
        evidence_groups.add("HARD_RISK")
        reasons.append("HARD_RISK:" + ",".join(sorted(set(hard_risks))))

    crossed_levels: list[float] = []
    for raw in target.get("down_levels") or []:
        level = num(raw)
        if level is None or level <= 0:
            continue
        if prev_price > level >= price:
            crossed_levels.append(level)
    if crossed_levels:
        severe = True
        risk_score += 4.0
        evidence_groups.add("PRICE")
        for level in sorted(set(crossed_levels), reverse=True):
            reasons.append(f"DOWN_LEVEL_BREACH_{level:.10f}")

    if scan_change <= -breakdown_drop:
        severe = True
        risk_score += 4.0
        evidence_groups.add("PRICE")
        reasons.append(f"SCAN_PRICE_DROP_{abs(scan_change):.2f}PCT")
    elif scan_change <= -warning_drop and ratio < flow_warning_ratio:
        risk_score += 2.0
        evidence_groups.update({"PRICE", "FLOW"})
        reasons.append(
            f"PRICE_WEAKNESS_WITH_FLOW_FAILURE_{abs(scan_change):.2f}PCT_RATIO_{ratio:.2f}"
        )

    if (
        prev_ratio is not None
        and prev_ratio >= flow_warning_ratio
        and ratio < flow_warning_ratio
        and scan_change < 0
    ):
        risk_score += 1.5
        evidence_groups.add("FLOW")
        reasons.append(f"BUY_FLOW_REVERSAL_{prev_ratio:.2f}_TO_{ratio:.2f}")

    flow_deterioration = None
    if prev_ratio is not None and prev_ratio > 0:
        flow_deterioration = max(0.0, (1.0 - ratio / prev_ratio) * 100.0)
        if (
            flow_deterioration >= flow_deterioration_pct
            and ratio < 1.0
            and scan_change < 0
        ):
            risk_score += 1.25
            evidence_groups.add("FLOW")
            reasons.append(
                f"FLOW_DETERIORATION_{flow_deterioration:.1f}PCT_{prev_ratio:.2f}_TO_{ratio:.2f}"
            )

    total_volume_multiple = volume_h1 / prev_volume_h1 if prev_volume_h1 > 0 else None
    if (
        total_volume_multiple is not None
        and total_volume_multiple >= volume_acceleration_multiple
        and ratio < 1.0
        and scan_change < 0
    ):
        # Exact-pair feed exposes total volume, not side-specific sell notional.
        risk_score += 1.0
        evidence_groups.add("VOLUME")
        reasons.append(f"BEARISH_TOTAL_VOLUME_EXPANSION_{total_volume_multiple:.2f}X")

    sell_count_multiple = sells / prev_sells if prev_sells > 0 else None
    if (
        sell_count_multiple is not None
        and prev_sells >= 5
        and sell_count_multiple >= sell_count_acceleration_multiple
        and ratio < 1.0
        and scan_change < 0
    ):
        risk_score += 1.5
        evidence_groups.update({"FLOW", "SELL_COUNT"})
        reasons.append(f"SELL_COUNT_ACCELERATION_{sell_count_multiple:.2f}X")

    buy_count_change_pct = None
    if prev_buys > 0:
        buy_count_change_pct = (buys / prev_buys - 1.0) * 100.0
        if (
            prev_buys >= 5
            and buy_count_change_pct <= -buy_count_deceleration_pct
            and ratio < 1.0
            and scan_change < 0
        ):
            risk_score += 0.75
            evidence_groups.add("FLOW")
            reasons.append(f"BUY_COUNT_DECELERATION_{abs(buy_count_change_pct):.1f}PCT")

    liquidity_drop_pct = None
    if prev_liquidity > 0 and liquidity >= 0:
        liquidity_drop_pct = (prev_liquidity - liquidity) / prev_liquidity * 100.0
        if liquidity_drop_pct >= liquidity_drop_threshold:
            severe = True
            risk_score += 4.0
            evidence_groups.add("LIQUIDITY")
            reasons.append(f"LIQUIDITY_DROP_{liquidity_drop_pct:.2f}PCT")

    final_buy_floor = float(policy.get("min_liquidity_usd", 50000.0))
    floor_headroom_pct = (
        (liquidity / final_buy_floor - 1.0) * 100.0
        if final_buy_floor > 0 and liquidity > 0
        else None
    )
    if prev_liquidity >= final_buy_floor and liquidity < final_buy_floor:
        severe = True
        risk_score += 4.0
        evidence_groups.add("LIQUIDITY")
        reasons.append(f"LIQUIDITY_FLOOR_BREACH_{final_buy_floor:.0f}")
    elif (
        floor_headroom_pct is not None
        and 0 <= floor_headroom_pct <= near_floor_headroom_pct
        and ratio < 1.0
        and scan_change < 0
    ):
        risk_score += 1.0
        evidence_groups.add("LIQUIDITY")
        reasons.append(f"LIQUIDITY_NEAR_FLOOR_{floor_headroom_pct:.2f}PCT_HEADROOM")

    if not reasons:
        return None

    # Precision guard: one inferred volume expansion by itself is not enough.
    if not severe and len(evidence_groups) < min_warning_groups:
        return None

    severity = "BREAKDOWN" if severe else "RISK_WARNING"
    event_name = (
        severity
        if severity in allowed
        else ("RISK_WARNING" if "RISK_WARNING" in allowed else "SELL_RISK")
    )
    if event_name not in allowed:
        return None

    signature = "|".join(sorted(set(reasons)))
    last_alert_at = prior.get("last_targeted_risk_alert_at")
    alert_age = age_seconds(last_alert_at, now) if last_alert_at else None
    last_alert_price = num(prior.get("last_targeted_risk_alert_price"), 0.0) or 0.0
    last_signature = str(prior.get("last_targeted_risk_signature") or "")
    last_severity = str(prior.get("last_targeted_risk_severity") or "").upper()
    prior_active = bool(prior.get("targeted_risk_active"))

    severity_rank = {"RISK_WARNING": 1, "BREAKDOWN": 2}
    escalated = severity_rank.get(severity, 1) > severity_rank.get(last_severity, 0)
    additional_drop = bool(
        last_alert_price > 0
        and price <= last_alert_price * (1.0 - re_alert_drop / 100.0)
    )
    new_break_level = bool(crossed_levels and signature != last_signature)
    cooled_new_signature = bool(
        alert_age is not None
        and alert_age >= cooldown_seconds
        and signature != last_signature
    )
    should_alert = bool(
        not prior_active
        or not last_alert_at
        or escalated
        or additional_drop
        or new_break_level
        or cooled_new_signature
    )

    return {
        "active": True,
        "event": event_name,
        "severity": severity,
        "alert": should_alert,
        "signature": signature,
        "reasons": list(dict.fromkeys(reasons)),
        "price_usd": price,
        "scan_price_change_pct": round(scan_change, 4),
        "liquidity_usd": liquidity,
        "liquidity_drop_pct": (
            round(liquidity_drop_pct, 4)
            if liquidity_drop_pct is not None
            else None
        ),
        "volume_h1_usd": volume_h1,
        "buy_sell_ratio": round(ratio, 4),
        "previous_buy_sell_ratio": (
            round(prev_ratio, 4) if prev_ratio is not None else None
        ),
        "crossed_down_levels": sorted(set(crossed_levels), reverse=True),
        "cooldown_seconds": cooldown_seconds,
        "manual_decision_only": True,
    }


def targeted_risk_message(target: dict, decision: dict, event: dict) -> str:
    market = decision.get("market") if isinstance(decision.get("market"), dict) else {}
    severe = str(event.get("severity") or "").upper() == "BREAKDOWN"
    title = (
        f"🔴⚠️ BREAKDOWN / SELL-RISK — {decision['symbol']} — WALLET500"
        if severe
        else f"🟠⚠️ אזהרת סיכון / SELL-RISK — {decision['symbol']} — WALLET500"
    )
    action = (
        "הידרדרות מהותית זוהתה. יש לבחון הגנת פוזיציה / צמצום או יציאה מיידית לפי מצבך."
        if severe
        else "המומנטום נחלש. יש לבחון צמצום סיכון לפני שהמהלך מחמיר."
    )
    lines = [
        title,
        action,
        f"Price: ${float(event.get('price_usd') or 0):.10f}",
        f"Scan move: {float(event.get('scan_price_change_pct') or 0):+.2f}%",
        (
            f"Liquidity: ${float(event.get('liquidity_usd') or 0):,.0f}"
            + (
                f" ({-float(event['liquidity_drop_pct']):+.1f}% vs previous scan)"
                if event.get("liquidity_drop_pct") is not None
                else ""
            )
        ),
        (
            f"Buys/Sells 1H: {int(market.get('buys_h1') or 0)}/"
            f"{int(market.get('sells_h1') or 0)} "
            f"({float(event.get('buy_sell_ratio') or 0):.2f}x)"
        ),
        "Signals: " + " | ".join(event.get("reasons") or []),
        "התראה זו ייעודית למטבע שביקשת לעקוב אחריו; אינה התראת RESEARCH כללית.",
        "Manual decision only. No automatic sell.",
        f"CA: {target.get('contract')}",
        f"Pair: {target.get('pair')}",
        str(target.get("dex_url") or ""),
    ]
    return "\n".join(lines)


def telegram_message(target: dict, decision: dict) -> str:
    m = decision["market"]
    intel = decision["intelligence"]
    timing = decision.get("entry_timing") if isinstance(decision.get("entry_timing"), dict) else {}
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
            (
                "Entry timing: reset + reclaim confirmed ✅"
                if timing.get("reset_reclaim_confirmed")
                else (
                    "Entry timing: exceptional exact-CEX continuation ✅"
                    if timing.get("exceptional_cex_continuation")
                    else "Entry timing: cumulative chase guard passed ✅"
                )
            ),
            (
                f"Intelligence: alternate verified path {intel['execution_path']} | "
                f"Fusion {intel['score']:.1f}/100 is informational, not the approving gate"
                if intel.get("fusion_gate_bypassed")
                else f"Intelligence Fusion: {intel['score']:.1f}/100 | {intel['positive_families']} positive families"
            ),
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
        (
            "Entry timing: reset + reclaim confirmed ✅"
            if timing.get("reset_reclaim_confirmed")
            else (
                "Entry timing: exceptional exact-CEX continuation ✅"
                if timing.get("exceptional_cex_continuation")
                else "Entry timing: cumulative chase guard passed ✅"
            )
        ),
        (
            f"Intelligence: alternate verified path {intel['execution_path']} | "
            f"Fusion {intel['score']:.1f}/100 is informational, not the approving gate"
            if intel.get("fusion_gate_bypassed")
            else f"Intelligence Fusion: {intel['score']:.1f}/100 | {intel['positive_families']} positive families"
        ),
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


def send_telegram(text: str) -> None:
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        raise RuntimeError("TELEGRAM_SECRETS_NOT_CONFIGURED")
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot}/sendMessage",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError("TELEGRAM_SEND_FAILED")


def checkpoint_delivery_state(target_state: dict, now: datetime) -> None:
    """Stage dedupe state immediately after a successful Telegram delivery.

    The workflow publishes this file from an always() step, so a later exception
    cannot reopen the same exact-identity episode and duplicate a user alert.
    """
    write(STATE, {
        "version": 1,
        "updated_at": now.isoformat(),
        "mode": POLICY_MODE,
        "targets": target_state,
    })


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
    close_intelligence = load(CLOSE_INTELLIGENCE, {"tokens": []})
    dynamic = load(DYNAMIC, {"candidates": []})
    persistent = load(STATE, {"version": 1, "targets": {}})

    upstream = os.environ.get("WALLET500_MARKET_WATCH_OUTCOME", "success").strip().lower()
    partial_upstream = upstream != "success"
    # A cancelled long scan must not globally erase fresh high-priority decisions.
    # On partial upstream, evaluate only targets refreshed in the last five minutes;
    # all older targets fail closed and keep their previous confirmation state.
    partial_upstream_max_age_seconds = min(
        300.0, float(policy.get("max_snapshot_age_seconds", 2100))
    )
    target_state = persistent.get("targets") if isinstance(persistent.get("targets"), dict) else {}
    target_state = dict(target_state)

    now = now_utc()
    top_report_age = age_seconds(watch_report.get("updated_at"), now)
    decisions: list[dict] = []
    delivered: list[str] = []
    pre_buy_delivered: list[str] = []
    targeted_risk_delivered: list[str] = []
    errors: list[dict] = []

    partial_upstream_skipped = 0
    partial_upstream_evaluated = 0
    fresh_state_intelligence_fallback_count = 0
    for target in eligible_targets(config, dynamic, watch_state):
        key = identity_key(target)
        m = market_row(watch_state, key)
        rr = report_row(watch_report, key)
        if rr is not None:
            rr = dict(rr)
            rr["_report_age_seconds"] = top_report_age
        rr = observed_with_fresh_intelligence_fallback(
            rr,
            m,
            close_intelligence_row(close_intelligence, key),
            key,
            now=now,
            max_age_seconds=float(policy.get("max_snapshot_age_seconds", 2100)),
        )
        if isinstance(rr, dict) and rr.get("_fresh_state_intelligence_fallback") is True:
            fresh_state_intelligence_fallback_count += 1

        if partial_upstream:
            market_age = age_seconds((m or {}).get("observed_at"), now)
            report_time = (rr or {}).get("observed_at") or (rr or {}).get("updated_at")
            report_age = age_seconds(report_time, now)
            if report_age is None:
                report_age = top_report_age
            fresh_partial = bool(
                market_age is not None
                and 0 <= market_age <= partial_upstream_max_age_seconds
                and report_age is not None
                and 0 <= report_age <= partial_upstream_max_age_seconds
                and (rr or {}).get("market_verified") is True
            )
            if not fresh_partial:
                partial_upstream_skipped += 1
                decisions.append({
                    "symbol": target.get("symbol"),
                    "identity_key": key,
                    "state": "WATCH",
                    "recommended_action": "WAIT",
                    "alert": False,
                    "pre_buy": False,
                    "qualified_this_scan": False,
                    "qualified_streak": int((target_state.get(key) or {}).get("qualified_streak") or 0),
                    "blockers": ["UPSTREAM_PARTIAL_SNAPSHOT_NOT_FRESH"],
                    "proof": [],
                    "upstream_outcome": upstream,
                })
                continue
            partial_upstream_evaluated += 1

        prior_state = target_state.get(key) if isinstance(target_state.get(key), dict) else {}
        decision, next_state = evaluate(
            target, m, rr, prior_state, policy, now=now
        )

        targeted_risk = targeted_risk_event(
            target, decision, prior_state, policy, now
        )
        decision["targeted_risk"] = targeted_risk
        next_state["targeted_risk_active"] = bool(
            targeted_risk and targeted_risk.get("active")
        )
        if targeted_risk and targeted_risk.get("alert") is True:
            try:
                send_telegram(targeted_risk_message(target, decision, targeted_risk))
                targeted_risk_delivered.append(key)
                next_state["last_targeted_risk_alert_at"] = now.isoformat()
                next_state["last_targeted_risk_alert_price"] = targeted_risk.get("price_usd")
                next_state["last_targeted_risk_signature"] = targeted_risk.get("signature")
                next_state["last_targeted_risk_severity"] = targeted_risk.get("severity")
                next_state["last_targeted_risk_delivery_status"] = "DELIVERED"
                target_state[key] = next_state
                checkpoint_delivery_state(target_state, now)
            except Exception as exc:
                next_state["last_targeted_risk_delivery_status"] = f"ERROR:{type(exc).__name__}"
                targeted_risk["alert"] = False
                targeted_risk["delivery_error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
                errors.append({
                    "identity_key": key,
                    "event": str(targeted_risk.get("event") or "RISK_WARNING"),
                    "error": targeted_risk["delivery_error"],
                })

        if decision.get("pre_buy_alert") is True:
            try:
                send_telegram(telegram_message(target, decision))
                pre_buy_delivered.append(key)
                next_state["last_pre_buy_delivery_status"] = "DELIVERED"
                target_state[key] = next_state
                checkpoint_delivery_state(target_state, now)
            except Exception as exc:
                next_state["pre_buy_armed"] = True
                next_state.pop("last_pre_buy_alert_at", None)
                next_state.pop("last_pre_buy_alert_price", None)
                next_state["pre_buy_episode_count"] = int((target_state.get(key) or {}).get("pre_buy_episode_count") or 0)
                next_state["last_pre_buy_delivery_status"] = f"ERROR:{type(exc).__name__}"
                decision["pre_buy_alert"] = False
                decision["pre_buy_delivery_error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
                errors.append({"identity_key": key, "event": "PRE_BUY", "error": decision["pre_buy_delivery_error"]})

        if decision.get("alert") is True:
            try:
                send_telegram(telegram_message(target, decision))
                delivered.append(key)
                next_state["last_delivery_status"] = "DELIVERED"
                target_state[key] = next_state
                checkpoint_delivery_state(target_state, now)
            except Exception as exc:
                next_state["armed"] = True
                next_state.pop("last_alert_at", None)
                next_state.pop("last_alert_price", None)
                next_state["buy_episode_count"] = int((target_state.get(key) or {}).get("buy_episode_count") or 0)
                next_state["last_delivery_status"] = f"ERROR:{type(exc).__name__}"
                decision["alert"] = False
                decision["delivery_error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
                errors.append({"identity_key": key, "event": "FINAL_BUY", "error": decision["delivery_error"]})

        target_state[key] = next_state
        decisions.append(decision)

    persistent = {
        "version": 1,
        "updated_at": now.isoformat(),
        "mode": POLICY_MODE,
        "targets": target_state,
    }
    write(STATE, persistent)

    configured_target_count = len(eligible_targets(config, dynamic, watch_state))
    evaluated_target_count = max(0, len(decisions) - partial_upstream_skipped)
    decision_coverage_pct = (
        round((evaluated_target_count / configured_target_count) * 100.0, 2)
        if configured_target_count
        else 100.0
    )

    report = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": POLICY_MODE,
        "policy": policy,
        "status": "PARTIAL_UPSTREAM_FRESH_TARGETS_ONLY" if partial_upstream else "OK",
        "upstream_outcome": upstream,
        "partial_upstream_evaluated": partial_upstream_evaluated,
        "partial_upstream_skipped": partial_upstream_skipped,
        "configured_targets": configured_target_count,
        "evaluated_target_count": evaluated_target_count,
        "decision_coverage_pct": decision_coverage_pct,
        "fresh_state_intelligence_fallback_count": fresh_state_intelligence_fallback_count,
        "buy_zone_count": sum(1 for x in decisions if x.get("state") == "BUY_ZONE"),
        "pre_buy_count": sum(1 for x in decisions if x.get("pre_buy") is True),
        "pre_buy_delivered_count": len(pre_buy_delivered),
        "pre_buy_delivered": pre_buy_delivered,
        "targeted_risk_delivered_count": len(targeted_risk_delivered),
        "targeted_risk_delivered": targeted_risk_delivered,
        "delivered_count": len(delivered),
        "delivered": delivered,
        "error_count": len(errors),
        "errors": errors,
        "decisions": decisions,
        "truth_contract": {
            "source": "Unified Watch exact-pair state + current intelligence report; fresh exact-state + close-watch-intelligence fallback on publication lag",
            "fresh_state_intelligence_fallback_requires_exact_identity_match": True,
            "fresh_state_intelligence_fallback_requires_both_sources_current": True,
            "fresh_state_intelligence_fallback_never_bypasses_final_buy_gates": True,
            "user_requested_targets_new_chain_and_quarter_wave_cex_only": True,
            "new_chain_bootstrap_uses_same_strict_final_buy_gate": True,
            "quarter_wave_cex_uses_same_strict_final_buy_gate": True,
            "quarter_wave_trigger_gain_pct": 25.0,
            "quarter_wave_trigger_is_not_buy": True,
            "telegram_final_buy_only": False,
            "telegram_pre_buy_enabled": bool(policy.get("telegram_pre_buy_enabled")),
            "pre_buy_definition": "ALL_CURRENT_GATES_PASSED_AND_EXACTLY_ONE_CONFIRMATION_SCAN_REMAINS",
            "minimum_confirmation_spacing_seconds": float(policy.get("min_qualified_scan_spacing_seconds", 180)),
            "hot_recheck_delay_seconds": int(policy.get("hot_recheck_delay_seconds", 180)),
            "hot_recheck_max_targets": int(policy.get("hot_recheck_max_targets", 8)),
            "hot_recheck_never_weakens_final_buy_gates": True,
            "research_watch_notifications": False,
            "near_buy_notifications": True,
            "generic_near_buy_notifications": False,
            "targeted_position_protection_notifications": True,
            "targeted_risk_requires_explicit_per_token_opt_in": True,
            "targeted_risk_never_uses_stale_or_identity_ambiguous_market_data": True,
            "fail_closed_per_target_on_partial_upstream": True,
            "partial_upstream_max_snapshot_age_seconds": partial_upstream_max_age_seconds,
            "decision_coverage_is_explicit": True,
            "zero_current_coverage_never_counts_as_healthy": True,
            "automatic_trade": False,
            "veteran_production_real_alert_policy_unchanged": True,
        },
    }
    write(REPORT, report)
    print(json.dumps({
        "status": ("DELIVERY_ERROR" if errors else ("PARTIAL_UPSTREAM_FRESH_TARGETS_ONLY" if partial_upstream else "OK")),
        "mode": POLICY_MODE,
        "configured_targets": report["configured_targets"],
        "evaluated_target_count": report["evaluated_target_count"],
        "decision_coverage_pct": report["decision_coverage_pct"],
        "fresh_state_intelligence_fallback_count": report["fresh_state_intelligence_fallback_count"],
        "buy_zone_count": report["buy_zone_count"],
        "pre_buy_count": report["pre_buy_count"],
        "pre_buy_delivered_count": report["pre_buy_delivered_count"],
        "targeted_risk_delivered_count": report["targeted_risk_delivered_count"],
        "delivered_count": report["delivered_count"],
        "error_count": report["error_count"],
    }, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
