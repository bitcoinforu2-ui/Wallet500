from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
LATEST = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-strict-t0.json"
NETWORK = "solana"
MODE = "FORWARD_LOCKED_STRICT_T0_V1"
EXPANSION_SOURCE = "revival_discovery_state+dexscreener_absorption_expansion"


def n(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def strict_key(token: str, pair: str) -> str:
    return f"{NETWORK}:{token}:{pair.lower()}"


def empty_state() -> dict:
    return {
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "no_hindsight": True,
        "records": {},
    }


def load_state(path: Path = STATE) -> dict:
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text())
    except Exception:
        return empty_state()
    if state.get("network") != NETWORK or state.get("no_hindsight") is not True:
        raise RuntimeError("STRICT_T0_STATE_TRUTH_CONTRACT_INVALID")
    state.setdefault("records", {})
    state["mode"] = MODE
    return state


def is_green_strict_expansion(coin: dict) -> bool:
    flow = coin.get("order_flow_absorption") or {}
    return all([
        coin.get("source") == EXPANSION_SOURCE,
        coin.get("absorption_candidate_proxy") is True,
        coin.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR",
        bool(str(coin.get("token_address") or "").strip()),
        bool(str(coin.get("dex_pair_address") or "").strip()),
        flow.get("signal") is True,
    ])


def lock_or_read_strict_t0(state: dict, coin: dict, observed_at: str) -> tuple[dict | None, bool]:
    if not is_green_strict_expansion(coin):
        return None, False

    token = str(coin.get("token_address") or "").strip()
    pair = str(coin.get("dex_pair_address") or "").strip()
    price = n(coin.get("price_usd"))
    if price <= 0:
        return None, False

    records = state.setdefault("records", {})
    key = strict_key(token, pair)
    created = key not in records
    if created:
        flow = coin.get("order_flow_absorption") or {}
        records[key] = {
            "network": NETWORK,
            "token_address": token,
            "pair_address": pair,
            "symbol_at_discovery": str(coin.get("symbol") or ""),
            "strict_first_seen_at": observed_at,
            "strict_discovery_price_usd": price,
            "strict_grade_at_discovery": flow.get("strict_grade"),
            "strict_level_at_discovery": flow.get("strict_level"),
            "source": "FORWARD_LOCKED_FIRST_GREEN_STRICT_EXACT_PAIR",
            "no_hindsight": True,
            "immutable_t0": True,
        }
    return records[key], created


def enrich_payload(payload: dict, state: dict, observed_at: str | None = None) -> tuple[dict, dict]:
    observed_at = observed_at or now_iso()
    created_count = 0
    current_count = 0

    for coin in payload.get("coins") or []:
        record, created = lock_or_read_strict_t0(state, coin, observed_at)
        if not record:
            coin.pop("strict_discovery", None)
            continue
        created_count += int(created)
        current_count += 1
        discovery = n(record.get("strict_discovery_price_usd"))
        current = n(coin.get("price_usd"))
        return_pct = ((current / discovery) - 1.0) * 100.0 if discovery > 0 and current > 0 else None
        coin["strict_discovery"] = {
            "strict_first_seen_at": record.get("strict_first_seen_at"),
            "discovery_price_usd": discovery,
            "snapshot_price_usd": current if current > 0 else None,
            "snapshot_return_since_discovery_pct": None if return_pct is None else round(return_pct, 6),
            "pair_address": record.get("pair_address"),
            "source": record.get("source"),
            "no_hindsight": True,
            "immutable_t0": True,
        }

    counts = payload.setdefault("counts", {})
    counts["strict_green_t0_current"] = current_count
    counts["strict_green_t0_new"] = created_count
    counts["strict_green_t0_state_records"] = len(state.get("records") or {})
    payload["strict_discovery_contract"] = {
        "version": MODE,
        "research_only": True,
        "production_portfolio_impact": "NONE",
        "scope": "GREEN_STRICT_DISCOVERY_EXPANSION_ONLY",
        "t0_rule": "FIRST_FORWARD_OBSERVATION_WHILE_STRICT_ON_EXACT_PAIR",
        "pair_identity": "TOKEN_PLUS_EXACT_PAIR_ADDRESS",
        "discovery_price_mutation": "FORBIDDEN_AFTER_FIRST_LOCK",
        "no_hindsight": True,
        "dashboard_return_rule": "LIVE_EXACT_PAIR_PRICE_VS_IMMUTABLE_STRICT_DISCOVERY_PRICE",
    }
    return payload, state


def main() -> None:
    if not LATEST.exists():
        raise SystemExit("REVIVAL_STRICT_T0_LATEST_MISSING")
    payload = json.loads(LATEST.read_text())
    if payload.get("network") != NETWORK or payload.get("production_portfolio_impact") != "NONE":
        raise SystemExit("REVIVAL_STRICT_T0_UNSAFE_INPUT")

    state = load_state()
    payload, state = enrich_payload(payload, state)
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print(json.dumps({
        "strict_green_t0_current": (payload.get("counts") or {}).get("strict_green_t0_current", 0),
        "strict_green_t0_new": (payload.get("counts") or {}).get("strict_green_t0_new", 0),
        "strict_green_t0_state_records": len(state.get("records") or {}),
    }))


if __name__ == "__main__":
    main()
