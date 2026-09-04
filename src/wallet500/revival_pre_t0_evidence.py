from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "REVIVAL_PRE_T0_EVIDENCE_V1"
MODE = "RESEARCH_ONLY_IMMUTABLE_PRE_T0_EVIDENCE"
NETWORK = "solana"
DEEP_WATCH = "DEEP_WATCH"
WAKING = "WAKING_MARKET_ONLY"
MIN_AGE_DAYS = 180


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _n(value: object, default: float | None = None) -> float | None:
    try:
        x = float(value)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _rows(payload: dict, *names: str) -> list[dict]:
    for name in names:
        value = payload.get(name)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            return [x for x in value.values() if isinstance(x, dict)]
    return []


def _token(row: dict) -> str:
    return str(row.get("token_address") or row.get("contract") or row.get("mint") or row.get("token") or "").strip()


def _pair(row: dict) -> str:
    return str(row.get("dex_pair_address") or row.get("exact_pair") or row.get("pair_address") or "").strip()


def _index(payload: dict, *names: str) -> dict[str, dict]:
    return {_token(row): row for row in _rows(payload, *names) if _token(row)}


def _source_time(payload: dict) -> datetime | None:
    for key in ("generated_at", "updated_at", "source_generated_at"):
        d = _dt(payload.get(key))
        if d:
            return d
    return None


def _source_safe(payload: dict, captured_at: datetime) -> bool:
    observed = _source_time(payload)
    return observed is None or observed <= captured_at


def _holder_family(row: dict | None) -> dict:
    if not isinstance(row, dict):
        return {"verified": False, "positive": False, "status": "MISSING"}
    growth_eligible = row.get("growth_eligible") is True
    current = row.get("holder_count")
    baseline = row.get("first_holder_count")
    growth_pct = row.get("holder_growth_pct")
    horizon = {}
    for key, value in row.items():
        if key.startswith("holder_growth_") and key not in {"holder_growth_pct", "holder_growth_count"}:
            horizon[key] = value
    positive = bool(growth_eligible and _n(growth_pct, 0.0) is not None and float(_n(growth_pct, 0.0) or 0) > 0)
    return {
        "verified": growth_eligible and current is not None,
        "positive": positive,
        "status": "VERIFIED_GROWTH" if growth_eligible and current is not None else "BASELINE_OR_UNTRUSTED",
        "source": row.get("source"),
        "holder_truth_status": row.get("holder_truth_status"),
        "first_holder_count": baseline,
        "first_holder_observed_at": row.get("first_holder_observed_at"),
        "holder_count": current,
        "holder_observed_at": row.get("holder_observed_at"),
        "holder_growth_count": row.get("holder_growth_count"),
        "holder_growth_pct": growth_pct,
        "horizons": horizon,
    }


def _wallet_family(row: dict | None) -> dict:
    if not isinstance(row, dict):
        return {"verified": False, "positive": False, "status": "MISSING"}
    coverage = row.get("coverage") or {}
    h1 = (row.get("windows") or {}).get("h1") or {}
    h4 = (row.get("windows") or {}).get("h4") or {}
    quality = str(coverage.get("coverage_quality") or "")
    verified = quality == "ACCEPTABLE" and coverage.get("coverage_gap") is False
    h1_acc = int(_n(h1.get("net_accumulating_wallets"), 0) or 0)
    h1_dist = int(_n(h1.get("net_distributing_wallets"), 0) or 0)
    buyers = int(_n(h1.get("unique_buyers"), 0) or 0)
    ratio = _n(h1.get("wallet_buy_sell_ratio"), 0.0) or 0.0
    positive = bool(verified and buyers >= 2 and h1_acc > h1_dist and ratio >= 1.25)
    return {
        "verified": verified,
        "positive": positive,
        "status": "ACCUMULATION" if positive else ("VERIFIED_NO_ACCUMULATION" if verified else "PARTIAL_COVERAGE"),
        "coverage": coverage,
        "h1": h1,
        "h4": h4,
        "monitor_started_at": row.get("monitor_started_at"),
        "exact_pair": row.get("exact_pair"),
        "top_wallets_raw_verified": (row.get("top_wallets_raw_verified") or [])[:25],
    }


