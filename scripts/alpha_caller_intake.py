from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "data/alpha-caller-inbox.json"
EVENTS = ROOT / "data/close-watch-events.json"
OUT = ROOT / "data/alpha-caller-candidates.json"
UA = "Wallet500-AlphaCallerIntel/1.2"

CHAIN = {
    "eth": "ethereum",
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "base": "base",
    "bsc": "bsc",
    "optimism": "optimism",
    "polygon": "polygon",
    "solana": "solana",
}
DS_TO_NETWORK = {
    "ethereum": "eth",
    "arbitrum": "arbitrum",
    "base": "base",
    "bsc": "bsc",
    "optimism": "optimism",
    "polygon": "polygon",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_json(url: str, timeout: int = 12):
    try:
        with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def valid_evm(value) -> bool:
    value = str(value or "")
    return value.startswith("0x") and len(value) == 42 and all(c in "0123456789abcdefABCDEF" for c in value[2:])


def valid_sol(value) -> bool:
    return 32 <= len(str(value or "")) <= 44 and not str(value).startswith("0x")


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def pair_age_minutes(pair: dict, current: datetime | None = None) -> float | None:
    try:
        created_ms = float(pair.get("pairCreatedAt") or 0)
    except (TypeError, ValueError):
        return None
    if created_ms <= 0:
        return None
    created = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc)
    current = current or datetime.now(timezone.utc)
    return max(0.0, (current - created).total_seconds() / 60.0)


def liquid_exact_pairs(pairs, contract: str, allowed_chain: str | None = None):
    exact = []
    for pair in pairs:
        chain_id = str(pair.get("chainId") or "").lower()
        if allowed_chain and chain_id != allowed_chain:
            continue
        base = str((pair.get("baseToken") or {}).get("address", "")).lower()
        quote = str((pair.get("quoteToken") or {}).get("address", "")).lower()
        if contract.lower() not in (base, quote):
            continue
        try:
            liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            liquidity = 0
        if liquidity > 0:
            exact.append((liquidity, pair))
    return exact


