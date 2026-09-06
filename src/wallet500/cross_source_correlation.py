"""Wallet500 Cross-Source Correlation Engine.

Builds a persistent asset-level evidence view across independent discovery lanes.
The correlation factor is discovery evidence only: it never bypasses Wallet500
identity, exact-pair, liquidity, survival, holder/cluster, risk or execution gates.

Core rule:
- poll forever;
- deduplicate repeated surfaces from the same source owner;
- keep prior evidence;
- when another independent source later reports the same exact asset identity,
  upgrade the discovery confirmation tier instead of treating it as a new token.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
GLOBAL_LEDGER = DATA / "global-listing-ledger.json"
CATALYST_LEDGER = DATA / "catalyst-wire-ledger.json"
EXTERNAL_ALPHA_LEDGER = DATA / "external-alpha-events.json"
OUT = DATA / "cross-source-correlation.json"
WATCHLIST = DATA / "manual-watchlist.json"

EVM_CHAINS = {"ethereum", "bsc", "arbitrum", "base"}
CHAIN_ALIASES = {
    "eth": "ethereum",
    "ethereum-mainnet": "ethereum",
    "bnb": "bsc",
    "bnb-chain": "bsc",
    "binance-smart-chain": "bsc",
    "arbitrum-one": "arbitrum",
    "sol": "solana",
}
EXCHANGE_OWNERS = {
    "binance", "coinbase", "kraken", "bybit", "okx", "kucoin", "bitget",
    "gate", "mexc", "bithumb", "coinex", "htx", "lbank", "bingx",
    "bitmart", "weex", "crypto.com", "upbit",
}
MAX_AUTO_WATCHLIST = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_chain(value: object) -> str:
    chain = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(chain, chain)


def _norm_token(token: object, chain: object) -> str:
    value = str(token or "").strip()
    c = _norm_chain(chain)
    if c in EVM_CHAINS or c == "evm_unknown" or value.startswith("0x"):
        return value.lower()
    return value


def _parse_ts(value: object) -> datetime | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _source_category(owner: str, source_kind: str = "") -> str:
    owner = str(owner or "").lower()
    kind = str(source_kind or "").lower()
    if owner in EXCHANGE_OWNERS or "exchange" in kind or "announcement" in kind:
        return "exchange"
    if owner == "moonshot" or "launchpad" in kind:
        return "launchpad"
    if "agent" in kind or "alpha" in kind:
        return "external_alpha"
    if "social" in kind:
        return "official_social"
    return "other"


def _global_observations() -> list[dict]:
    ledger = _load(GLOBAL_LEDGER, {})
    records = ledger.get("records") if isinstance(ledger, dict) else {}
    if not isinstance(records, dict):
        return []
    out: list[dict] = []
    for record_id, rec in records.items():
        if not isinstance(rec, dict):
            continue
        obs = rec.get("first_observation") or rec.get("last_observation") or {}
        if not isinstance(obs, dict):
            continue
        token = obs.get("token")
        chain = _norm_chain(obs.get("chain"))
        owner = str(obs.get("source") or "").lower()
        if not token or not chain or not owner:
            continue
        out.append({
            "evidence_id": f"global:{record_id}",
            "lane": "GLOBAL_LISTING_INTELLIGENCE",
            "source_owner": owner,
            "source_id": obs.get("surface") or owner,
            "source_kind": "OFFICIAL_EXCHANGE_OR_LAUNCHPAD_SURFACE",
            "source_category": _source_category(owner, "launchpad" if owner == "moonshot" else "exchange"),
            "source_url": obs.get("source_url"),
            "event_type": obs.get("stage") or "LISTING_DISCOVERY",
            "token": str(token),
            "chain": chain,
            "first_seen_at": rec.get("first_seen_at") or obs.get("observed_at"),
            "last_seen_at": rec.get("last_seen_at") or obs.get("observed_at"),
        })
    return out


def _catalyst_observations() -> list[dict]:
    ledger = _load(CATALYST_LEDGER, {})
    events = ledger.get("events") if isinstance(ledger, dict) else {}
    if not isinstance(events, dict):
        return []
    out: list[dict] = []
    for event_id, rec in events.items():
        if not isinstance(rec, dict):
            continue
        event = rec.get("event") or {}
        if not isinstance(event, dict):
            continue
        token = event.get("contract") or event.get("token") or event.get("mint")
        chain = _norm_chain(event.get("chain"))
        owner = str(event.get("source_owner") or event.get("source") or "").lower()
        if not token or not chain or not owner:
            continue
        out.append({
            "evidence_id": f"catalyst:{event_id}",
            "lane": "CATALYST_WIRE",
            "source_owner": owner,
            "source_id": event.get("source_id") or owner,
            "source_kind": event.get("source_kind") or "OFFICIAL_CATALYST",
            "source_category": _source_category(owner, event.get("source_kind") or ""),
            "source_url": event.get("source_url") or event.get("source_surface_url"),
            "event_type": event.get("event_type") or "OFFICIAL_CATALYST",
            "token": str(token),
            "chain": chain,
            "symbol": event.get("symbol"),
            "first_seen_at": rec.get("first_seen_at") or event.get("observed_at"),
            "last_seen_at": rec.get("last_seen_at") or event.get("observed_at"),
        })
    return out


def _external_alpha_observations() -> list[dict]:
    """Optional generic adapter for future external agents (for example Obscura).

    Expected rows may live under ``events`` or at the top level and must contain
    an exact contract/mint plus chain and a named source owner. Symbol-only rows
    are deliberately ignored so they cannot create false cross-source matches.
    """
    payload = _load(EXTERNAL_ALPHA_LEDGER, [])
    if isinstance(payload, dict):
        rows = payload.get("events") or payload.get("records") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
    else:
        rows = payload
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for i, raw in enumerate(rows):
        rec = raw.get("event") if isinstance(raw, dict) and isinstance(raw.get("event"), dict) else raw
        if not isinstance(rec, dict):
            continue
        token = rec.get("contract") or rec.get("token") or rec.get("mint")
        chain = _norm_chain(rec.get("chain") or rec.get("network"))
        owner = str(rec.get("source_owner") or rec.get("source") or rec.get("agent") or "").strip().lower()
        if not token or not chain or not owner:
            continue
        eid = rec.get("event_id") or rec.get("id") or i
        out.append({
            "evidence_id": f"external:{eid}",
            "lane": "EXTERNAL_ALPHA_INTEL",
            "source_owner": owner,
            "source_id": rec.get("source_id") or owner,
            "source_kind": rec.get("source_kind") or "EXTERNAL_ALPHA_AGENT",
            "source_category": _source_category(owner, rec.get("source_kind") or "external_alpha"),
            "source_url": rec.get("source_url") or rec.get("url"),
            "event_type": rec.get("event_type") or rec.get("decision") or "EXTERNAL_ALPHA_OBSERVATION",
            "token": str(token),
            "chain": chain,
            "symbol": rec.get("symbol"),
            "first_seen_at": rec.get("first_seen_at") or rec.get("observed_at") or rec.get("timestamp"),
            "last_seen_at": rec.get("last_seen_at") or rec.get("observed_at") or rec.get("timestamp"),
        })
    return out


def _identity_key(chain: str, token: str) -> str:
    c = _norm_chain(chain)
    return f"{c}:{_norm_token(token, c)}"


def _resolve_provisional_evm(observations: list[dict]) -> list[dict]:
    """Attach address-only EVM evidence only when one exact EVM chain is known.

    The same 0x address can theoretically exist on multiple EVM chains. We never
    merge a provisional listing observation into an exact identity if more than
    one exact chain is present for that address.
    """
    exact_by_address: dict[str, set[str]] = {}
    for obs in observations:
        chain = _norm_chain(obs.get("chain"))
        token = _norm_token(obs.get("token"), chain)
        if chain in EVM_CHAINS and token:
            exact_by_address.setdefault(token, set()).add(chain)

    resolved: list[dict] = []
    for original in observations:
        obs = dict(original)
        chain = _norm_chain(obs.get("chain"))
        token = _norm_token(obs.get("token"), chain)
        if chain == "evm_unknown":
            exact = exact_by_address.get(token, set())
            if len(exact) == 1:
                obs["chain"] = next(iter(exact))
                obs["identity_resolution"] = "PROVISIONAL_EVM_ATTACHED_TO_UNIQUE_EXACT_CHAIN"
            else:
                obs["identity_resolution"] = (
                    "PROVISIONAL_EVM_AMBIGUOUS_MULTICHAIN" if len(exact) > 1
                    else "PROVISIONAL_EVM_ADDRESS_ONLY"
                )
        resolved.append(obs)
    return resolved


def _correlate(observations: list[dict]) -> dict[str, dict]:
    observations = _resolve_provisional_evm(observations)
    grouped: dict[str, list[dict]] = {}
    for obs in observations:
        chain = _norm_chain(obs.get("chain"))
        token = str(obs.get("token") or "").strip()
        owner = str(obs.get("source_owner") or "").strip().lower()
        if not chain or not token or not owner:
            continue
        key = _identity_key(chain, token)
        grouped.setdefault(key, []).append(dict(obs))

    assets: dict[str, dict] = {}
    for key, evidence in grouped.items():
        unique_events: dict[str, dict] = {}
        for e in evidence:
            eid = str(e.get("evidence_id") or f"{e.get('source_owner')}|{e.get('source_id')}|{e.get('event_type')}|{e.get('first_seen_at')}")
            unique_events[eid] = e
        evidence = list(unique_events.values())

        owners = sorted({str(e.get("source_owner") or "").lower() for e in evidence if e.get("source_owner")})
        source_ids = sorted({str(e.get("source_id") or "") for e in evidence if e.get("source_id")})
        lanes = sorted({str(e.get("lane") or "") for e in evidence if e.get("lane")})
        categories = sorted({str(e.get("source_category") or _source_category(str(e.get("source_owner") or ""), str(e.get("source_kind") or ""))) for e in evidence})
        exchange_owners = sorted({
            str(e.get("source_owner") or "").lower()
            for e in evidence
            if _source_category(str(e.get("source_owner") or ""), str(e.get("source_kind") or "")) == "exchange"
        })

        first_values = [x for x in (_parse_ts(e.get("first_seen_at")) for e in evidence) if x]
        last_values = [x for x in (_parse_ts(e.get("last_seen_at")) for e in evidence) if x]
        first_seen = min(first_values).isoformat() if first_values else None
        last_seen = max(last_values).isoformat() if last_values else first_seen
        spread = int((max(first_values) - min(first_values)).total_seconds()) if len(first_values) >= 2 else 0

        source_count = len(owners)
        if source_count >= 5:
            tier = "HIGH_DENSITY_MULTI_SOURCE"
        elif source_count >= 3:
            tier = "MULTI_SOURCE_CONFIRMED"
        elif source_count == 2:
            tier = "DOUBLE_SOURCE_CONFIRMED"
        else:
            tier = "SINGLE_SOURCE"

        chain, token = key.split(":", 1)
        exact_identity = chain != "evm_unknown"
        assets[key] = {
            "asset_key": key,
            "chain": chain,
            "token": token,
            "symbol": next((e.get("symbol") for e in evidence if e.get("symbol")), None),
            "identity_confidence": "EXACT_CHAIN_CONTRACT" if exact_identity else "PROVISIONAL_EVM_ADDRESS_ONLY",
            "first_seen_any_source_at": first_seen,
            "last_seen_any_source_at": last_seen,
            "source_confirmation_count": source_count,
            "exchange_confirmation_count": len(exchange_owners),
            "surface_count": len(source_ids),
            "event_count": len(evidence),
            "source_category_count": len(categories),
            "sources_seen": owners,
            "exchange_sources_seen": exchange_owners,
            "source_surfaces_seen": source_ids,
            "lanes_seen": lanes,
            "source_categories_seen": categories,
            "confirmation_tier": tier,
            "discovery_confirmation_multiplier": float(min(4, max(1, source_count))),
            "source_first_seen_spread_seconds": spread,
            "continuous_rescan": True,
            "automatic_trade": False,
            "research_only_until_wallet500_gates_pass": True,
            "evidence": sorted(
                evidence,
                key=lambda e: (
                    str(e.get("first_seen_at") or ""),
                    str(e.get("source_owner") or ""),
                    str(e.get("source_id") or ""),
                ),
            )[-100:],
        }
    return assets


def _previous_counts(previous: Any) -> dict[str, int]:
    if not isinstance(previous, dict):
        return {}
    assets = previous.get("assets")
    if isinstance(assets, dict):
        return {k: int(v.get("source_confirmation_count") or 0) for k, v in assets.items() if isinstance(v, dict)}
    return {}


def _upgrade_rows(assets: dict[str, dict], previous: Any, ts: str) -> list[dict]:
    before = _previous_counts(previous)
    upgrades = []
    for key, asset in assets.items():
        old = before.get(key, 0)
        new = int(asset.get("source_confirmation_count") or 0)
        if old > 0 and new > old:
            previous_sources = set((previous.get("assets", {}).get(key, {}) or {}).get("sources_seen", [])) if isinstance(previous, dict) else set()
            upgrades.append({
                "asset_key": key,
                "at": ts,
                "previous_source_confirmation_count": old,
                "new_source_confirmation_count": new,
                "confirmation_tier": asset.get("confirmation_tier"),
                "new_sources": [s for s in asset.get("sources_seen", []) if s not in previous_sources],
            })
    return upgrades


def _watch_fields(asset: dict) -> dict:
    return {
        "cross_source_asset_key": asset.get("asset_key"),
        "cross_source_confirmation_tier": asset.get("confirmation_tier"),
        "cross_source_confirmation_count": asset.get("source_confirmation_count"),
        "cross_source_exchange_confirmation_count": asset.get("exchange_confirmation_count"),
        "cross_source_multiplier": asset.get("discovery_confirmation_multiplier"),
        "cross_source_sources": asset.get("sources_seen"),
        "cross_source_first_seen_at": asset.get("first_seen_any_source_at"),
        "cross_source_last_seen_at": asset.get("last_seen_any_source_at"),
        "cross_source_continuous_rescan": True,
    }


def _merge_watchlist(assets: dict[str, dict]) -> dict:
    current = _load(WATCHLIST, [])
    if not isinstance(current, list):
        current = []

    base = [
        dict(row) for row in current
        if isinstance(row, dict) and row.get("source") != "CROSS_SOURCE_CORRELATION"
    ]

    exact_assets = {
        key: asset for key, asset in assets.items()
        if asset.get("identity_confidence") == "EXACT_CHAIN_CONTRACT"
    }

    matched: set[str] = set()
    enriched = 0
    for row in base:
        token = row.get("token") or row.get("contract") or row.get("mint") or row.get("token_address")
        chain = _norm_chain(row.get("chain") or row.get("network"))
        if not token or not chain:
            continue
        key = _identity_key(chain, str(token))
        asset = exact_assets.get(key)
        if not asset:
            continue
        row.update(_watch_fields(asset))
        matched.add(key)
        enriched += 1

    ranked = sorted(
        (a for k, a in exact_assets.items() if k not in matched),
        key=lambda a: (
            int(a.get("source_confirmation_count") or 0),
            str(a.get("last_seen_any_source_at") or ""),
        ),
        reverse=True,
    )

    added = 0
    for asset in ranked[:MAX_AUTO_WATCHLIST]:
        base.append({
            "chain": asset["chain"],
            "token": asset["token"],
            "symbol": asset.get("symbol"),
            "source": "CROSS_SOURCE_CORRELATION",
            "research_only_until_wallet500_gates_pass": True,
            "listing_first_observed_at": asset.get("first_seen_any_source_at"),
            **_watch_fields(asset),
        })
        added += 1

    _write(WATCHLIST, base)
    return {"existing_rows_enriched": enriched, "cross_source_rows_added": added, "total_rows": len(base)}


def build(observations: list[dict] | None = None, previous: Any = None, ts: str | None = None) -> dict:
    ts = ts or _now()
    if observations is None:
        observations = _global_observations() + _catalyst_observations() + _external_alpha_observations()
    assets = _correlate(observations)
    previous = _load(OUT, {}) if previous is None else previous
    upgrades = _upgrade_rows(assets, previous, ts)
    multi = [a for a in assets.values() if int(a.get("source_confirmation_count") or 0) >= 2]
    exact = [a for a in assets.values() if a.get("identity_confidence") == "EXACT_CHAIN_CONTRACT"]
    return {
        "version": 1,
        "updated_at": ts,
        "mode": "CONTINUOUS_CROSS_SOURCE_CORRELATION_RESEARCH_ONLY",
        "automatic_trade": False,
        "policy": {
            "identity": "chain+contract/mint; EVM address-only evidence is provisional unless a unique exact chain resolves it",
            "independence": "one source owner counts once even when multiple pages/APIs/Telegram surfaces repeat it",
            "persistence": "prior evidence is retained in source ledgers; every scan recomputes and can upgrade an already-known asset",
            "multiplier": "discovery confirmation only; never multiplies or bypasses production trade gates",
            "truth_boundary": "all normal Wallet500 exact-pair, liquidity, survival, risk, holder/cluster and execution gates remain mandatory",
        },
        "counts": {
            "input_evidence": len(observations),
            "correlated_assets": len(assets),
            "exact_identity_assets": len(exact),
            "multi_source_assets": len(multi),
            "double_or_better_exchange_assets": sum(1 for a in assets.values() if int(a.get("exchange_confirmation_count") or 0) >= 2),
            "upgraded_this_scan": len(upgrades),
        },
        "upgrades": upgrades,
        "assets": assets,
    }


def run() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    payload = build()
    watch = _merge_watchlist(payload["assets"])
    payload["watchlist"] = watch
    _write(OUT, payload)
    print("CROSS SOURCE CORRELATION", json.dumps({
        **payload["counts"],
        **watch,
    }, separators=(",", ":")))
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
