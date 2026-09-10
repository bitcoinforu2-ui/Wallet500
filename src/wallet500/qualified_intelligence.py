"""Automatic post-qualification intelligence for Wallet500.

This module is a research-only enrichment lane.  It starts when a token has
already crossed an existing Wallet500 qualification threshold and must never
promote, demote, or bypass production gates by itself.

The lane captures point-in-time evidence for:
* public exchange / Moonshot listing and pre-listing surfaces;
* exact-contract social/news context and organic attention inputs;
* holder growth when a verified provider is configured;
* Solana whale concentration (>= 0.1% supply) and balance deltas;
* material external catalysts.

A balance delta is NOT called a buy/sell without verified swap evidence.
Unsupported data fails closed and is recorded as unavailable rather than guessed.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .waking_confirmation import (
    _identity,
    _scan_birdeye,
    _scan_news,
    _scan_reddit,
    _scan_x,
    _scan_youtube,
)

DATA = Path("data")
QUALIFIED = DATA / "qualified-candidates.json"
REVIVAL_QUALIFIED = DATA / "revival-qualified.json"
LISTING_LEDGER = DATA / "global-listing-ledger.json"
ORGANIC = DATA / "social-organic-acceleration.json"
STATE = DATA / "qualified-intelligence-state.json"
DOSSIERS = DATA / "qualified-intelligence-dossiers.json"
LEDGER = DATA / "qualified-intelligence-ledger.json"

MODE = "RESEARCH_ONLY_POST_QUALIFICATION_INTELLIGENCE_V1"
WHALE_SUPPLY_PCT = 0.1
MAX_TARGETS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _n(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _key(chain: str, token: str) -> str:
    chain = str(chain or "").lower()
    token = str(token or "")
    return f"{chain}:{token.lower() if chain in {'ethereum', 'bsc'} else token}"


def _targets() -> list[dict]:
    rows: list[dict] = []
    seen = set()
    for path, allowed in (
        (QUALIFIED, {"QUALIFIED"}),
        (REVIVAL_QUALIFIED, {"REVIVAL_QUALIFIED"}),
    ):
        payload = _load(path, [])
        if not isinstance(payload, list):
            continue
        for row in payload:
            if not isinstance(row, dict) or row.get("qualification") not in allowed:
                continue
            chain = str(row.get("chain") or "").lower()
            token = str(row.get("token") or row.get("mint") or "")
            pair = str(row.get("pair_address") or "")
            if not chain or not token:
                continue
            k = _key(chain, token)
            if k in seen:
                continue
            seen.add(k)
            rows.append({**row, "chain": chain, "token": token, "pair_address": pair})
    rows.sort(key=lambda x: str(x.get("qualified_at") or x.get("observed_at") or ""), reverse=True)
    return rows[:MAX_TARGETS]


def _contains_exact_token(obj, token: str) -> bool:
    needle = token.lower()
    if isinstance(obj, dict):
        return any(_contains_exact_token(v, token) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_exact_token(v, token) for v in obj)
    if isinstance(obj, str):
        return needle in obj.lower()
    return False


def _listing_matches(token: str) -> list[dict]:
    payload = _load(LISTING_LEDGER, {})
    records = payload.get("records") if isinstance(payload, dict) else {}
    out = []
    if not isinstance(records, dict):
        return out
    for rec in records.values():
        if not isinstance(rec, dict) or not _contains_exact_token(rec, token):
            continue
        obs = rec.get("last_observation") or rec.get("first_observation") or {}
        out.append({
            "source": obs.get("source"),
            "surface": obs.get("surface"),
            "stage": obs.get("stage"),
            "source_url": obs.get("source_url"),
            "first_seen_at": rec.get("first_seen_at"),
            "last_seen_at": rec.get("last_seen_at"),
            "exact_contract_match": True,
        })
    return out[:30]


def _organic_match(token: str):
    payload = _load(ORGANIC, {})
    for row in payload.get("tokens") or [] if isinstance(payload, dict) else []:
        if isinstance(row, dict) and str(row.get("contract") or "") == token:
            return row
    return None


def _rpc(url: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "Wallet500-QualifiedIntel/1.0"})
    with urlopen(req, timeout=18) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError(str(payload["error"])[:240])
    return payload.get("result")


def _solana_whales(token: str, previous: dict) -> tuple[dict, dict]:
    """Return owner-aggregated top holders and point-in-time balance deltas.

    Solana getTokenLargestAccounts returns token accounts, so we resolve each
    token account's parsed owner before aggregation.  A balance increase/decrease
    remains a balance-flow observation only; it is never labelled BUY/SELL here.
    """
    rpc = (os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com").strip()
    try:
        supply_res = _rpc(rpc, "getTokenSupply", [token, {"commitment": "confirmed"}]) or {}
        supply_v = (supply_res.get("value") or {}) if isinstance(supply_res, dict) else {}
        supply = _n(supply_v.get("uiAmountString") or supply_v.get("uiAmount"))
        if not supply or supply <= 0:
            return {"status": "SUPPLY_UNAVAILABLE"}, previous
        threshold = supply * (WHALE_SUPPLY_PCT / 100.0)
        largest = _rpc(rpc, "getTokenLargestAccounts", [token, {"commitment": "confirmed"}]) or {}
        accounts = (largest.get("value") or []) if isinstance(largest, dict) else []
        owners: dict[str, float] = {}
        unresolved = 0
        for row in accounts[:20]:
            account = str((row or {}).get("address") or "")
            amount = _n((row or {}).get("uiAmountString") or (row or {}).get("uiAmount"), 0.0) or 0.0
            if not account or amount <= 0:
                continue
            try:
                info = _rpc(rpc, "getAccountInfo", [account, {"encoding": "jsonParsed", "commitment": "confirmed"}]) or {}
                value = info.get("value") if isinstance(info, dict) else None
                parsed = (((value or {}).get("data") or {}).get("parsed") or {}) if isinstance(value, dict) else {}
                owner = str(((parsed.get("info") or {}).get("owner")) or "")
            except Exception:
                owner = ""
            if not owner:
                unresolved += 1
                owner = f"TOKEN_ACCOUNT:{account}"
            owners[owner] = owners.get(owner, 0.0) + amount

        whales = {o: a for o, a in owners.items() if a >= threshold}
        prev_balances = previous.get("balances") if isinstance(previous, dict) and isinstance(previous.get("balances"), dict) else {}
        changes = []
        for owner in sorted(set(prev_balances) | set(whales)):
            before = _n(prev_balances.get(owner), 0.0) or 0.0
            after = _n(whales.get(owner), 0.0) or 0.0
            delta = after - before
            if abs(delta) <= max(supply * 0.00005, 1e-12):
                continue
            changes.append({
                "wallet": owner,
                "before": before,
                "after": after,
                "delta": delta,
                "delta_supply_pct": round(delta / supply * 100.0, 6),
                "flow": "BALANCE_INCREASE" if delta > 0 else "BALANCE_DECREASE",
                "swap_verified": False,
                "buy_sell_label": None,
            })
        rows = [
            {"wallet": owner, "balance": amount, "supply_pct": round(amount / supply * 100.0, 6)}
            for owner, amount in sorted(whales.items(), key=lambda x: x[1], reverse=True)
        ]
        snapshot = {"supply": supply, "threshold_tokens": threshold, "balances": whales}
        return {
            "status": "OK",
            "definition": "OWNER_BALANCE_GTE_0_1_PERCENT_TOTAL_SUPPLY",
            "supply": supply,
            "threshold_tokens": threshold,
            "whale_count_top20_resolved": len(rows),
            "unresolved_token_accounts": unresolved,
            "whales": rows,
            "balance_changes": changes,
            "truth_rule": "BALANCE_DELTA_IS_NOT_BUY_OR_SELL_WITHOUT_VERIFIED_SWAP_EVIDENCE",
        }, snapshot
    except Exception as exc:
        return {"status": f"UNAVAILABLE:{type(exc).__name__}", "truth_rule": "NO_GUESSING"}, previous


def _social_events(identity: dict) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    statuses: list[dict] = []
    for fn in (_scan_x, _scan_reddit, _scan_youtube, _scan_news):
        try:
            rows, status = fn(identity)
            statuses.append(status)
            events.extend(rows or [])
        except Exception as exc:
            statuses.append({"provider": getattr(fn, "__name__", "unknown"), "status": type(exc).__name__})
    mint = str(identity.get("token_address") or "")
    exact = []
    contextual = []
    for event in events:
        text = str(event.get("text") or "")
        row = {**event, "exact_contract_match": bool(mint and mint in text)}
        (exact if row["exact_contract_match"] else contextual).append(row)
    # Exact-CA evidence gets priority; contextual name/ticker material remains
    # visible research evidence but cannot be treated as an endorsement.
    return (exact + contextual)[:80], statuses


def _holder_layer(chain: str, token: str, state_row: dict, observed_at: str):
    if chain != "solana":
        return {"status": "NOT_IMPLEMENTED_FOR_CHAIN", "chain": chain}, state_row, {"provider": "holders", "status": "NOT_IMPLEMENTED_FOR_CHAIN"}
    holders, wallets, new_state, provider = _scan_birdeye(token, state_row, observed_at)
    return {
        "status": "OK" if holders or wallets else provider.get("status", "UNAVAILABLE"),
        "holders": holders,
        "unique_wallet_activity": wallets,
    }, new_state, provider


def run(output_dir: str | Path = "data") -> dict:
    global DATA, QUALIFIED, REVIVAL_QUALIFIED, LISTING_LEDGER, ORGANIC, STATE, DOSSIERS, LEDGER
    DATA = Path(output_dir)
    QUALIFIED = DATA / "qualified-candidates.json"
    REVIVAL_QUALIFIED = DATA / "revival-qualified.json"
    LISTING_LEDGER = DATA / "global-listing-ledger.json"
    ORGANIC = DATA / "social-organic-acceleration.json"
    STATE = DATA / "qualified-intelligence-state.json"
    DOSSIERS = DATA / "qualified-intelligence-dossiers.json"
    LEDGER = DATA / "qualified-intelligence-ledger.json"
    DATA.mkdir(parents=True, exist_ok=True)

    observed_at = _now()
    state = _load(STATE, {"version": 1, "tokens": {}})
    token_state = state.setdefault("tokens", {})
    ledger = _load(LEDGER, {"version": 1, "events": []})
    ledger_events = list(ledger.get("events") or [])
    dossiers = []

    for candidate in _targets():
        chain = candidate["chain"]
        token = candidate["token"]
        k = _key(chain, token)
        prior = token_state.get(k) if isinstance(token_state.get(k), dict) else {}
        first_seen = prior.get("first_qualified_seen_at") or observed_at
        first_crossing = not bool(prior.get("first_qualified_seen_at"))

        identity = {
            "token_address": token,
            "symbol": candidate.get("base_token_symbol") or candidate.get("symbol"),
            "name": candidate.get("base_token_name") or candidate.get("name"),
            "coingecko_id": None,
            "official_x": None,
            "official_telegram": None,
            "official_discord": None,
            "official_website": None,
            "official_reddit": None,
            "github_repos": [],
        }
        identity_status = []
        if chain == "solana" and candidate.get("pair_address"):
            try:
                enriched, identity_status = _identity({
                    "token_address": token,
                    "dex_pair_address": candidate.get("pair_address"),
                    "symbol": identity["symbol"],
                    "name": identity["name"],
                    "id": None,
                })
                identity.update({kk: vv for kk, vv in enriched.items() if vv not in (None, "", [])})
            except Exception as exc:
                identity_status = [{"provider": "identity", "status": type(exc).__name__}]

        social, social_status = _social_events(identity)
        holder_state = prior.get("holder_state") if isinstance(prior.get("holder_state"), dict) else {}
        holders, holder_state, holder_provider = _holder_layer(chain, token, holder_state, observed_at)
        whale_state = prior.get("whale_state") if isinstance(prior.get("whale_state"), dict) else {}
        if chain == "solana":
            whales, whale_state = _solana_whales(token, whale_state)
        else:
            whales = {"status": "NOT_IMPLEMENTED_FOR_CHAIN", "chain": chain, "truth_rule": "NO_GUESSING"}

        listings = _listing_matches(token)
        organic = _organic_match(token)
        dossier = {
            "observed_at": observed_at,
            "first_qualified_seen_at": first_seen,
            "first_crossing_capture": first_crossing,
            "chain": chain,
            "token": token,
            "pair_address": candidate.get("pair_address"),
            "qualification": candidate.get("qualification"),
            "qualified_at": candidate.get("qualified_at"),
            "market_at_check": {
                "price_usd": candidate.get("price_usd"),
                "liquidity_usd": candidate.get("liquidity_usd"),
                "volume_h1": candidate.get("volume_h1"),
                "volume_h24": candidate.get("volume_h24"),
                "market_cap": candidate.get("market_cap"),
                "anomaly_score": candidate.get("anomaly_score"),
                "revival_score": candidate.get("revival_score"),
            },
            "identity": identity,
            "listing_intelligence": listings,
            "moonshot_exact_contract_seen": any(str(x.get("source") or "").lower() == "moonshot" for x in listings),
            "social_news": social,
            "organic_social": organic,
            "holders": holders,
            "whales_gte_0_1pct": whales,
            "provider_status": identity_status + social_status + [holder_provider],
            "research_only": True,
            "production_impact": "NONE",
            "no_hindsight": True,
            "truth_rules": [
                "EXACT_CONTRACT_EVIDENCE_OUTRANKS_NAME_OR_TICKER_CONTEXT",
                "SOCIAL_MENTIONS_NEQ_ORGANIC_SOCIAL_ACCELERATION",
                "BALANCE_DELTA_NEQ_BUY_SELL_WITHOUT_SWAP_EVIDENCE",
                "UNAVAILABLE_DATA_IS_NEVER_GUESSED",
                "POST_QUALIFICATION_RESEARCH_CANNOT_BYPASS_PRODUCTION_GATES",
            ],
        }
        dossiers.append(dossier)
        token_state[k] = {
            **prior,
            "chain": chain,
            "token": token,
            "first_qualified_seen_at": first_seen,
            "last_checked_at": observed_at,
            "holder_state": holder_state,
            "whale_state": whale_state,
        }
        ledger_events.append({
            "at": observed_at,
            "key": k,
            "first_crossing_capture": first_crossing,
            "qualification": candidate.get("qualification"),
            "listing_matches": len(listings),
            "exact_ca_social_events": sum(1 for x in social if x.get("exact_contract_match")),
            "holder_status": holders.get("status"),
            "whale_status": whales.get("status"),
        })

    state.update({"version": 1, "mode": MODE, "updated_at": observed_at, "tokens": token_state})
    output = {
        "version": 1,
        "mode": MODE,
        "generated_at": observed_at,
        "candidate_count": len(dossiers),
        "whale_definition_supply_pct": WHALE_SUPPLY_PCT,
        "research_only": True,
        "production_impact": "NONE",
        "dossiers": dossiers,
    }
    ledger = {
        "version": 1,
        "mode": "IMMUTABLE_POST_QUALIFICATION_INTELLIGENCE_LEDGER_V1",
        "updated_at": observed_at,
        "events_count": len(ledger_events),
        "events": ledger_events[-10000:],
    }
    _write(STATE, state)
    _write(DOSSIERS, output)
    _write(LEDGER, ledger)
    print("QUALIFIED_INTELLIGENCE", json.dumps({"candidates": len(dossiers), "events": len(ledger_events)}, separators=(",", ":")))
    return output


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
