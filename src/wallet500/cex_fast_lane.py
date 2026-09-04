from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .cex_identity import _verified_pairs, run as resolve_identity
from .cex_identity_preflight import run as verify_age_and_identity
from .cex_revival import run_cex_revival
from .cex_spot_revival import run_cex_spot_revival
from .real_alerts import run as build_real_alerts

DATA = Path("data")
PROJECT_SCOPE_MIN_AGE_DAYS = 180
MIN_AGE_DAYS = PROJECT_SCOPE_MIN_AGE_DAYS
APPROVED_PRODUCTION_MIN_AGE_DAYS = PROJECT_SCOPE_MIN_AGE_DAYS


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _retry(fn, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < attempts - 1:
                time.sleep(1.5 * (i + 1))
    raise last


def _base_symbol(value: object) -> str:
    s = str(value or "").upper().replace("-", "").replace("_", "").strip()
    if s.endswith("USDTM"):
        return s[:-5]
    if s.endswith("USDT"):
        return s[:-4]
    return s


def _registry_rows(raw_rows: list[dict], data_dir: Path, now: datetime) -> tuple[list[dict], list[dict]]:
    registry = _load(data_dir / "cex-identity-registry.json", {})
    symbols = registry.get("symbols") if isinstance(registry, dict) else {}
    symbols = symbols if isinstance(symbols, dict) else {}
    registered, unknown = [], []
    for row in raw_rows:
        reg = symbols.get(_base_symbol(row.get("symbol")))
        if not isinstance(reg, dict):
            unknown.append(row)
            continue
        evidence = str(reg.get("market_age_evidence_at") or "").strip()
        try:
            s = evidence[:-1] + "+00:00" if evidence.endswith("Z") else evidence
            d = datetime.fromisoformat(s)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            age_days = int((now - d.astimezone(timezone.utc)).total_seconds() // 86400)
        except Exception:
            age_days = -1
        chain = str(reg.get("chain") or "").strip().lower()
        token = str(reg.get("token_address") or "").strip()
        coin_id = str(reg.get("coingecko_id") or "").strip()
        if age_days < MIN_AGE_DAYS or not chain or not token or not coin_id:
            unknown.append(row)
            continue
        registered.append({
            **row,
            "coingecko_id": coin_id,
            "chain": chain,
            "token_address": token,
            "market_age_verified": True,
            "market_age_min_days": age_days,
            "market_age_evidence_at": evidence,
            "market_age_evidence_source": reg.get("evidence_source") or "EXACT_IDENTITY_REGISTRY",
            "cex_identity_preflight_verified": True,
            "identity_registry_verified": True,
            "cex_identity_preflight": {
                "method": "EXACT_IDENTITY_REGISTRY",
                "registry_version": registry.get("version"),
            },
        })
    return registered, unknown


def _preflight_unknown(raw_payload: dict, unknown: list[dict], data_dir: Path) -> tuple[list[dict], dict, str | None]:
    if not unknown:
        return [], {"accepted": 0, "rejected": 0, "status": "NOT_NEEDED_ALL_REGISTERED"}, None
    temp = data_dir / ".cex-preflight-unknown.json"
    _write(temp, {**raw_payload, "alerts": unknown, "alerts_count": len(unknown)})
    try:
        report = _retry(lambda: verify_age_and_identity(temp), attempts=3)
        payload = _load(temp, {})
        return list(payload.get("alerts") or []), report, None
    except Exception as e:
        return [], {
            "accepted": 0,
            "rejected": len(unknown),
            "status": "DEGRADED_FAIL_CLOSED_PROVIDER_TRANSIENT",
        }, f"{type(e).__name__}: {e}"[:500]
    finally:
        try:
            temp.unlink(missing_ok=True)
        except Exception:
            pass


def _apply_registry_dex_fallback(payload: dict) -> dict:
    rows = list(payload.get("alerts") or [])
    for i, row in enumerate(rows):
        if row.get("identity_registry_verified") is not True or row.get("identity_status") == "DEX_VERIFIED":
            continue
        candidate = {
            "chain": str(row.get("chain") or "").lower(),
            "token_address": str(row.get("token_address") or ""),
            "coingecko_platform": "identity-registry",
        }
        try:
            pairs = _verified_pairs(candidate)
        except Exception:
            pairs = []
        if not pairs:
            rows[i] = {
                **row,
                "identity_status": "IDENTITY_RESOLVED_PAIR_PENDING",
                "identity_blocker": "EXACT_DEX_PAIR_NOT_FOUND_ACROSS_PROVIDERS",
                "actionable": False,
            }
            continue
        best = max(pairs, key=lambda x: (float(x.get("liquidity_usd") or 0), float(x.get("volume_h24") or 0)))
        rows[i] = {
            **row,
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "pair_address": best.get("pair_address"),
            "dex": best.get("dex"),
            "dex_url": best.get("dex_url"),
            "dex_price_usd": best.get("price_usd"),
            "dex_liquidity_usd": best.get("liquidity_usd"),
            "dex_volume_h1": best.get("volume_h1"),
            "dex_volume_h24": best.get("volume_h24"),
            "pair_created_at": best.get("pair_created_at"),
            "pair_provider": best.get("pair_provider"),
            "exact_token_side": best.get("exact_token_side"),
            "identity_source": "EXACT_IDENTITY_REGISTRY_PLUS_EXACT_ADDRESS_DEX_POOL",
            "pair_selection_rule": "HIGHEST_CURRENT_LIQUIDITY_AMONG_EXACT_TOKEN_PAIRS_ACROSS_FALLBACK_PROVIDERS",
            "actionable": False,
        }
    payload["alerts"] = rows
    payload["identity_counts"] = {
        "dex_verified": sum(1 for x in rows if x.get("identity_status") == "DEX_VERIFIED"),
        "pair_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_RESOLVED_PAIR_PENDING"),
        "identity_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_PENDING"),
    }
    return payload


