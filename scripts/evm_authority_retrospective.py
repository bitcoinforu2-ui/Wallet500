from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from wallet500.evm_contract_authority_guard import evaluate_security

ROOT = Path(__file__).resolve().parents[1]
REJECTED = ROOT / "data/rejected-candidates.json"
OUT = ROOT / "data/evm-authority-retrospective.json"
UA = "Wallet500-EVMAuthorityRetrospective/1.0"
CHAIN_IDS = {
    "ethereum": 1,
    "bsc": 56,
    "base": 8453,
    "arbitrum": 42161,
    "optimism": 10,
    "polygon": 137,
    "avalanche": 43114,
}
DEX_CHAIN = dict((k, k) for k in CHAIN_IDS)
BATCH = 30


def _json(url: str, headers=None, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _dt(value):
    try:
        raw = str(value or "").replace("Z", "+00:00")
        d = datetime.fromisoformat(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def _age_at_reject_minutes(row):
    created = row.get("pair_created_at")
    evaluated = _dt(row.get("evaluated_at") or row.get("observed_at"))
    try:
        created_ms = float(created)
    except (TypeError, ValueError):
        return None
    if not evaluated or created_ms <= 0:
        return None
    created_dt = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc)
    return max(0.0, (evaluated - created_dt).total_seconds() / 60.0)


def _goplus(rows):
    grouped = {}
    for row in rows:
        chain = str(row.get("chain") or "").lower()
        token = str(row.get("token") or "").lower()
        if chain in CHAIN_IDS and token:
            grouped.setdefault(chain, [])
            if token not in grouped[chain]:
                grouped[chain].append(token)

    token = os.getenv("GOPLUS_ACCESS_TOKEN", "").strip()
    headers = {"Authorization": "Bearer " + token} if token else {}
    out = {}
    for chain, addresses in grouped.items():
        chain_id = CHAIN_IDS[chain]
        for i in range(0, len(addresses), BATCH):
            chunk = addresses[i:i + BATCH]
            q = urllib.parse.quote(",".join(chunk), safe=",")
            payload = _json(
                f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={q}",
                headers=headers,
            )
            result = (payload or {}).get("result") if isinstance(payload, dict) else None
            if isinstance(result, dict):
                low = {str(k).lower(): v for k, v in result.items() if isinstance(v, dict)}
                for address in chunk:
                    if address in low:
                        out[(chain, address)] = low[address]
            time.sleep(0.15)
    return out


def _market(row):
    chain = str(row.get("chain") or "").lower()
    pair = str(row.get("pair_address") or "").strip()
    token = str(row.get("token") or "").lower()
    if chain not in DEX_CHAIN or not pair:
        return {}
    payload = _json(f"https://api.dexscreener.com/latest/dex/pairs/{DEX_CHAIN[chain]}/{pair}") or {}
    pairs = payload.get("pairs") if isinstance(payload, dict) else []
    exact = next(
        (
            p for p in (pairs or [])
            if str(p.get("pairAddress") or "").lower() == pair.lower()
            and str(((p.get("baseToken") or {}).get("address") or "")).lower() == token
        ),
        None,
    )
    if exact is None:
        exact = next(
            (
                p for p in (pairs or [])
                if str(p.get("pairAddress") or "").lower() == pair.lower()
                and token in {
                    str(((p.get("baseToken") or {}).get("address") or "")).lower(),
                    str(((p.get("quoteToken") or {}).get("address") or "")).lower(),
                }
            ),
            None,
        )
    if not exact:
        return {}
    try:
        price = float(exact.get("priceUsd") or 0)
    except (TypeError, ValueError):
        price = 0.0
    try:
        liquidity = float(((exact.get("liquidity") or {}).get("usd")) or 0)
    except (TypeError, ValueError):
        liquidity = 0.0
    return {"current_price_usd": price, "current_liquidity_usd": liquidity}


def run(max_cases: int | None = None):
    max_cases = max_cases or int(os.getenv("EVM_AUTHORITY_RETROSPECTIVE_MAX", "60"))
    raw = json.loads(REJECTED.read_text(encoding="utf-8")) if REJECTED.exists() else []
    rows = []
    seen = set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        chain = str(row.get("chain") or "").lower()
        token = str(row.get("token") or "").lower()
        pair = str(row.get("pair_address") or "").lower()
        if chain not in CHAIN_IDS or not token or not pair:
            continue
        age = _age_at_reject_minutes(row)
        if age is None or age > 7 * 24 * 60:
            continue
        key = (chain, token, pair)
        if key in seen:
            continue
        seen.add(key)
        rows.append({**row, "_age_at_reject_minutes": age})

    rows.sort(key=lambda x: str(x.get("evaluated_at") or x.get("observed_at") or ""), reverse=True)
    rows = rows[:max_cases]
    security = _goplus(rows)
    findings = []

    for row in rows:
        chain = str(row.get("chain") or "").lower()
        token = str(row.get("token") or "").lower()
        sec = security.get((chain, token))
        market = _market(row)
        if not sec or not market.get("current_price_usd"):
            continue
        age = float(row["_age_at_reject_minutes"])
        assessment = evaluate_security(sec, age_minutes=age)
        try:
            t0_price = float(row.get("price_usd") or 0)
        except (TypeError, ValueError):
            t0_price = 0.0
        current_price = float(market["current_price_usd"])
        change = ((current_price / t0_price) - 1.0) * 100.0 if t0_price > 0 else None
        collapsed80 = bool(change is not None and change <= -80.0)
        collapsed50 = bool(change is not None and change <= -50.0)
        findings.append({
            "chain": chain,
            "token": token,
            "pair_address": row.get("pair_address"),
            "symbol": row.get("base_token_symbol"),
            "evaluated_at": row.get("evaluated_at"),
            "age_at_reject_minutes": round(age, 2),
            "t0_price_usd": t0_price or None,
            "current_price_usd": current_price,
            "current_liquidity_usd": market.get("current_liquidity_usd"),
            "current_change_from_reject_pct": round(change, 2) if change is not None else None,
            "current_collapse_ge50pct": collapsed50,
            "current_collapse_ge80pct": collapsed80,
            "authority_risk_score_using_t0_age": assessment["risk_score"],
            "authority_risk_tier_using_t0_age": assessment["risk_tier"],
            "authority_buy_eligible_using_current_security_state": assessment["buy_eligible"],
            "authority_risk_reasons": assessment["risk_reasons"],
            "dangerous_combinations": assessment["dangerous_combinations"],
            "direct_critical_capabilities": assessment["direct_critical_capabilities"],
            "current_security_flags": assessment["flags"],
        })
        time.sleep(0.10)

    collapsed = [x for x in findings if x["current_collapse_ge80pct"]]
    withheld = [x for x in findings if not x["authority_buy_eligible_using_current_security_state"]]
    overlap = [
        x for x in collapsed
        if not x["authority_buy_eligible_using_current_security_state"]
    ]
    report = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "POST_EVENT_FORENSIC_ONLY_NOT_T0_PROOF",
        "input": "data/rejected-candidates.json",
        "max_cases": max_cases,
        "eligible_young_evm_cases": len(rows),
        "cases_with_current_market_and_security": len(findings),
        "current_collapse_ge80pct": len(collapsed),
        "authority_would_withhold_buy_using_current_security_state_and_t0_age": len(withheld),
        "collapsed_with_authority_warning_overlap": len(overlap),
        "collapsed_overlap_pct": round(len(overlap) / len(collapsed) * 100.0, 2) if collapsed else None,
        "limitations": [
            "GoPlus security is queried now, not reconstructed at the original decision timestamp.",
            "Contract-code capabilities can persist, but owner/role state may have changed after T0.",
            "Current price is not the historical trough; this study measures present collapse only.",
            "Results are forensic evidence for rule design, never proof that a specific flag existed at T0.",
        ],
        "production_effect": False,
        "findings": findings,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "eligible_young_evm_cases",
        "cases_with_current_market_and_security",
        "current_collapse_ge80pct",
        "authority_would_withhold_buy_using_current_security_state_and_t0_age",
        "collapsed_with_authority_warning_overlap",
        "collapsed_overlap_pct",
    )}, indent=2))
    return report


if __name__ == "__main__":
    run()
