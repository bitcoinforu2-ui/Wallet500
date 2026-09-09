from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

DATA = Path("data")
EVM_CHAINS = {
    "ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche",
    "fantom", "linea", "zksync", "mantle", "scroll", "blast",
}


def _load(path: Path, default):
    try:
        if not path.exists() or not path.stat().st_size:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _num(value, default=0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _norm_addr(chain: object, value: object) -> str:
    c = str(chain or "").strip().lower()
    raw = str(value or "").strip()
    return raw.lower() if c in EVM_CHAINS else raw


def _compact_candidate(row: dict) -> dict:
    """Compact a verified-watch row without throwing away exact-pair market data.

    Research cards need market context, but unverified concentrated-liquidity depth must
    never be silently promoted to executable liquidity. When execution depth is not
    verified we expose the provider-reported exact-pair pool value only as an
    informational display value and preserve the execution value separately.
    """
    activity = row.get("dex_activity_truth") if isinstance(row.get("dex_activity_truth"), dict) else {}

    execution_liq = _num(row.get("execution_pool_liquidity_usd"), 0.0)
    provider_pool_value = _num(
        _first_present(
            row.get("provider_reported_pool_value_usd"),
            row.get("dex_pair_liquidity_usd"),
            row.get("dex_liquidity_usd"),
            row.get("current_liquidity_usd"),
        ),
        0.0,
    )
    if execution_liq > 0:
        display_liq = execution_liq
        liquidity_semantics = "VERIFIED_EXECUTION_LIQUIDITY"
    elif provider_pool_value > 0:
        display_liq = provider_pool_value
        liquidity_semantics = "PROVIDER_REPORTED_EXACT_PAIR_POOL_VALUE_INFORMATIONAL_ONLY"
    else:
        display_liq = None
        liquidity_semantics = "UNAVAILABLE"

    volume_h1 = _first_present(row.get("dex_volume_h1"), row.get("volume_h1_usd"), activity.get("volume_h1_usd"))
    volume_h24 = _first_present(row.get("dex_volume_h24"), row.get("volume_h24_usd"), activity.get("volume_h24_usd"))
    buys_h1 = _first_present(row.get("buys_h1"), activity.get("buys_h1"))
    sells_h1 = _first_present(row.get("sells_h1"), activity.get("sells_h1"))
    buys_h24 = _first_present(row.get("buys_h24"), activity.get("buys_h24"))
    sells_h24 = _first_present(row.get("sells_h24"), activity.get("sells_h24"))

    turnover_h1 = row.get("turnover_h1")
    if turnover_h1 is None and display_liq and _num(volume_h1, -1) >= 0:
        turnover_h1 = _num(volume_h1) / display_liq

    market_activity_verified = bool(
        row.get("market_activity_verified") is True
        or row.get("dex_activity_verified") is True
        or activity.get("market_activity_verified") is True
        or activity.get("verified") is True
    )

    return {
        "symbol": row.get("symbol"),
        "chain": row.get("chain"),
        "token_address": row.get("token_address"),
        "pair_address": row.get("pair_address"),
        "dex_url": row.get("dex_url"),
        "dex": row.get("dex"),
        "radar_tier": row.get("radar_tier"),
        "status": row.get("status"),
        "readiness_passed": int(row.get("readiness_passed") or 0),
        "readiness_total": int(row.get("readiness_total") or 7),
        "readiness_pct": _num(row.get("readiness_pct")),
        "missing_gates": list(row.get("missing_gates") or []),
        "blockers": list(row.get("blockers") or []),
        "signal_score": _num(row.get("signal_score")),
        "signal_score_semantics": "MAX_AVAILABLE_SIGNAL_NOT_PROBABILITY",
        "source_lane_count": int(row.get("source_lane_count") or 0),
        "evidence_ready": row.get("evidence_ready") is True,
        "evidence_positive_count": int(row.get("evidence_positive_count") or 0),
        "evidence_positive_lanes": list(row.get("evidence_positive_lanes") or []),
        "watch_is_new_24h": row.get("watch_is_new_24h") is True,
        "watch_added_at": row.get("watch_added_at"),
        "watch_entered_label": row.get("watch_entered_label"),
        "execution_pool_liquidity_usd": execution_liq,
        "provider_reported_pool_value_usd": provider_pool_value or None,
        "liquidity_usd": display_liq,
        "liquidity_display_semantics": liquidity_semantics,
        "dex_volume_h1": _num(volume_h1, 0.0) if volume_h1 is not None else None,
        "dex_volume_h24": _num(volume_h24, 0.0) if volume_h24 is not None else None,
        "turnover_h1": _num(turnover_h1, 0.0) if turnover_h1 is not None else None,
        "buys_h1": int(_num(buys_h1, 0)) if buys_h1 is not None else None,
        "sells_h1": int(_num(sells_h1, 0)) if sells_h1 is not None else None,
        "buys_h24": int(_num(buys_h24, 0)) if buys_h24 is not None else None,
        "sells_h24": int(_num(sells_h24, 0)) if sells_h24 is not None else None,
        "market_activity_verified": market_activity_verified,
        "exact_identity_verified": row.get("exact_identity_verified") is True,
        "exact_pair_verified": row.get("exact_pair_verified") is True,
        "market_age_verified": row.get("market_age_verified") is True,
        "research_only": True,
        "automatic_buy": False,
    }


def _fetch_exact_pair_market(row: dict, timeout: float = 7.0) -> dict | None:
    """Fetch one exact pair from DexScreener and reject any identity mismatch."""
    chain = str(row.get("chain") or "").strip().lower()
    token = str(row.get("token_address") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    if not chain or not token or not pair:
        return None
    if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
        return None

    url = f"https://api.dexscreener.com/latest/dex/pairs/{quote(chain)}/{quote(pair)}"
    request = Request(url, headers={"User-Agent": "Wallet500/1.0 exact-pair research refresh"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pairs = payload.get("pairs") if isinstance(payload, dict) else []
    if not isinstance(pairs, list):
        return None

    wanted_pair = _norm_addr(chain, pair)
    wanted_token = _norm_addr(chain, token)
    for item in pairs:
        if not isinstance(item, dict):
            continue
        if _norm_addr(chain, item.get("pairAddress")) != wanted_pair:
            continue
        base = item.get("baseToken") if isinstance(item.get("baseToken"), dict) else {}
        quote_token = item.get("quoteToken") if isinstance(item.get("quoteToken"), dict) else {}
        returned_tokens = {_norm_addr(chain, base.get("address")), _norm_addr(chain, quote_token.get("address"))}
        if wanted_token not in returned_tokens:
            continue
        return item
    return None


def _apply_exact_pair_market(row: dict, market: dict | None, observed_at: str | None = None) -> None:
    """Overlay only exact-pair live market facts; never promote pool TVL to execution depth."""
    if not isinstance(row, dict):
        return
    if not isinstance(market, dict):
        row["live_market_status"] = "EXACT_PAIR_LIVE_DATA_UNAVAILABLE"
        return

    liquidity = market.get("liquidity") if isinstance(market.get("liquidity"), dict) else {}
    volume = market.get("volume") if isinstance(market.get("volume"), dict) else {}
    txns = market.get("txns") if isinstance(market.get("txns"), dict) else {}
    h1_tx = txns.get("h1") if isinstance(txns.get("h1"), dict) else {}
    h24_tx = txns.get("h24") if isinstance(txns.get("h24"), dict) else {}

    provider_pool_value = _num(liquidity.get("usd"), 0.0)
    if provider_pool_value > 0:
        row["provider_reported_pool_value_usd"] = provider_pool_value
        if _num(row.get("execution_pool_liquidity_usd"), 0.0) <= 0:
            row["liquidity_usd"] = provider_pool_value
            row["liquidity_display_semantics"] = "PROVIDER_REPORTED_EXACT_PAIR_POOL_VALUE_INFORMATIONAL_ONLY"

    h1 = _first_present(volume.get("h1"), row.get("dex_volume_h1"))
    h24 = _first_present(volume.get("h24"), row.get("dex_volume_h24"))
    row["dex_volume_h1"] = _num(h1, 0.0) if h1 is not None else None
    row["dex_volume_h24"] = _num(h24, 0.0) if h24 is not None else None
    row["buys_h1"] = int(_num(h1_tx.get("buys"), 0)) if h1_tx.get("buys") is not None else None
    row["sells_h1"] = int(_num(h1_tx.get("sells"), 0)) if h1_tx.get("sells") is not None else None
    row["buys_h24"] = int(_num(h24_tx.get("buys"), 0)) if h24_tx.get("buys") is not None else None
    row["sells_h24"] = int(_num(h24_tx.get("sells"), 0)) if h24_tx.get("sells") is not None else None

    display_liq = _num(row.get("liquidity_usd"), 0.0)
    if row.get("dex_volume_h1") is not None and display_liq > 0:
        row["turnover_h1"] = _num(row.get("dex_volume_h1")) / display_liq

    row["market_activity_verified"] = True
    row["live_market_status"] = "EXACT_PAIR_VERIFIED"
    row["live_market_provider"] = "DEXSCREENER_EXACT_PAIR"
    row["live_market_observed_at"] = observed_at or datetime.now(timezone.utc).isoformat()
    if market.get("url"):
        row["dex_url"] = market.get("url")
    if market.get("dexId"):
        row["dex"] = market.get("dexId")


def _refresh_live_market(payload: dict, fetcher=_fetch_exact_pair_market) -> dict:
    """Refresh unique research candidates once per exact identity, fail-soft per pair."""
    lists = [payload.get("near_alert_leaderboard") or [], payload.get("closest_to_real_alert") or []]
    cache: dict[tuple[str, str, str], dict | None] = {}
    observed_at = datetime.now(timezone.utc).isoformat()
    for rows in lists:
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = (
                str(row.get("chain") or "").strip().lower(),
                _norm_addr(row.get("chain"), row.get("token_address")),
                _norm_addr(row.get("chain"), row.get("pair_address")),
            )
            if not all(key):
                row["live_market_status"] = "IDENTITY_INCOMPLETE"
                continue
            if key not in cache:
                try:
                    cache[key] = fetcher(row)
                except Exception as exc:
                    cache[key] = None
                    row["live_market_error"] = type(exc).__name__
            _apply_exact_pair_market(row, cache[key], observed_at=observed_at)
    payload["live_market_refresh"] = {
        "provider": "DEXSCREENER_EXACT_PAIR",
        "unique_pairs_requested": len(cache),
        "exact_pairs_verified": sum(1 for value in cache.values() if isinstance(value, dict)),
        "observed_at": observed_at,
        "fail_closed_on_identity_mismatch": True,
        "execution_gate_changed": False,
    }
    return payload


def build(data_dir: Path = DATA) -> dict:
    real = _load(data_dir / "real-alerts.json", {})
    funnel = _load(data_dir / "revival-funnel-diagnostics.json", {})
    shadow = _load(data_dir / "reawakening-shadow.json", {})
    paper = _load(data_dir / "real-alert-10usd-summary.json", {})

    counts = real.get("counts") if isinstance(real.get("counts"), dict) else {}
    watch_rows = [x for x in (real.get("verified_watch") or []) if isinstance(x, dict)]
    tier_priority = {"NEAR_ALERT": 4, "VERIFIED_WATCH": 3, "BLOCKED": 2, "IDENTITY_PENDING": 1}
    ranked = sorted(
        watch_rows,
        key=lambda row: (
            tier_priority.get(str(row.get("radar_tier") or ""), 0),
            int(row.get("readiness_passed") or 0),
            row.get("evidence_ready") is True,
            int(row.get("evidence_positive_count") or 0),
            int(row.get("source_lane_count") or 0),
            _num(row.get("signal_score")),
        ),
        reverse=True,
    )
    closest = [_compact_candidate(x) for x in ranked[:10]]
    near = [_compact_candidate(x) for x in ranked if x.get("radar_tier") == "NEAR_ALERT"][:10]

    missing_counter: Counter[str] = Counter()
    blocker_counter: Counter[str] = Counter()
    for row in watch_rows:
        missing_counter.update(str(x) for x in (row.get("missing_gates") or []) if x)
        blocker_counter.update(str(x) for x in (row.get("blockers") or []) if x)

    lanes = funnel.get("lanes") if isinstance(funnel.get("lanes"), dict) else {}
    evidence = lanes.get("evidence_promotion") if isinstance(lanes.get("evidence_promotion"), dict) else {}
    revival = lanes.get("solana_veteran_revival") if isinstance(lanes.get("solana_veteran_revival"), dict) else {}
    recovery = lanes.get("reawakening_recovery") if isinstance(lanes.get("reawakening_recovery"), dict) else {}
    shadow_counts = shadow.get("counts") if isinstance(shadow.get("counts"), dict) else {}

    hard_blockers = [
        {"code": row.get("code"), "count": int(row.get("count") or 0), "classification": row.get("classification")}
        for row in (funnel.get("blockers") or []) if isinstance(row, dict)
    ]
    pending = [
        {"code": row.get("code"), "count": int(row.get("count") or 0), "classification": row.get("classification")}
        for row in (funnel.get("pending_confirmations") or []) if isinstance(row, dict)
    ]

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "RESEARCH_ONLY_NEAR_ALERT_FALSE_NEGATIVE_OBSERVATORY_V1",
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "minimum_market_age_days": 90,
            "real_alert_gate_changed": False,
            "real_alert_thresholds_weakened": False,
            "readiness_is_gate_completion_not_profit_probability": True,
            "signal_score_is_probability": False,
            "missing_evidence_is_not_failure": True,
            "near_alert_is_not_real_alert": True,
            "false_negative_recovery_is_forward_only": True,
            "exact_token_and_pair_identity_required_for_learning": True,
            "paper_tracking_only_after_delivered_real_alert": True,
        },
        "summary": {
            "real_alerts": int(counts.get("real_alerts") or 0),
            "near_alert_not_real": int(counts.get("near_alert_not_real") or 0),
            "verified_watch_not_real": int(counts.get("verified_watch_not_real") or len(watch_rows)),
            "new_watch_24h": int(counts.get("new_watch_24h") or 0),
            "evidence_ready_research": int(counts.get("evidence_ready_research") or evidence.get("evidence_ready") or 0),
            "veteran_universe": int(revival.get("universe") or 0),
            "exact_pair_universe": int(evidence.get("universe_with_exact_pair") or 0),
            "hard_blocked_truth": int(evidence.get("blocked_truth") or 0),
            "liquidity_only_false_negative_population": int(recovery.get("eligible_liquidity_only_rejects") or shadow_counts.get("eligible_liquidity_only_rejects") or 0),
            "false_negative_forward_matches": int(recovery.get("outcome_tracker_matches") or shadow_counts.get("outcome_tracker_matches") or 0),
            "false_negative_v2_triggers": int(recovery.get("shadow_triggers_v2") or shadow_counts.get("shadow_triggers_v2") or 0),
            "paper_positions": int(paper.get("positions_total") or 0),
            "paper_roi_pct": _num(paper.get("roi_pct")),
        },
        "gate_bottlenecks": [{"gate": gate, "count": count} for gate, count in missing_counter.most_common()],
        "blocker_bottlenecks": [{"blocker": blocker, "count": count} for blocker, count in blocker_counter.most_common()],
        "canonical_hard_blockers": hard_blockers,
        "pending_confirmations": pending,
        "near_alert_leaderboard": near,
        "closest_to_real_alert": closest,
        "false_negative_recovery": {
            "mode": shadow.get("mode"),
            "contract": shadow.get("contract"),
            "research_only": True,
            "automatic_buy": False,
            "v2_started_at": shadow.get("v2_started_at"),
            "eligible_liquidity_only_rejects": int(shadow_counts.get("eligible_liquidity_only_rejects") or 0),
            "dedicated_forward_state_candidates": int(shadow_counts.get("dedicated_forward_state_candidates") or 0),
            "dedicated_forward_exact_pair_successes_this_run": int(shadow_counts.get("dedicated_forward_exact_pair_successes_this_run") or 0),
            "dedicated_forward_exact_pair_misses_this_run": int(shadow_counts.get("dedicated_forward_exact_pair_misses_this_run") or 0),
            "shadow_triggers_v2": int(shadow_counts.get("shadow_triggers_v2") or 0),
        },
        "paper_experiment": {
            "mode": paper.get("mode"),
            "position_size_usd": _num(paper.get("position_size_usd")),
            "positions_total": int(paper.get("positions_total") or 0),
            "roi_pct": _num(paper.get("roi_pct")),
            "new_entry_trigger": paper.get("new_entry_trigger"),
        },
    }


def run(data_dir: Path = DATA) -> dict:
    payload = _refresh_live_market(build(data_dir))
    (data_dir / "near-alert-observatory.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
