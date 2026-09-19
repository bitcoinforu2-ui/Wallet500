from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .cex_identity import run as resolve_exact_identity
from .cex_identity_preflight import run as verify_age_and_coin_identity
from .cex_spot_identity_fallback import resolve as resolve_dex_fallback

DATA = Path("data")
MAX_WATCH_CANDIDATES = 60
MAX_PERSISTENT_PRIORITY_SLOTS = 30
PERSISTENT_BACKLOG_TARGET_SLOTS = 30
PREWAVE_IDENTITY_PRIORITY_SLOTS = 12
PREWAVE_MIN_VOLUME_ACCEL_PCT = 50.0
PREWAVE_MIN_VOLUME_WINDOW_MULTIPLE = 3.0
PREWAVE_MIN_CURRENT_CHANGE_PCT = -10.0
PREWAVE_MAX_CURRENT_CHANGE_PCT = 20.0
MAX_CEX_DEX_PRICE_RATIO = 2.0
USD_LIKE_QUOTES = {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI"}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_symbol(value: object) -> str:
    s = str(value or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()
    return s[:-4] if s.endswith("USDT") else s


def _num(value: object) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _median(values: list[float]) -> float:
    values = sorted(x for x in values if x > 0)
    if not values:
        return 0.0
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def _current_cex_usd_reference_price(row: dict) -> tuple[float, list[float]]:
    """Use only contemporaneous USD-like spot markets for execution-price coherence.

    Historical first-seen/watch/alert prices are intentionally excluded here so this
    verification cannot use stale milestones or hindsight. Regional/non-USD markets are
    excluded because their raw prices are not directly USD-comparable.
    """
    prices: list[float] = []
    for market in row.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if str(market.get("market_type") or "spot").lower() != "spot":
            continue
        if market.get("regional_market") is True or market.get("volume_comparable_usd_like") is False:
            continue
        quote_symbol = str(market.get("quote_symbol") or "").upper().strip()
        market_symbol = str(market.get("symbol") or "").upper().replace("-", "").replace("_", "").replace("/", "")
        if quote_symbol:
            if quote_symbol not in USD_LIKE_QUOTES:
                continue
        elif not any(market_symbol.endswith(q) for q in USD_LIKE_QUOTES):
            continue
        price = _num(market.get("price"))
        if price > 0:
            prices.append(price)
    return _median(prices), prices


def _enforce_cex_dex_price_coherence(row: dict) -> dict:
    """Fail closed when an exact DEX pair is economically detached from current CEX spot.

    Exact chain+contract+pair identity is necessary but not sufficient for an execution
    identity. A stale or detached exact-token pool can have large nominal liquidity while
    quoting a price far away from the live CEX market. This guard never upgrades a row; it
    can only withhold DEX_VERIFIED status and registry learning.
    """
    if str(row.get("identity_status") or "") != "DEX_VERIFIED":
        return row

    out = dict(row)
    cex_reference, cex_prices = _current_cex_usd_reference_price(row)
    dex_price = _num(row.get("dex_price_usd"))
    out["cex_reference_price_usd"] = round(cex_reference, 12) if cex_reference > 0 else None
    out["cex_reference_price_sample_count"] = len(cex_prices)
    out["dex_execution_price_usd"] = dex_price if dex_price > 0 else None
    out["max_cex_dex_price_ratio"] = MAX_CEX_DEX_PRICE_RATIO

    blocker = None
    ratio = None
    if cex_reference <= 0:
        blocker = "CEX_USD_REFERENCE_MISSING_FOR_DEX_COHERENCE"
    elif dex_price <= 0:
        blocker = "DEX_EXECUTION_PRICE_MISSING_FOR_CEX_COHERENCE"
    else:
        ratio = max(cex_reference, dex_price) / min(cex_reference, dex_price)
        out["cex_dex_price_ratio"] = round(ratio, 6)
        if ratio > MAX_CEX_DEX_PRICE_RATIO:
            blocker = "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT"

    if blocker:
        out.update({
            "identity_status": "IDENTITY_RESOLVED_PAIR_PENDING",
            "identity_verified": False,
            "identity_blocker": blocker,
            "execution_pair_price_coherent": False,
            "registry_learning_eligible": False,
            "actionable": False,
            "automatic_buy": False,
        })
        return out

    out["execution_pair_price_coherent"] = True
    out["registry_learning_eligible"] = True
    return out


def _status(row: dict) -> str:
    identity = str(row.get("identity_status") or "")
    if identity == "DEX_VERIFIED":
        return "CEX_SPOT_EXACT_IDENTITY_RESEARCH"
    if identity == "IDENTITY_RESOLVED_PAIR_PENDING":
        return "CEX_SPOT_IDENTITY_RESOLVED_PAIR_PENDING_RESEARCH"
    return "CEX_SPOT_IDENTITY_PENDING_RESEARCH"


def _is_prewave_shadow_identity_candidate(row: dict) -> bool:
    """Surface strong pre-wave spot evidence for identity work without changing action score.

    This closes the W3GG-class hole: a large turnover burst or persistent cross-venue
    pressure while price is still relatively quiet should get exact-identity work before
    the token has already broken out. The signal remains research-only and never satisfies
    identity, liquidity, age, action-score or Telegram gates by itself.
    """
    if row.get("leveraged_product") is True:
        return False
    change = _num(row.get("change_24h_max_pct"))
    if change < PREWAVE_MIN_CURRENT_CHANGE_PCT or change > PREWAVE_MAX_CURRENT_CHANGE_PCT:
        return False

    shadow = set(row.get("shadow_features") or [])
    volume_accel = _num(row.get("volume_acceleration_max_pct"))
    volume_window = _num(row.get("volume_window_multiple_max"))
    absorption = (
        "VOLUME_PRICE_ABSORPTION_SHADOW" in shadow
        and (
            volume_accel >= PREWAVE_MIN_VOLUME_ACCEL_PCT
            or volume_window >= PREWAVE_MIN_VOLUME_WINDOW_MULTIPLE
        )
    )
    slow = row.get("slow_ignition") if isinstance(row.get("slow_ignition"), dict) else {}
    persistent_pressure = (
        slow.get("status") == "CROSS_VENUE_PERSISTENT"
        and _num(slow.get("confirmations")) >= 2
    )
    return bool(absorption or persistent_pressure)


def _identity_priority(row: dict) -> tuple:
    persistent = bool(row.get("persistent_until_exact_identity_resolution"))
    precursor = row.get("cross_lane_derivatives_precursor") if isinstance(row.get("cross_lane_derivatives_precursor"), dict) else {}
    cross_lane = bool(
        precursor.get("identity_priority") is True
        and precursor.get("status") == "QUALIFIED_CEX_DERIVATIVES_SPOT_PRECURSOR"
    )
    prewave = _is_prewave_shadow_identity_candidate(row) or bool(row.get("prewave_identity_priority"))
    early = str(row.get("timing_quality") or "") == "EARLY_BREAKOUT_EVIDENCE" or cross_lane
    alert_score = max(
        _num(row.get("first_alert_score") or row.get("spot_revival_score")),
        _num(precursor.get("action_signal_score")),
    )
    watch_score = _num(row.get("first_watch_score"))
    coherent = max(
        _num(
            row.get("first_alert_coherent_confirmations")
            or row.get("first_watch_coherent_confirmations")
            or row.get("coherent_confirmations")
        ),
        _num(precursor.get("derivatives_coherent_confirmations")),
    )
    accel = max(
        _num(row.get("first_watch_price_acceleration_max_pct")),
        _num(row.get("first_watch_volume_acceleration_max_pct")),
        _num(row.get("volume_acceleration_max_pct")),
    )
    prewave_strength = max(
        _num(row.get("volume_acceleration_max_pct")),
        _num(row.get("volume_window_multiple_max")) * 10.0,
    )
    return (cross_lane, prewave, early, coherent, alert_score, watch_score, prewave_strength, accel, persistent)


def _last_attempted_symbols(previous_identity: dict) -> set[str]:
    attempted: set[str] = set()
    for key in ("candidates", "rejections"):
        for row in previous_identity.get(key) or []:
            if not isinstance(row, dict):
                continue
            symbol = _base_symbol(row.get("symbol"))
            if symbol:
                attempted.add(symbol)
    return attempted


def _build_identity_queue(spot: dict, pending: dict, previous_identity: dict | None = None) -> tuple[list[dict], dict]:
    """Prioritize unresolved exact-identity work without hindsight or starvation.

    Persistent candidates may receive resolver priority after a strong early signal, but
    that priority is ordering-only. At most half the resolver is reserved for persistent
    backlog, fresh/current watches retain capacity, and candidates attempted in the prior
    run receive a one-cycle cooldown when other unresolved candidates are waiting.
    """
    previous_identity = previous_identity if isinstance(previous_identity, dict) else {}
    recent_attempts = _last_attempted_symbols(previous_identity)
    watch_rows = [x for x in (spot.get("watchlist") or []) if isinstance(x, dict)]
    shadow_rows = [x for x in (spot.get("shadow_watchlist") or []) if isinstance(x, dict)]
    cross_lane_rows = [
        x for x in shadow_rows
        if isinstance(x.get("cross_lane_derivatives_precursor"), dict)
        and x["cross_lane_derivatives_precursor"].get("identity_priority") is True
        and x["cross_lane_derivatives_precursor"].get("status") == "QUALIFIED_CEX_DERIVATIVES_SPOT_PRECURSOR"
    ]
    prewave_rows = [x for x in shadow_rows if _is_prewave_shadow_identity_candidate(x)]
    current_rows = []
    current_seen = set()
    for row in cross_lane_rows + prewave_rows + watch_rows:
        symbol = _base_symbol(row.get("symbol"))
        if not symbol or symbol in current_seen:
            continue
        current_rows.append(row)
        current_seen.add(symbol)
    pending_rows = [x for x in (pending.get("candidates") or []) if isinstance(x, dict)]
    pending_symbols_seed = {
        _base_symbol(x.get("symbol"))
        for x in pending_rows
        if _base_symbol(x.get("symbol"))
    }
    previous_persistent_rows = []
    for row in previous_identity.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        symbol = _base_symbol(row.get("symbol"))
        if not symbol or symbol in pending_symbols_seed:
            continue
        if row.get("persistent_until_exact_identity_resolution") is not True:
            continue
        if str(row.get("identity_status") or "") == "DEX_VERIFIED":
            continue
        previous_persistent_rows.append(dict(row))
        pending_symbols_seed.add(symbol)
    pending_rows.extend(previous_persistent_rows)

    merged: dict[str, dict] = {}
    current_symbols: set[str] = set()
    for row in current_rows:
        symbol = _base_symbol(row.get("symbol"))
        if symbol:
            merged[symbol] = dict(row)
            current_symbols.add(symbol)

    carried = 0
    pending_symbols: set[str] = set()
    for row in pending_rows:
        symbol = _base_symbol(row.get("symbol"))
        if not symbol:
            continue
        pending_symbols.add(symbol)
        if symbol in merged:
            combined = dict(row)
            combined.update(merged[symbol])
            for key in (
                "persistent_until_exact_identity_resolution",
                "timing_quality",
                "earliest_retained_milestone",
                "first_watch_score",
                "first_watch_coherent_confirmations",
                "first_watch_observed_at",
                "first_watch_reference_price",
                "first_watch_price_acceleration_max_pct",
                "first_watch_volume_acceleration_max_pct",
                "first_alert_score",
                "first_alert_coherent_confirmations",
                "first_alert_observed_at",
                "first_alert_reference_price",
                "first_alert_reference_exchange",
            ):
                if row.get(key) is not None:
                    combined[key] = row.get(key)
            merged[symbol] = combined
        else:
            merged[symbol] = dict(row)
            carried += 1

    ordered = sorted(merged.values(), key=_identity_priority, reverse=True)
    current_ordered = [
        row for row in ordered if _base_symbol(row.get("symbol")) in current_symbols
    ]
    prewave_symbols = {
        _base_symbol(row.get("symbol"))
        for row in prewave_rows
        if _base_symbol(row.get("symbol"))
    }
    prewave_ordered = [
        row for row in current_ordered
        if _base_symbol(row.get("symbol")) in prewave_symbols
    ]
    pending_only_symbols = pending_symbols - current_symbols
    pending_only_ordered = sorted(
        [
            row for row in ordered
            if _base_symbol(row.get("symbol")) in pending_only_symbols
        ],
        key=lambda row: (
            _base_symbol(row.get("symbol")) not in recent_attempts,
            _identity_priority(row),
        ),
        reverse=True,
    )

    selected: list[dict] = []
    selected_symbols: set[str] = set()

    def add_rows(rows: list[dict], category_cap: int | None = None) -> int:
        added = 0
        for row in rows:
            if len(selected) >= MAX_WATCH_CANDIDATES:
                break
            if category_cap is not None and added >= category_cap:
                break
            symbol = _base_symbol(row.get("symbol"))
            if not symbol or symbol in selected_symbols:
                continue
            selected.append(row)
            selected_symbols.add(symbol)
            added += 1
        return added

    prewave_selected = add_rows(prewave_ordered, PREWAVE_IDENTITY_PRIORITY_SLOTS)
    backlog_selected = add_rows(
        pending_only_ordered,
        min(MAX_PERSISTENT_PRIORITY_SLOTS, PERSISTENT_BACKLOG_TARGET_SLOTS),
    )
    add_rows(current_ordered)

    selected_recent = len(selected_symbols & recent_attempts)
    pending_not_recent = len(pending_only_symbols - recent_attempts)
    report = {
        "current_watch_count": len(current_rows),
        "regular_watch_count": len(watch_rows),
        "cross_lane_identity_priority_count": len(cross_lane_rows),
        "prewave_shadow_identity_priority_count": len(prewave_rows),
        "prewave_shadow_selected_count": prewave_selected,
        "prewave_shadow_priority_slot_cap": PREWAVE_IDENTITY_PRIORITY_SLOTS,
        "persistent_pending_count": len(pending_rows),
        "previous_unresolved_persistent_carried_count": len(previous_persistent_rows),
        "persistent_backlog_only_count": len(pending_only_symbols),
        "persistent_carried_when_absent_from_current_watch": carried,
        "merged_unique_count": len(ordered),
        "selected_count": len(selected),
        "selected_persistent_count": len(selected_symbols & pending_symbols),
        "selected_persistent_backlog_only_count": len(selected_symbols & pending_only_symbols),
        "selected_current_count": len(selected_symbols & current_symbols),
        "selected_current_nonpersistent_count": len((selected_symbols & current_symbols) - pending_symbols),
        "previous_attempted_symbol_count": len(recent_attempts),
        "pending_not_attempted_previous_run": pending_not_recent,
        "selected_attempted_previous_run": selected_recent,
        "limit": MAX_WATCH_CANDIDATES,
        "persistent_priority_slot_cap": MAX_PERSISTENT_PRIORITY_SLOTS,
        "persistent_backlog_target_slots": PERSISTENT_BACKLOG_TARGET_SLOTS,
        "persistent_backlog_selected_this_run": backlog_selected,
        "persistent_backlog_cap_enforced": backlog_selected <= MAX_PERSISTENT_PRIORITY_SLOTS,
        "fresh_watch_capacity_protected": True,
        "prewave_shadow_capacity_protected": True,
        "one_cycle_backlog_rotation": True,
        "ordering_only": True,
        "prewave_shadow_is_identity_priority_only": True,
        "prewave_shadow_never_satisfies_identity": True,
        "cross_lane_derivatives_precursor_is_identity_priority_only": True,
        "cross_lane_derivatives_precursor_never_satisfies_identity": True,
        "production_effect": False,
        "no_hindsight": True,
    }
    return selected, report


def _persist_verified_registry(data_dir: Path, rows: list[dict], now: str) -> dict:
    path = data_dir / "cex-identity-registry.json"
    registry = _load(path, {})
    if not isinstance(registry, dict):
        registry = {}
    symbols = registry.get("symbols") if isinstance(registry.get("symbols"), dict) else {}
    added, confirmed, conflicts = [], [], []

    for row in rows:
        if row.get("identity_status") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
            continue
        if row.get("execution_pair_price_coherent") is not True:
            continue
        if row.get("market_age_verified") is not True:
            continue
        symbol = _base_symbol(row.get("symbol"))
        coin_id = str(row.get("coingecko_id") or "").strip()
        chain = str(row.get("chain") or "").lower().strip()
        token = str(row.get("token_address") or "").strip()
        pair = str(row.get("pair_address") or "").strip()
        age_at = str(row.get("market_age_evidence_at") or "").strip()
        if not all((symbol, coin_id, chain, token, pair, age_at)):
            continue

        existing = symbols.get(symbol)
        if isinstance(existing, dict):
            same = (
                str(existing.get("coingecko_id") or "") == coin_id
                and str(existing.get("chain") or "").lower() == chain
                and str(existing.get("token_address") or "").lower() == token.lower()
            )
            if same:
                confirmed.append(symbol)
            else:
                conflicts.append({
                    "symbol": symbol,
                    "reason": "EXISTING_EXACT_REGISTRY_CONFLICT_PRESERVED_FAIL_CLOSED",
                    "existing_coingecko_id": existing.get("coingecko_id"),
                    "candidate_coingecko_id": coin_id,
                })
            continue

        native_proxy = row.get("native_asset_proxy") is True
        evidence_source = (
            "AUTO_STRICT_CEX_SPOT_NATIVE_WRAPPED_PROXY_PLUS_EXACT_DEX_PAIR"
            if native_proxy
            else "AUTO_STRICT_CEX_SPOT_CGID_AGE_PLUS_EXACT_DEX_PAIR"
        )
        symbols[symbol] = {
            "coingecko_id": coin_id,
            "chain": chain,
            "token_address": token,
            "market_age_evidence_at": age_at,
            "evidence_source": evidence_source,
            "evidence_note": (
                "Automatically learned only after strict CEX symbol identity, >=90d age evidence, "
                + (
                    "a curated canonical wrapped-native execution proxy, exact-address DEX pair and "
                    if native_proxy
                    else "exact on-chain chain+contract resolution, exact-address DEX pair and "
                )
                + "current CEX/DEX execution-price coherence. This is an identity seed only; all "
                "liquidity, holder, survival and REAL ALERT gates still apply."
            ),
            "native_asset_proxy": native_proxy,
            "native_asset_symbol": row.get("native_asset_symbol") if native_proxy else None,
            "native_asset_representation": row.get("native_asset_representation") if native_proxy else None,
            "native_asset_evidence_source": row.get("native_asset_evidence_source") if native_proxy else None,
            "auto_verified_pair_address": pair,
            "auto_verified_at": now,
        }
        added.append(symbol)

    if added:
        registry["version"] = max(int(registry.get("version") or 0), 4)
        registry["updated_at"] = now
        registry["policy"] = "EXACT_IDENTITY_SEEDS_ONLY_PRICE_COHERENT_NO_SYMBOL_ONLY_ACTIONABILITY"
        registry["symbols"] = symbols
        _write(path, registry)

    return {
        "added": added,
        "confirmed_existing": confirmed,
        "conflicts": conflicts,
        "added_count": len(added),
        "conflict_count": len(conflicts),
        "rule": "ONLY_CGID_BACKED_DEX_VERIFIED_EXACT_IDENTITY_WITH_CURRENT_CEX_DEX_PRICE_COHERENCE_SELF_REGISTERS; STRICT_DEX_FALLBACK_STAYS_RUN_SCOPED",
    }


def _quarantine_incoherent_auto_registry(data_dir: Path, rows: list[dict], now: str) -> dict:
    """Quarantine derived auto-registry seeds disproven by current execution-price coherence.

    The original detection milestones remain immutable in their source state. Only the
    derived identity cache is invalidated, and its previous value is retained under a
    quarantine ledger for auditability.
    """
    path = data_dir / "cex-identity-registry.json"
    registry = _load(path, {})
    if not isinstance(registry, dict):
        return {"quarantined": [], "quarantined_count": 0}
    symbols = registry.get("symbols") if isinstance(registry.get("symbols"), dict) else {}
    quarantine = registry.get("quarantined_symbols") if isinstance(registry.get("quarantined_symbols"), dict) else {}
    quarantined: list[str] = []

    for row in rows:
        if row.get("identity_blocker") != "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT":
            continue
        symbol = _base_symbol(row.get("symbol"))
        existing = symbols.get(symbol)
        if not isinstance(existing, dict):
            continue
        if str(existing.get("evidence_source") or "") not in {
            "AUTO_STRICT_CEX_SPOT_CGID_AGE_PLUS_EXACT_DEX_PAIR",
            "AUTO_STRICT_CEX_SPOT_NATIVE_WRAPPED_PROXY_PLUS_EXACT_DEX_PAIR",
        }:
            continue
        same = (
            str(existing.get("coingecko_id") or "") == str(row.get("coingecko_id") or "")
            and str(existing.get("chain") or "").lower() == str(row.get("chain") or "").lower()
            and str(existing.get("token_address") or "").lower() == str(row.get("token_address") or "").lower()
            and str(existing.get("auto_verified_pair_address") or "").lower() == str(row.get("pair_address") or "").lower()
        )
        if not same:
            continue
        quarantine[symbol] = {
            **existing,
            "quarantined_at": now,
            "quarantine_reason": "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT",
            "observed_cex_reference_price_usd": row.get("cex_reference_price_usd"),
            "observed_dex_execution_price_usd": row.get("dex_execution_price_usd"),
            "observed_cex_dex_price_ratio": row.get("cex_dex_price_ratio"),
            "immutable_detection_history_untouched": True,
        }
        del symbols[symbol]
        quarantined.append(symbol)

    if quarantined:
        registry["version"] = max(int(registry.get("version") or 0), 4)
        registry["updated_at"] = now
        registry["policy"] = "EXACT_IDENTITY_SEEDS_ONLY_PRICE_COHERENT_NO_SYMBOL_ONLY_ACTIONABILITY"
        registry["symbols"] = symbols
        registry["quarantined_symbols"] = quarantine
        _write(path, registry)

    return {
        "quarantined": quarantined,
        "quarantined_count": len(quarantined),
        "reason": "AUTO_REGISTRY_SEED_INVALIDATED_BY_CURRENT_CEX_DEX_EXECUTION_PRICE_INCOHERENCE",
        "immutable_detection_history_untouched": True,
    }


def _research_wrap(row: dict, source_lane: str, attempted_at: str) -> dict:
    return {
        **row,
        "status": _status(row),
        "research_only": True,
        "actionable": False,
        "automatic_buy": False,
        "source_lane": source_lane,
        "identity_attempted_at": attempted_at,
    }


def run(data_dir: Path = DATA) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    spot_path = data_dir / "cex-spot-revival-radar.json"
    pending_path = data_dir / "cex-early-revival-pending.json"
    out_path = data_dir / "cex-spot-identity-radar.json"
    spot = _load(spot_path, {})
    pending = _load(pending_path, {})
    previous_identity = _load(out_path, {})
    watch, queue_report = _build_identity_queue(spot, pending, previous_identity)

    base = {
        "version": 4,
        "generated_at": now,
        "source_generated_at": spot.get("generated_at"),
        "mode": "RESEARCH_ONLY_DYNAMIC_CEX_SPOT_EXACT_IDENTITY_V4_FAIR_PRIORITY_QUEUE",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "symbol_only_actionable": False,
        "minimum_market_age_days": 90,
        "identity_queue": queue_report,
        "truth_contract": {
            "symbol_only_never_actionable": True,
            "unique_or_strictly_coherent_coin_identity_required": True,
            "exact_onchain_contract_required": True,
            "native_asset_requires_curated_canonical_wrapped_contract": True,
            "native_asset_proxy_never_bypasses_price_coherence": True,
            "native_asset_proxy_never_bypasses_buy_safety_gates": True,
            "exact_dex_pair_required_before_registry_learning": True,
            "dynamic_exact_pair_requires_current_cex_dex_price_coherence": True,
            "incoherent_auto_registry_seed_quarantined_with_audit_record": True,
            "cex_only_never_real_alert": True,
            "hard_liquidity_and_survival_gates_unchanged": True,
            "existing_registry_conflict_never_overwritten": True,
            "dex_fallback_for_missing_or_inconclusive_age_evidence": True,
            "dex_fallback_never_waives_ambiguous_coin_identity": True,
            "dex_fallback_requires_price_pair_age_coherence": True,
            "persistent_pending_priority_is_ordering_only": True,
            "persistent_pending_never_satisfies_identity": True,
            "priority_uses_only_preexisting_evidence": True,
            "cross_lane_derivatives_precursor_identity_priority_only": True,
            "cross_lane_derivatives_precursor_never_satisfies_identity": True,
            "prewave_shadow_identity_priority_only": True,
            "prewave_shadow_never_satisfies_identity": True,
            "persistent_backlog_cap_enforced": True,
            "fresh_watch_capacity_protected": True,
            "prewave_shadow_capacity_protected": True,
            "previous_attempt_only_controls_future_queue_order": True,
            "previous_unresolved_persistent_identity_is_carried_forward": True,
            "previous_unresolved_persistent_identity_never_becomes_actionable_by_persistence": True,
            "no_hindsight": True,
        },
        "source_watch_count": len(watch),
    }
    if not watch:
        payload = {
            **base,
            "status": "HEALTHY_EMPTY",
            "counts": {"age_identity_verified": 0, "dex_verified": 0, "pair_pending": 0, "identity_pending": 0, "price_incoherent": 0, "dex_fallback_verified": 0},
            "auto_registry": {"added": [], "confirmed_existing": [], "conflicts": [], "added_count": 0, "conflict_count": 0, "quarantine": {"quarantined": [], "quarantined_count": 0}},
            "candidates": [],
            "rejections": [],
        }
        _write(out_path, payload)
        return payload

    temp = data_dir / ".cex-spot-identity-work.json"
    _write(temp, {"version": 1, "generated_at": spot.get("generated_at") or now, "alerts": watch, "alerts_count": len(watch)})
    try:
        age_report = verify_age_and_coin_identity(temp)
        resolve_exact_identity(temp)
        resolved = _load(temp, {})
        rows = [
            _research_wrap(_enforce_cex_dex_price_coherence(row), "CEX_SPOT_DYNAMIC_EXACT_IDENTITY", now)
            for row in (resolved.get("alerts") or [])
            if isinstance(row, dict)
        ]

        rejected = list((age_report or {}).get("rejections") or [])
        fallback_age_reasons = {
            "AGE_IDENTITY_NOT_FOUND",
            "AGE_MINIMUM_NOT_PROVEN_BY_COINGECKO_EXTREMA",
            # Backward-compatible aliases from older preflight reports. These are
            # treated as "age unproven", never as evidence that the asset is young.
            "UNDER_60_DAYS_OR_AGE_UNVERIFIED",
            "UNDER_90_DAYS_OR_AGE_UNVERIFIED",
        }
        fallback_rejections = {
            _base_symbol(x.get("symbol")): x
            for x in rejected
            if isinstance(x, dict) and x.get("reason") in fallback_age_reasons
        }
        fallback_rows = []
        for original in watch:
            base_symbol = _base_symbol(original.get("symbol"))
            rejection = fallback_rejections.get(base_symbol)
            if not rejection:
                continue
            fallback_input = dict(original)
            # Preserve the already-disambiguated CoinGecko identity when the only
            # missing proof is age. If CoinGecko had no identity, the strict DEX
            # fallback remains run-scoped and cannot auto-seed the registry.
            if rejection.get("coingecko_id"):
                fallback_input["coingecko_id"] = rejection.get("coingecko_id")
            fallback = resolve_dex_fallback(fallback_input)
            if fallback:
                fallback["age_preflight_rejection_reason"] = rejection.get("reason")
                fallback_rows.append(_research_wrap(fallback, "CEX_SPOT_STRICT_DEX_IDENTITY_FALLBACK", now))
        rows.extend(fallback_rows)

        unique = {}
        for row in rows:
            key = (
                str(row.get("chain") or "").lower(),
                str(row.get("token_address") or "").lower(),
                str(row.get("pair_address") or "").lower(),
            )
            if all(key):
                unique[key] = row
            else:
                unique[(str(row.get("symbol")), str(len(unique)), "pending")] = row
        rows = list(unique.values())

        quarantine_report = _quarantine_incoherent_auto_registry(data_dir, rows, now)
        registry_report = _persist_verified_registry(data_dir, rows, now)
        registry_report["quarantine"] = quarantine_report
        counts = {
            "age_identity_verified": len(rows),
            "dex_verified": sum(1 for x in rows if x.get("identity_status") == "DEX_VERIFIED"),
            "native_proxy_verified": sum(1 for x in rows if x.get("identity_status") == "DEX_VERIFIED" and x.get("native_asset_proxy") is True),
            "pair_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_RESOLVED_PAIR_PENDING"),
            "identity_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_PENDING"),
            "price_incoherent": sum(1 for x in rows if x.get("identity_blocker") == "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT"),
            "dex_fallback_verified": len(fallback_rows),
            "age_inconclusive_fallback_verified": sum(
                1 for x in fallback_rows
                if x.get("age_preflight_rejection_reason") == "AGE_MINIMUM_NOT_PROVEN_BY_COINGECKO_EXTREMA"
            ),
        }
        payload = {
            **base,
            "status": "OK",
            "counts": counts,
            "auto_registry": registry_report,
            "age_identity_preflight": age_report,
            "platform_catalog": resolved.get("platform_catalog"),
            "identity_contract": resolved.get("identity_contract"),
            "candidates": rows,
            "rejections": rejected,
        }
    except Exception as exc:
        payload = {
            **base,
            "status": "DEGRADED_FAIL_CLOSED",
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "counts": {"age_identity_verified": 0, "dex_verified": 0, "pair_pending": 0, "identity_pending": len(watch), "price_incoherent": 0, "dex_fallback_verified": 0},
            "auto_registry": {"added": [], "confirmed_existing": [], "conflicts": [], "added_count": 0, "conflict_count": 0, "quarantine": {"quarantined": [], "quarantined_count": 0}},
            "candidates": [],
            "rejections": [],
        }
    finally:
        try:
            temp.unlink(missing_ok=True)
        except Exception:
            pass

    _write(out_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))