def _smart_money_family(wallet_row: dict | None, registry: dict) -> dict:
    if not isinstance(wallet_row, dict):
        return {"verified": False, "positive": False, "status": "NO_PREWAKING_WALLET_EVIDENCE", "qualified_wallets": []}
    registry_index = {}
    for item in registry.get("wallets") or []:
        if isinstance(item, dict) and item.get("wallet"):
            registry_index[str(item["wallet"])] = item
    qualified = []
    observed = 0
    for raw in wallet_row.get("top_wallets_raw_verified") or []:
        wallet = str(raw.get("wallet") or "")
        if not wallet:
            continue
        reg = registry_index.get(wallet)
        if not reg:
            continue
        observed += 1
        tier = (reg.get("tier_current") or {}).get("tier")
        if tier in {"ELITE", "STRONG"} and int(_n(raw.get("buys"), 0) or 0) > 0:
            qualified.append({
                "wallet": wallet,
                "tier": tier,
                "buys": raw.get("buys"),
                "sells": raw.get("sells"),
                "net_token_delta": raw.get("net_token_delta"),
                "tier_evidence": reg.get("tier_current"),
            })
    return {
        "verified": observed > 0,
        "positive": bool(qualified),
        "status": "QUALIFIED_PREWAKING_BUYER_PRESENT" if qualified else ("REGISTRY_MATCH_NO_QUALIFIED_BUYER" if observed else "NO_REGISTRY_MATCH"),
        "registry_matches": observed,
        "qualified_wallets": qualified,
        "truth_rule": "REGISTRY_TIER_WAS_ALREADY_AVAILABLE_AT_CAPTURE_TIME_AND_RAW_WALLET_HAS_VERIFIED_BUY",
    }


def _concentration_family(row: dict | None, previous: dict | None) -> dict:
    if not isinstance(row, dict):
        return {"verified": False, "positive": False, "status": "MISSING", "cluster_verified": False}
    verified = row.get("verified") is True or row.get("verified_concentration") is True
    top10 = _n(row.get("top10_pct"))
    prev_top10 = _n(((previous or {}).get("concentration") or {}).get("top10_pct"))
    delta = None if top10 is None or prev_top10 is None else round(top10 - prev_top10, 6)
    return {
        "verified": verified,
        "positive": False,
        "status": "TOKEN_ACCOUNT_CONCENTRATION_CONTEXT_ONLY" if verified else "UNVERIFIED",
        "cluster_verified": False,
        "owner_cluster_change_verified": False,
        "top1_pct": row.get("top1_pct"),
        "top5_pct": row.get("top5_pct"),
        "top10_pct": row.get("top10_pct"),
        "top20_pct": row.get("top20_pct"),
        "concentration_risk_score": row.get("concentration_risk_score"),
        "top10_change_vs_previous_capture_pct_points": delta,
        "truth_rule": "RUGCHECK_TOKEN_ACCOUNT_CONCENTRATION_IS_RISK_CONTEXT_NOT_VERIFIED_OWNER_CLUSTER_ALPHA",
    }


def _social_family(row: dict | None) -> dict:
    if not isinstance(row, dict):
        return {"verified": False, "positive": False, "status": "MISSING"}
    status = str(row.get("status") or "")
    verified = bool(status)
    positive = status in {"ORGANIC_ACCELERATION", "STRONG_ORGANIC_ACCELERATION"}
    return {
        "verified": verified,
        "positive": positive,
        "status": status or "MISSING",
        "organic_acceleration_score": row.get("organic_acceleration_score"),
        "acceleration_vs_prior_6h_hourly_baseline": row.get("acceleration_vs_prior_6h_hourly_baseline"),
        "contamination_ratio_24h": row.get("contamination_ratio_24h"),
        "current_1h": row.get("current_1h"),
        "latest_event_at": row.get("latest_event_at"),
        "truth_rule": "SOCIAL_MENTIONS_NEQ_ORGANIC_SOCIAL_ACCELERATION",
    }