def main() -> None:
    inbox = json.loads(INBOX.read_text()) if INBOX.exists() else {"calls": []}
    calls = inbox.get("calls") or []
    bus = json.loads(EVENTS.read_text()) if EVENTS.exists() else {"version": 2, "events": []}
    events = bus.get("events") or []
    results = []
    added = 0

    for call in calls:
        caller = str(call.get("caller") or "").strip()
        source = str(call.get("source") or "").strip()
        contract = str(call.get("contract") or "").strip()
        input_network = str(call.get("network") or "").lower().strip()
        network = input_network
        ts = parse_time(call.get("called_at"))
        role = str(call.get("signal_role") or "candidate_discovery")
        result = {
            "caller": caller,
            "origin_caller": call.get("origin_caller") or caller,
            "source": source,
            "source_id": call.get("source_id"),
            "source_class": call.get("source_class"),
            "independence_group": call.get("independence_group"),
            "independence_key": call.get("independence_key"),
            "source_post_id": call.get("source_post_id"),
            "historical_evidence_grade": call.get("historical_evidence_grade"),
            "discovery_priority": call.get("discovery_priority"),
            "contract": contract,
            "network": input_network,
            "called_at": call.get("called_at"),
            "status": "REJECTED",
            "reasons": [],
            "observed_at": now(),
            "signal_role": role,
        }

        if not caller or not source or not ts:
            result["reasons"].append("MISSING_CALL_IDENTITY_OR_TIMESTAMP")
        if input_network == "evm":
            if not valid_evm(contract):
                result["reasons"].append("INVALID_EVM_CONTRACT")
        elif input_network not in CHAIN:
            result["reasons"].append("UNSUPPORTED_NETWORK")
        elif input_network == "solana" and not valid_sol(contract):
            result["reasons"].append("INVALID_SOLANA_CONTRACT")
        elif input_network != "solana" and not valid_evm(contract):
            result["reasons"].append("INVALID_EVM_CONTRACT")
        if not contract:
            result["reasons"].append("MISSING_CONTRACT")

        ds = get_json("https://api.dexscreener.com/latest/dex/tokens/" + contract) if contract and not result["reasons"] else None
        pairs = (ds or {}).get("pairs") or []
        liquid = []

        if not result["reasons"] and input_network == "evm":
            supported_pairs = []
            for chain_id in DS_TO_NETWORK:
                supported_pairs.extend(liquid_exact_pairs(pairs, contract, chain_id))
            chains = {
                str(pair.get("chainId") or "").lower()
                for _, pair in supported_pairs
            }
            if len(chains) == 1:
                resolved_chain = next(iter(chains))
                network = DS_TO_NETWORK[resolved_chain]
                result["network"] = network
                result["resolved_from_network"] = "evm"
                liquid = supported_pairs
            elif len(chains) > 1:
                result["reasons"].append("AMBIGUOUS_EVM_CHAIN")
            else:
                result["reasons"].append("NO_SUPPORTED_EVM_CHAIN_VERIFIED_LIVE_LIQUID_MARKET")
        elif not result["reasons"]:
            wanted = CHAIN.get(input_network)
            liquid = liquid_exact_pairs(pairs, contract, wanted)
            if not liquid:
                result["reasons"].append("NO_CHAIN_VERIFIED_LIVE_LIQUID_MARKET")

        if result["reasons"]:
            results.append(result)
            continue

        liquidity, pair = max(liquid, key=lambda item: item[0])
        pair_address = str(pair.get("pairAddress") or "")
        symbol = str(call.get("symbol") or (pair.get("baseToken") or {}).get("symbol") or "UNKNOWN").upper()
        event_kind = "alpha_source_market_confirmation" if role == "confirmation_only" else "verified_alpha_caller_call"
        direction = 0 if role == "confirmation_only" else 1
        result.update(
            {
                "status": "GATED_CONFIRMATION_ONLY" if role == "confirmation_only" else "GATED_RESEARCH_CANDIDATE",
                "pair": pair_address,
                "liquidity_usd": liquidity,
                "dex_url": pair.get("url"),
                "symbol": symbol,
                "price_usd": pair.get("priceUsd"),
                "market_cap_usd": pair.get("marketCap"),
                "fdv_usd": pair.get("fdv"),
                "pair_created_at_ms": pair.get("pairCreatedAt"),
                "pair_age_minutes_at_intake": pair_age_minutes(pair),
                "volume_h1_usd": (pair.get("volume") or {}).get("h1"),
                "buys_h1": ((pair.get("txns") or {}).get("h1") or {}).get("buys"),
                "sells_h1": ((pair.get("txns") or {}).get("h1") or {}).get("sells"),
                "price_change_m5_pct": (pair.get("priceChange") or {}).get("m5"),
                "price_change_h1_pct": (pair.get("priceChange") or {}).get("h1"),
                "reasons": [
                    "CONFIRMATION_ONLY_DOES_NOT_CREATE_BUY_SIGNAL"
                    if role == "confirmation_only"
                    else "CALLER_SIGNAL_DOES_NOT_BYPASS_WALLET500_GATES"
                ],
            }
        )

        canonical_id = (
            f"alpha-call:{role}:{source}:{caller}:{network}:{contract.lower()}:{ts.isoformat()}"
        )
        if not any(event.get("canonical_event_id") == canonical_id for event in events):
            events.append(
                {
                    "symbol": symbol,
                    "network": network,
                    "contract": contract,
                    "pair": pair_address,
                    "family": "attention_social",
                    "kind": event_kind,
                    "direction": direction,
                    "strength": float(call.get("caller_strength") or 25),
                    "confidence": float(call.get("caller_confidence") or 30),
                    "source": source,
                    "subject": caller,
                    "source_url": str(call.get("source_url") or ""),
                    "canonical_event_id": canonical_id,
                    "event_time": ts.isoformat(),
                    "observed_at": now(),
                    "free_source": True,
                    "research_only": True,
                    "requires_full_wallet500_gates": True,
                    "liquidity_usd_at_intake": liquidity,
                    "price_usd_at_intake": result.get("price_usd"),
                    "market_cap_usd_at_intake": result.get("market_cap_usd"),
                    "fdv_usd_at_intake": result.get("fdv_usd"),
                    "pair_created_at_ms": result.get("pair_created_at_ms"),
                    "pair_age_minutes_at_intake": result.get("pair_age_minutes_at_intake"),
                    "volume_h1_usd_at_intake": result.get("volume_h1_usd"),
                    "buys_h1_at_intake": result.get("buys_h1"),
                    "sells_h1_at_intake": result.get("sells_h1"),
                    "price_change_m5_pct_at_intake": result.get("price_change_m5_pct"),
                    "price_change_h1_pct_at_intake": result.get("price_change_h1_pct"),
                    "timestamp_semantics": call.get("timestamp_semantics"),
                    "signal_role": role,
                    "source_id": call.get("source_id"),
                    "source_class": call.get("source_class"),
                    "origin_caller": call.get("origin_caller") or caller,
                    "independence_group": call.get("independence_group"),
                    "independence_key": call.get("independence_key"),
                    "source_post_id": call.get("source_post_id"),
                    "historical_evidence_grade": call.get("historical_evidence_grade"),
                    "discovery_priority": call.get("discovery_priority"),
                }
            )
            added += 1
        results.append(result)

    EVENTS.write_text(
        json.dumps({"version": 2, "generated_at": now(), "events": events}, indent=2, ensure_ascii=False) + "\n"
    )
    OUT.write_text(
        json.dumps({"version": 3, "generated_at": now(), "candidates": results}, indent=2, ensure_ascii=False) + "\n"
    )
    print(
        json.dumps(
            {
                "status": "OK",
                "calls_seen": len(calls),
                "events_added": added,
                "gated_candidates": sum(x["status"] == "GATED_RESEARCH_CANDIDATE" for x in results),
                "confirmation_only": sum(x["status"] == "GATED_CONFIRMATION_ONLY" for x in results),
                "rejected": sum(x["status"] == "REJECTED" for x in results),
            }
        )
    )


if __name__ == "__main__":
    main()
