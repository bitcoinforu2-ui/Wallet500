from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .cex_identity import run as resolve_exact_identity
from .cex_identity_preflight import run as verify_age_and_coin_identity
from .cex_spot_identity_fallback import resolve as resolve_dex_fallback

DATA = Path("data")
MAX_WATCH_CANDIDATES = 60


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


def _status(row: dict) -> str:
    identity = str(row.get("identity_status") or "")
    if identity == "DEX_VERIFIED":
        return "CEX_SPOT_EXACT_IDENTITY_RESEARCH"
    if identity == "IDENTITY_RESOLVED_PAIR_PENDING":
        return "CEX_SPOT_IDENTITY_RESOLVED_PAIR_PENDING_RESEARCH"
    return "CEX_SPOT_IDENTITY_PENDING_RESEARCH"


def _identity_priority(row: dict) -> tuple:
    """Order identity work using evidence already observed before this attempt only.

    Persistent early-revival evidence is allowed to move a candidate earlier in the
    resolver queue, but can never resolve identity or satisfy any production gate.
    """
    persistent = bool(row.get("persistent_until_exact_identity_resolution"))
    early = str(row.get("timing_quality") or "") == "EARLY_BREAKOUT_EVIDENCE"
    alert_score = _num(row.get("first_alert_score") or row.get("spot_revival_score"))
    watch_score = _num(row.get("first_watch_score"))
    coherent = _num(
        row.get("first_alert_coherent_confirmations")
        or row.get("first_watch_coherent_confirmations")
        or row.get("coherent_confirmations")
    )
    accel = max(
        _num(row.get("first_watch_price_acceleration_max_pct")),
        _num(row.get("first_watch_volume_acceleration_max_pct")),
    )
    return (persistent, early, coherent, alert_score, watch_score, accel)


def _build_identity_queue(spot: dict, pending: dict) -> tuple[list[dict], dict]:
    """Merge current watches with unresolved persistent candidates, then prioritize.

    This fixes the historical failure mode where a strong unresolved candidate could
    disappear from the current top-N watchlist before exact identity was obtained.
    Only already-recorded evidence is used; later price/outcome data is not consulted.
    """
    current_rows = [x for x in (spot.get("watchlist") or []) if isinstance(x, dict)]
    pending_rows = [x for x in (pending.get("candidates") or []) if isinstance(x, dict)]

    merged: dict[str, dict] = {}
    for row in current_rows:
        symbol = _base_symbol(row.get("symbol"))
        if symbol:
            merged[symbol] = dict(row)

    carried = 0
    for row in pending_rows:
        symbol = _base_symbol(row.get("symbol"))
        if not symbol:
            continue
        if symbol in merged:
            # Preserve current market fields while adding immutable first-watch/alert evidence.
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
    selected = ordered[:MAX_WATCH_CANDIDATES]
    selected_symbols = {_base_symbol(x.get("symbol")) for x in selected}
    pending_symbols = {_base_symbol(x.get("symbol")) for x in pending_rows}
    report = {
        "current_watch_count": len(current_rows),
        "persistent_pending_count": len(pending_rows),
        "persistent_carried_when_absent_from_current_watch": carried,
        "merged_unique_count": len(ordered),
        "selected_count": len(selected),
        "selected_persistent_count": len(selected_symbols & pending_symbols),
        "limit": MAX_WATCH_CANDIDATES,
        "ordering_only": True,
        "production_effect": False,
        "no_hindsight": True,
    }
    return selected, report