def run(data_dir: Path = DATA) -> dict:
    """Refresh raw CEX intelligence, then enforce veteran-only fail-closed truth."""
    data_dir.mkdir(parents=True, exist_ok=True)
    radar_path = data_dir / "cex-revival-radar.json"
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    raw = run_cex_revival(data_dir, now)
    raw_payload = _load(radar_path, {})
    raw_rows = list(raw_payload.get("alerts") or [])
    _write(data_dir / "cex-revival-raw.json", raw_payload)
    spot = run_cex_spot_revival(data_dir, now)

    # 180d is the explicit project universe boundary. If any code path drifts from
    # it, quarantine actionable CEX output while continuing raw collection.
    if MIN_AGE_DAYS != PROJECT_SCOPE_MIN_AGE_DAYS or MIN_AGE_DAYS != APPROVED_PRODUCTION_MIN_AGE_DAYS:
        blocked_payload = {
            **raw_payload,
            "version": max(int(raw_payload.get("version") or 0), 12),
            "alerts": [],
            "alerts_count": 0,
            "raw_alerts_before_age_gate": len(raw_rows),
            "raw_collection_generated_at": raw_payload.get("generated_at") or now,
            "collection_status": "FRESH_COLLECTION_CONTINUES",
            "spot_collection": {
                "generated_at": spot.get("generated_at"),
                "healthy_sources": spot.get("healthy_sources", 0),
                "markets_seen": spot.get("markets_seen", 0),
                "symbols_seen": spot.get("symbols_seen", 0),
                "watch_count": spot.get("watch_count", 0),
                "alerts_count": spot.get("alerts_count", 0),
                "production_portfolio_impact": "NONE",
            },
            "age_gate": {
                "status": "BLOCKED_FAIL_CLOSED_VETERAN_SCOPE_POLICY_DRIFT",
                "minimum_market_age_days": MIN_AGE_DAYS,
                "project_scope_minimum_market_age_days": PROJECT_SCOPE_MIN_AGE_DAYS,
                "approved_production_minimum_market_age_days": APPROVED_PRODUCTION_MIN_AGE_DAYS,
                "accepted": 0,
                "rejected": len(raw_rows),
                "unknown_or_unresolved_identity": "REJECT",
                "production_change_allowed": False,
                "policy": "VETERAN_ONLY_SCOPE_MUST_BE_180D_EVERYWHERE; SIGNAL_THRESHOLDS_ARE_SEPARATELY_GOVERNED",
            },
            "generated_identity_preflight_at": now,
            "fast_lane_degraded": {
                "at": now,
                "reason": "VETERAN_SCOPE_POLICY_DRIFT",
                "policy": "ACTIONABLE_CEX_OUTPUT_QUARANTINED; RAW_COLLECTION_CONTINUES",
            },
        }
        _write(radar_path, blocked_payload)
        real = build_real_alerts(data_dir)
        return {
            "status": "COLLECTED_BUT_ACTIONABLE_BLOCKED_BY_SCOPE_DRIFT",
            "generated_at": now,
            "raw_cex_alerts": len(raw_rows),
            "raw_cex_symbols_seen": raw.get("symbols_seen", 0),
            "spot_watch_count": spot.get("watch_count", 0),
            "spot_alerts_count": spot.get("alerts_count", 0),
            "spot_symbols_seen": spot.get("symbols_seen", 0),
            "registry_verified": 0,
            "external_age_identity_preflight": {"status": "NOT_RUN_POLICY_BLOCK"},
            "external_error": None,
            "dex_identity": {"dex_verified": 0, "pair_pending": 0, "identity_pending": 0},
            "real_alert_feed": real,
        }

    registered, unknown = _registry_rows(raw_rows, data_dir, now_dt)
    external_rows, ext_report, ext_error = _preflight_unknown(raw_payload, unknown, data_dir)
    merged = registered + external_rows
    merged.sort(key=lambda x: (float(x.get("cex_revival_score") or 0), int(x.get("coherent_confirmations") or 0)), reverse=True)

    preflight_payload = {
        **raw_payload,
        "version": max(int(raw_payload.get("version") or 0), 12),
        "alerts": merged,
        "alerts_count": len(merged),
        "raw_alerts_before_age_gate": len(raw_rows),
        "raw_collection_generated_at": raw_payload.get("generated_at") or now,
        "collection_status": "FRESH_COLLECTION_CONTINUES",
        "spot_collection": {
            "generated_at": spot.get("generated_at"),
            "healthy_sources": spot.get("healthy_sources", 0),
            "markets_seen": spot.get("markets_seen", 0),
            "symbols_seen": spot.get("symbols_seen", 0),
            "watch_count": spot.get("watch_count", 0),
            "alerts_count": spot.get("alerts_count", 0),
            "production_portfolio_impact": "NONE",
        },
        "age_gate": {
            "status": "ENFORCED_FAIL_CLOSED" if ext_error is None else "DEGRADED_UNKNOWN_IDENTITIES_FAIL_CLOSED",
            "minimum_market_age_days": MIN_AGE_DAYS,
            "project_scope_minimum_market_age_days": PROJECT_SCOPE_MIN_AGE_DAYS,
            "approved_production_minimum_market_age_days": APPROVED_PRODUCTION_MIN_AGE_DAYS,
            "scope_policy": "VETERAN_ONLY_PRODUCT_SCOPE_NOT_ALPHA_THRESHOLD",
            "accepted": len(merged),
            "rejected": max(0, len(raw_rows) - len(merged)),
            "registered_exact_identities": len(registered),
            "external_preflight": ext_report,
            "unknown_or_unresolved_identity": "REJECT",
        },
        "generated_identity_preflight_at": now,
    }
    if ext_error:
        preflight_payload["fast_lane_degraded"] = {
            "at": now,
            "reason": "EXTERNAL_IDENTITY_PROVIDER_TRANSIENT",
            "detail": ext_error,
            "policy": "REGISTERED_EXACT_IDENTITIES_KEPT; UNKNOWN_IDENTITIES_FAIL_CLOSED",
        }
    _write(radar_path, preflight_payload)

    identity = _retry(lambda: resolve_identity(radar_path), attempts=2)
    resolved_payload = _apply_registry_dex_fallback(_load(radar_path, {}))
    _write(radar_path, resolved_payload)
    real = build_real_alerts(data_dir)

    return {
        "status": "OK" if ext_error is None else "DEGRADED_UNKNOWN_IDENTITIES_FAIL_CLOSED",
        "generated_at": now,
        "raw_cex_alerts": raw.get("alerts_count", 0),
        "raw_cex_symbols_seen": raw.get("symbols_seen", 0),
        "spot_watch_count": spot.get("watch_count", 0),
        "spot_alerts_count": spot.get("alerts_count", 0),
        "spot_symbols_seen": spot.get("symbols_seen", 0),
        "registry_verified": len(registered),
        "external_age_identity_preflight": ext_report,
        "external_error": ext_error,
        "dex_identity": resolved_payload.get("identity_counts", identity),
        "real_alert_feed": real,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
