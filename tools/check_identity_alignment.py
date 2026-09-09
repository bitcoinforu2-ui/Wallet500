#!/usr/bin/env python3
"""Fail-closed row-level identity and policy audit for engine -> dashboard data."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXPECTED_MIN_AGE_DAYS = 180
EXPECTED_MIN_EXECUTION_LIQUIDITY_USD = 50_000.0


def load(name: str, default):
    p = DATA / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm_chain(v: object) -> str:
    return str(v or "").strip().lower()


def norm_token(chain: str, token: object) -> str:
    t = str(token or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast"}:
        return t.lower()
    return t


def url_pair(url: object) -> str | None:
    s = str(url or "").strip().rstrip("/")
    if not s:
        return None
    m = re.search(r"/(?:solana|ethereum|bsc|base|arbitrum|optimism|polygon|avalanche|fantom|linea|zksync|mantle|scroll|blast)/(?:pools/)?([^/?#]+)(?:[/?#].*)?$", s, re.I)
    return m.group(1) if m else None


def rows(payload: object, *keys: str) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def main() -> int:
    findings: list[dict] = []

    def add(code: str, message: str, **details):
        findings.append({"code": code, "message": message, **details})

    real = load("real-alerts.json", {})
    contract = real.get("truth_contract") if isinstance(real, dict) else {}
    if int(contract.get("minimum_market_age_days") or 0) != EXPECTED_MIN_AGE_DAYS:
        add("POLICY_AGE_SPLIT", "Canonical real-alert feed is not on the 180-day policy", observed=contract.get("minimum_market_age_days"), expected=EXPECTED_MIN_AGE_DAYS)
    if float(contract.get("minimum_execution_pool_liquidity_usd") or 0) != EXPECTED_MIN_EXECUTION_LIQUIDITY_USD:
        add("POLICY_LIQUIDITY_SPLIT", "Canonical real-alert feed is not on the $50K execution-liquidity policy", observed=contract.get("minimum_execution_pool_liquidity_usd"), expected=EXPECTED_MIN_EXECUTION_LIQUIDITY_USD)

    market_sources = {
        "real_alerts": rows(real, "alerts"),
        "real_watch": rows(real, "verified_watch"),
        "cex": rows(load("cex-revival-radar.json", {}), "alerts"),
        "envelope": rows(load("candidate-evidence-envelope.json", {}), "candidates"),
        "fusion": rows(load("cross-signal-fusion-v2.json", {}), "tokens"),
        "catalyst": rows(load("catalyst-wire-live.json", {}), "events", "items", "catalysts"),
    }

    identity_seen: dict[tuple[str, str], set[str]] = {}
    for source, source_rows in market_sources.items():
        for i, row in enumerate(source_rows):
            chain = norm_chain(row.get("chain") or row.get("network"))
            token = norm_token(chain, row.get("token_address") or row.get("token") or row.get("mint"))
            pair = str(row.get("pair_address") or row.get("dex_pair_address") or row.get("exact_pair") or "").strip()
            dex_url = row.get("dex_url") or row.get("url")
            upair = url_pair(dex_url)
            if pair and upair and pair.lower() != upair.lower():
                add("PAIR_URL_MISMATCH", "Displayed DEX URL points to a different pair/pool", source=source, row=i, chain=chain, token=token, pair=pair, url_pair=upair, dex_url=dex_url)
            if chain and token and pair:
                identity_seen.setdefault((chain, token), set()).add(pair.lower())
            if source in {"real_alerts", "real_watch"}:
                if not chain or not token or not pair:
                    add("CANONICAL_IDENTITY_INCOMPLETE", "Canonical dashboard row lacks chain/token/exact-pair identity", source=source, row=i, chain=chain, token=token, pair=pair)
                if row.get("pair_metadata_atomic") is not True:
                    add("PAIR_ATOMICITY_MARKER_MISSING", "Canonical row was not produced under pair-atomic metadata contract", source=source, row=i, chain=chain, token=token, pair=pair)
                if source == "real_alerts" and row.get("exact_pair_verified") is not True:
                    add("REAL_ALERT_PAIR_NOT_VERIFIED", "Real alert lacks exact-pair verification", row=i, chain=chain, token=token, pair=pair)

    fusion = load("cross-signal-fusion-v2.json", {})
    for i, row in enumerate(rows(fusion, "tokens")):
        if not norm_chain(row.get("chain")):
            add("FUSION_CHAIN_MISSING", "Fusion row has token data but no chain, allowing cross-chain contamination", row=i, token=row.get("token_address"))
    fc = fusion.get("truth_contract") if isinstance(fusion, dict) else {}
    if fusion and fc.get("token_only_cross_chain_join_forbidden") is not True:
        add("FUSION_TOKEN_ONLY_JOIN_GUARD_MISSING", "Fusion output does not assert chain+token identity joins")

    status_html = (ROOT / "index.html").read_text(encoding="utf-8")
    if "[x.token_address,x]" in status_html or "fm[a.token_address]" in status_html or "sm[a.token_address]" in status_html:
        add("STATUS_DASH_TOKEN_ONLY_JOIN", "Status dashboard still joins cross-source rows by token only instead of chain+token")

    out = {
        "version": "IDENTITY_ALIGNMENT_AUDIT_V1",
        "expected_policy": {"minimum_market_age_days": EXPECTED_MIN_AGE_DAYS, "minimum_execution_pool_liquidity_usd": EXPECTED_MIN_EXECUTION_LIQUIDITY_USD},
        "critical_count": len(findings),
        "findings": findings,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
