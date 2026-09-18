from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY = "buy-zone-close-watch-registry.json"
EVM_CHAINS = {
    "ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast",
}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def _now_iso(now: datetime | None = None) -> str:
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref.astimezone(timezone.utc).isoformat()


def _chain(value: object) -> str:
    raw = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(raw, raw)


def _addr(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM_CHAINS else raw


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def exact_key(row: object) -> str:
    if not isinstance(row, dict):
        return ""
    chain = _chain(row.get("chain") or row.get("network"))
    token = _addr(chain, row.get("token_address") or row.get("token") or row.get("mint") or row.get("contract"))
    pair = _addr(chain, row.get("pair_address") or row.get("pair") or row.get("locked_pair_address"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def _final_buy(row: dict) -> bool:
    decision = row.get("telegram_buy_decision")
    if not isinstance(decision, dict):
        return False
    return (
        decision.get("recommended_action") == "BUY"
        and decision.get("state") == "BUY_ZONE"
        and str(decision.get("model_signal") or "") in {"BUY", "STRONG_BUY"}
    )


def _price(row: dict) -> float | None:
    for key in (
        "current_price_usd",
        "current_price",
        "price_usd",
        "exact_pair_price_usd",
        "entry_price_usd",
        "discovery_price",
    ):
        try:
            value = float(row.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    try:
        value = float(market.get("price_usd") or market.get("price") or 0)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def upsert_buy_zone_registry(
    output_dir: str | Path,
    rows: list[dict],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist every exact-pair final BUY into the permanent close-watch registry.

    A BUY activation is never silently removed by a later research state. Removal
    requires a separate explicit exit/deactivation policy. This makes the close
    watch durable across workflows and process restarts.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / REGISTRY
    existing = _load(path, {"version": 1, "entries": {}})
    entries = existing.get("entries") if isinstance(existing, dict) and isinstance(existing.get("entries"), dict) else {}
    entries = dict(entries)
    observed_at = _now_iso(now)

    activated: list[str] = []
    refreshed: list[str] = []

    for row in rows or []:
        if not isinstance(row, dict) or not _final_buy(row):
            continue
        key = exact_key(row)
        if not key:
            continue
        chain, token, pair = key.split(":", 2)
        previous = entries.get(key) if isinstance(entries.get(key), dict) else {}
        decision = row.get("telegram_buy_decision") or {}
        scores = decision.get("scores") if isinstance(decision.get("scores"), dict) else {}
        is_new = not bool(previous)

        entry = dict(previous)
        entry.update({
            "identity_key": key,
            "candidate_type": "BUY_ZONE",
            "symbol": str(row.get("symbol") or row.get("base_token_symbol") or previous.get("symbol") or "UNKNOWN").upper(),
            "network": chain,
            "contract": token,
            "pair": pair,
            "dex_url": row.get("dex_url") or row.get("url") or previous.get("dex_url") or "",
            "source": "DECISION_ENGINE_V1_BUY_ZONE",
            "source_alert_id": row.get("alert_event_id") or row.get("alert_id") or previous.get("source_alert_id"),
            "active": True,
            "priority": "HIGHEST",
            "close_watch": "HIGHEST",
            "collector_priority": 0,
            "deep_investigation": True,
            "full_intelligence": True,
            "wallet_holder_intelligence": True,
            "attention_social_intelligence": True,
            "search_news_intelligence": True,
            "market_microstructure_intelligence": True,
            "derivatives_intelligence": bool(row.get("derivatives_intelligence") or previous.get("derivatives_intelligence")),
            "derivatives_symbol": row.get("derivatives_symbol") or previous.get("derivatives_symbol"),
            "automatic_trade": False,
            "manual_decision_only": True,
            "activation_reason": "FINAL_BUY_ZONE",
            "model_signal": decision.get("model_signal"),
            "decision_scores": scores,
            "last_buy_at": observed_at,
            "last_seen_at": observed_at,
            "buy_signal_count": int(previous.get("buy_signal_count") or 0) + (1 if is_new else 0),
        })
        if not entry.get("first_buy_at"):
            entry["first_buy_at"] = observed_at
        price = _price(row)
        if price is not None:
            entry["buy_zone_price_usd"] = price
            if entry.get("first_buy_price_usd") is None:
                entry["first_buy_price_usd"] = price

        entries[key] = entry
        (activated if is_new else refreshed).append(key)

    payload = {
        "version": 1,
        "updated_at": observed_at,
        "mode": "FINAL_BUY_TO_UNIFIED_CLOSE_WATCH",
        "truth_contract": {
            "source_requires_final_buy_zone": True,
            "exact_chain_contract_pair_required": True,
            "close_watch_priority": "HIGHEST",
            "deep_intelligence_required": True,
            "automatic_trade": False,
            "no_silent_auto_deactivation": True,
        },
        "active_count": sum(1 for x in entries.values() if isinstance(x, dict) and x.get("active") is True),
        "activated_this_run": activated,
        "refreshed_this_run": refreshed,
        "entries": entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def active_registry_candidates(output_dir: str | Path) -> list[dict]:
    payload = _load(Path(output_dir) / REGISTRY, {"entries": {}})
    entries = payload.get("entries") if isinstance(payload, dict) and isinstance(payload.get("entries"), dict) else {}
    rows = [dict(x) for x in entries.values() if isinstance(x, dict) and x.get("active") is True and exact_key(x)]
    rows.sort(key=lambda x: str(x.get("first_buy_at") or ""))
    return rows