def _persist_verified_registry(data_dir: Path, rows: list[dict], now: str) -> dict:
    """Self-expand the veteran identity registry only from fully exact, conflict-free CoinGecko-backed evidence."""
    path = data_dir / "cex-identity-registry.json"
    registry = _load(path, {})
    if not isinstance(registry, dict):
        registry = {}
    symbols = registry.get("symbols") if isinstance(registry.get("symbols"), dict) else {}
    added, confirmed, conflicts = [], [], []

    for row in rows:
        if row.get("identity_status") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
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

        symbols[symbol] = {
            "coingecko_id": coin_id,
            "chain": chain,
            "token_address": token,
            "market_age_evidence_at": age_at,
            "evidence_source": "AUTO_STRICT_CEX_SPOT_CGID_AGE_PLUS_EXACT_DEX_PAIR",
            "evidence_note": (
                "Automatically learned only after strict CEX symbol identity, >=90d age evidence, "
                "exact on-chain chain+contract resolution and an exact-address DEX pair. This is an "
                "identity seed only; all liquidity, holder, survival and REAL ALERT gates still apply."
            ),
            "auto_verified_pair_address": pair,
            "auto_verified_at": now,
        }
        added.append(symbol)

    if added:
        registry["version"] = max(int(registry.get("version") or 0), 3)
        registry["updated_at"] = now
        registry["policy"] = "EXACT_IDENTITY_SEEDS_ONLY_NO_SYMBOL_ONLY_ACTIONABILITY"
        registry["symbols"] = symbols
        _write(path, registry)

    return {
        "added": added,
        "confirmed_existing": confirmed,
        "conflicts": conflicts,
        "added_count": len(added),
        "conflict_count": len(conflicts),
        "rule": "ONLY_CGID_BACKED_DEX_VERIFIED_EXACT_IDENTITY_SELF_REGISTERS; STRICT_DEX_FALLBACK_STAYS_RUN_SCOPED",
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
    """Resolve CEX Spot watches to exact on-chain identity without relaxing production gates.

    Primary path uses CoinGecko identity + age evidence then exact chain/contract/pair.
    Persistent unresolved early-revival candidates are prioritized for future resolver
    attempts even if they fall out of the current watchlist. This is ordering only.
    If CoinGecko has no symbol entry, a strict DexScreener fallback may resolve identity only
    when exact base symbol, CEX-price coherence, exact token+pair, and >=90d pair age all agree.
    Ambiguous matches fail closed. Symbol-only evidence never becomes actionable.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    spot_path = data_dir / "cex-spot-revival-radar.json"
    pending_path = data_dir / "cex-early-revival-pending.json"
    out_path = data_dir / "cex-spot-identity-radar.json"
    spot = _load(spot_path, {})
    pending = _load(pending_path, {})
    watch, queue_report = _build_identity_queue(spot, pending)

    base = {
        "version": 3,
        "generated_at": now,
        "source_generated_at": spot.get("generated_at"),
        "mode": "RESEARCH_ONLY_DYNAMIC_CEX_SPOT_EXACT_IDENTITY_V3_PRIORITY_QUEUE",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "symbol_only_actionable": False,
        "minimum_market_age_days": 90,
        "identity_queue": queue_report,
        "truth_contract": {
            "symbol_only_never_actionable": True,
            "unique_or_strictly_coherent_coin_identity_required": True,
            "exact_onchain_contract_required": True,
            "exact_dex_pair_required_before_registry_learning": True,
            "cex_only_never_real_alert": True,
            "hard_liquidity_and_survival_gates_unchanged": True,
            "existing_registry_conflict_never_overwritten": True,
            "dex_fallback_only_for_coingecko_not_found": True,
            "dex_fallback_requires_price_pair_age_coherence": True,
            "persistent_pending_priority_is_ordering_only": True,
            "persistent_pending_never_satisfies_identity": True,
            "priority_uses_only_preexisting_evidence": True,
            "no_hindsight": True,
        },
        "source_watch_count": len(watch),
    }
    if not watch:
        payload = {
            **base,
            "status": "HEALTHY_EMPTY",
            "counts": {"age_identity_verified": 0, "dex_verified": 0, "pair_pending": 0, "identity_pending": 0, "dex_fallback_verified": 0},
            "auto_registry": {"added": [], "confirmed_existing": [], "conflicts": [], "added_count": 0, "conflict_count": 0},
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
        rows = [_research_wrap(row, "CEX_SPOT_DYNAMIC_EXACT_IDENTITY", now) for row in (resolved.get("alerts") or []) if isinstance(row, dict)]

        rejected = list((age_report or {}).get("rejections") or [])
        not_found = {_base_symbol(x.get("symbol")) for x in rejected if isinstance(x, dict) and x.get("reason") == "AGE_IDENTITY_NOT_FOUND"}
        fallback_rows = []
        for original in watch:
            if _base_symbol(original.get("symbol")) not in not_found:
                continue
            fallback = resolve_dex_fallback(original)
            if fallback:
                fallback_rows.append(_research_wrap(fallback, "CEX_SPOT_STRICT_DEX_IDENTITY_FALLBACK", now))
        rows.extend(fallback_rows)

        # Prevent duplicate exact token/pair identities if both providers converge.
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

        registry_report = _persist_verified_registry(data_dir, rows, now)
        counts = {
            "age_identity_verified": len(rows),
            "dex_verified": sum(1 for x in rows if x.get("identity_status") == "DEX_VERIFIED"),
            "pair_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_RESOLVED_PAIR_PENDING"),
            "identity_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_PENDING"),
            "dex_fallback_verified": len(fallback_rows),
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
            "counts": {"age_identity_verified": 0, "dex_verified": 0, "pair_pending": 0, "identity_pending": len(watch), "dex_fallback_verified": 0},
            "auto_registry": {"added": [], "confirmed_existing": [], "conflicts": [], "added_count": 0, "conflict_count": 0},
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