def _fingerprint(snapshot: dict) -> str:
    # Fingerprint evidence families, not the frequently changing market/timestamp fields.
    # Market T0 is already frozen by Revival Forensics; this ledger exists to preserve
    # the scarce pre-WAKING evidence without exploding repository storage every 5 min.
    body = {
        "key": snapshot.get("key"),
        "families": snapshot.get("families"),
        "confirmation_shadow": snapshot.get("confirmation_shadow"),
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record_key(token: str, pair: str) -> str:
    return f"{token}|{pair.lower()}"


def _previous_record(records: list[dict], token: str, pair: str) -> dict | None:
    key = _record_key(token, pair)
    for row in reversed(records):
        if row.get("key") == key:
            return row
    return None


def _snapshot(coin: dict, captured_at: datetime, holder: dict | None, wallet: dict | None,
              registry: dict, concentration: dict | None, social: dict | None,
              previous: dict | None) -> dict:
    token = _token(coin)
    pair = _pair(coin)
    families = {
        "holder_acceleration": _holder_family(holder),
        "independent_wallet_accumulation": _wallet_family(wallet),
        "smart_money": _smart_money_family(wallet, registry),
        "concentration": _concentration_family(concentration, previous),
        "organic_social": _social_family(social),
    }
    verified = sum(1 for x in families.values() if x.get("verified") is True)
    positive = sum(1 for name, x in families.items() if name != "concentration" and x.get("positive") is True)
    snapshot = {
        "key": _record_key(token, pair),
        "network": NETWORK,
        "token_address": token,
        "symbol": coin.get("symbol"),
        "pair_address": pair,
        "captured_at": captured_at.isoformat(),
        "source_revival_generated_at": coin.get("_source_generated_at"),
        "watch_status_at_capture": coin.get("watch_status"),
        "market": {
            "revival_score_verified": coin.get("revival_score_verified"),
            "price_usd": coin.get("price_usd"),
            "pair_liquidity_usd": coin.get("dex_pair_liquidity_usd"),
            "pair_volume_24h_usd": coin.get("dex_pair_volume_24h_usd"),
            "drawdown_from_ath_pct": coin.get("drawdown_from_ath_pct"),
        },
        "families": families,
        "coverage": {
            "verified_families": verified,
            "positive_families_excluding_concentration": positive,
            "total_families": 5,
        },
        "confirmation_shadow": {
            "status": "PRE_T0_STRONG" if verified >= 4 and positive >= 3 else ("PRE_T0_CONFIRMED" if verified >= 3 and positive >= 2 else "PRE_T0_PARTIAL"),
            "production_effect": False,
            "pre_alpha_promotion": "FORBIDDEN",
        },
        "no_hindsight": True,
        "immutable_after_append": True,
        "production_portfolio_impact": "NONE",
    }
    snapshot["evidence_sha256"] = _fingerprint(snapshot)
    snapshot["record_id"] = f"PRET0-{snapshot['evidence_sha256'][:20]}"
    return snapshot


def run(data_dir: str | Path = "data", now: str | None = None) -> dict:
    data = Path(data_dir)
    captured_at = _dt(now) if now else datetime.now(timezone.utc)
    captured_at = captured_at or datetime.now(timezone.utc)

    revival = _load(data / "revival-1000-latest.json", {})
    if revival.get("network") != NETWORK or revival.get("no_hindsight") is not True or revival.get("production_portfolio_impact") != "NONE":
        raise RuntimeError("PRE_T0_REVIVAL_SOURCE_TRUTH_INVALID")

    sources = {
        "holder": _load(data / "revival-holder-latest.json", {}),
        "wallet": _load(data / "revival-prewaking-wallet-evidence.json", {}),
        "registry": _load(data / "revival-wallet-registry.json", {}),
        "concentration": _load(data / "holder-concentration-shadow.json", {}),
        "social": _load(data / "social-organic-acceleration.json", {}),
    }
    for name, payload in sources.items():
        if isinstance(payload, dict) and not _source_safe(payload, captured_at):
            sources[name] = {}

    holder_ix = _index(sources["holder"], "coins", "tokens", "rows")
    wallet_ix = _index(sources["wallet"], "tokens", "rows")
    concentration_ix = _index(sources["concentration"], "rows", "tokens", "coins")
    social_ix = _index(sources["social"], "tokens", "rows")

    ledger_path = data / "revival-pre-t0-evidence-ledger.json"
    latest_path = data / "revival-pre-t0-evidence.json"
    ledger = _load(ledger_path, {})
    if ledger and ledger.get("mode") != MODE:
        raise RuntimeError("PRE_T0_LEDGER_MODE_INVALID")
    records = ledger.setdefault("records", [])
    bindings = ledger.setdefault("waking_bindings", {})

    source_generated_at = revival.get("generated_at")
    appended = 0
    unchanged = 0
    bound = 0
    missing_binding = 0
    current = []

    coins = [x for x in (revival.get("coins") or []) if isinstance(x, dict)]
    for coin0 in coins:
        coin = dict(coin0)
        token = _token(coin)
        pair = _pair(coin)
        if not token or not pair or coin.get("market_age_verified") is not True:
            continue
        if int(_n(coin.get("market_age_min_days"), 0) or 0) < MIN_AGE_DAYS:
            continue
        coin["_source_generated_at"] = source_generated_at
        status = coin.get("watch_status")
        key = _record_key(token, pair)

        if status == DEEP_WATCH:
            previous = _previous_record(records, token, pair)
            snap = _snapshot(
                coin, captured_at, holder_ix.get(token), wallet_ix.get(token),
                sources["registry"], concentration_ix.get(token), social_ix.get(token), previous,
            )
            if previous and previous.get("evidence_sha256") == snap.get("evidence_sha256"):
                unchanged += 1
                current.append(previous)
            else:
                records.append(snap)
                appended += 1
                current.append(snap)

        elif status == WAKING and key not in bindings:
            waking_t0 = _dt(source_generated_at)
            candidates = [
                r for r in records
                if r.get("key") == key
                and waking_t0 is not None
                and (_dt(r.get("captured_at")) or captured_at) <= waking_t0
            ]
            if candidates:
                chosen = max(candidates, key=lambda r: _dt(r.get("captured_at")) or datetime.min.replace(tzinfo=timezone.utc))
                bindings[key] = {
                    "key": key,
                    "token_address": token,
                    "symbol": coin.get("symbol"),
                    "pair_address": pair,
                    "waking_first_seen_at": source_generated_at,
                    "bound_at": captured_at.isoformat(),
                    "pre_t0_record_id": chosen.get("record_id"),
                    "pre_t0_captured_at": chosen.get("captured_at"),
                    "pre_t0_evidence_sha256": chosen.get("evidence_sha256"),
                    "snapshot": chosen,
                    "status": "BOUND_TO_PRE_WAKING_EVIDENCE",
                    "no_hindsight": True,
                    "immutable": True,
                }
                bound += 1
            else:
                bindings[key] = {
                    "key": key,
                    "token_address": token,
                    "symbol": coin.get("symbol"),
                    "pair_address": pair,
                    "waking_first_seen_at": source_generated_at,
                    "bound_at": captured_at.isoformat(),
                    "pre_t0_record_id": None,
                    "snapshot": None,
                    "status": "MISSING_PRE_T0_NO_BACKFILL_ALLOWED",
                    "no_hindsight": True,
                    "immutable": True,
                }
                missing_binding += 1

    ledger.update({
        "version": VERSION,
        "mode": MODE,
        "network": NETWORK,
        "updated_at": captured_at.isoformat(),
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "truth_contract": {
            "capture_lane": "DEEP_WATCH_BEFORE_WAKING_ONLY",
            "waking_binding": "LATEST_EXISTING_EXACT_TOKEN_EXACT_PAIR_RECORD_ONLY",
            "retroactive_backfill_after_waking": "FORBIDDEN",
            "missing_evidence_imputed": False,
            "concentration_positive_alpha": False,
            "raw_social_mentions_are_organic_alpha": False,
        },
        "records": records,
        "waking_bindings": bindings,
    })
    _write(ledger_path, ledger)

    active_bindings = []
    for coin in coins:
        if coin.get("watch_status") == WAKING:
            key = _record_key(_token(coin), _pair(coin))
            if key in bindings:
                active_bindings.append(bindings[key])

    payload = {
        "version": VERSION,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": captured_at.isoformat(),
        "source_revival_generated_at": source_generated_at,
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "counts": {
            "records_total": len(records),
            "records_appended_this_run": appended,
            "unchanged_deduped_this_run": unchanged,
            "waking_bindings_total": len(bindings),
            "waking_bound_this_run": bound,
            "waking_missing_pre_t0_this_run": missing_binding,
            "active_deep_watch_snapshots": len(current),
            "active_waking_bindings": len(active_bindings),
        },
        "truth_contract": ledger["truth_contract"],
        "active_deep_watch": current,
        "active_waking_bindings": active_bindings,
    }
    _write(latest_path, payload)
    return payload


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
