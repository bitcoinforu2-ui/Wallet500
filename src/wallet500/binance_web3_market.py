"""Binance Web3 read-only verifier for Wallet500 market cross-checking.

The Binance feed is token-level evidence. It is never treated as an exact-pair
quote and never grants production promotion by itself. Data is normalized into
the provider-neutral ``market-source-snapshots.json`` contract consumed by
``wallet500.market_cross_check``.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
CORRELATION = DATA / "cross-source-correlation.json"
SNAPSHOTS = DATA / "market-source-snapshots.json"
STATUS = DATA / "binance-web3-market-status.json"

DYNAMIC_URL = (
    "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/"
    "buw/wallet/market/token/dynamic/info/ai"
)
AUDIT_URL = (
    "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/"
    "security/token/audit"
)
CHAIN_IDS = {
    "ethereum": "1",
    "bsc": "56",
    "base": "8453",
    "solana": "CT_501",
}
CHAIN_ALIASES = {
    "eth": "ethereum",
    "ethereum-mainnet": "ethereum",
    "bnb": "bsc",
    "bnb-chain": "bsc",
    "binance-smart-chain": "bsc",
    "sol": "solana",
}
SOURCE = "binance_web3"
USER_AGENT = "wallet500-market-cross-check/1.0"
TIMEOUT_SECONDS = 10
DEFAULT_MAX_ASSETS = 100
DEFAULT_REQUEST_DELAY_SECONDS = 0.08


class ProviderError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_chain(value: object) -> str:
    chain = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(chain, chain)


def _num(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
        return out if out >= 0 else None
    except (TypeError, ValueError):
        return None


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None and mapping[key] != "":
            return mapping[key]
    return None


def _request_json(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    raw_body = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=raw_body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "identity")
    req.add_header("User-Agent", USER_AGENT)
    if raw_body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderError(f"Binance Web3 request failed: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ProviderError("Binance Web3 returned a non-object payload")
    code = payload.get("code")
    if code not in (None, "000000", 0, "0"):
        raise ProviderError(f"Binance Web3 business error: {code}")
    return payload


def fetch_dynamic(chain: str, token: str, *, observed_at: str | None = None) -> dict[str, Any]:
    """Fetch and normalize current token-level market metrics."""
    chain = _norm_chain(chain)
    chain_id = CHAIN_IDS.get(chain)
    if not chain_id:
        raise ProviderError(f"unsupported Binance Web3 chain: {chain}")
    payload = _request_json(
        DYNAMIC_URL,
        params={"chainId": chain_id, "contractAddress": token},
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ProviderError("Binance Web3 dynamic response has no data object")

    return {
        "chain": chain,
        "token": token,
        "source": SOURCE,
        "role": "verifier",
        "observed_at": observed_at or _now(),
        # Binance token-info is token-level/aggregate evidence, not an exact-pair quote.
        "market_scope": "token_aggregate",
        "price_usd": _num(_first(data, "price", "priceUsd", "priceUSD")),
        "market_cap_usd": _num(_first(data, "marketCap", "market_cap", "marketCapUsd")),
        "liquidity_usd": _num(_first(data, "liquidity", "liquidityUsd", "liquidityUSD")),
        "volume_24h_usd": _num(_first(data, "volume24h", "volume24H", "volume_24h")),
        "holders": _num(_first(data, "holders", "holderCount", "totalHolders")),
        # Some Binance surfaces expose this field even when the dynamic API does not.
        # We consume it only when actually present; absence never becomes zero.
        "top10_pct": _num(_first(
            data,
            "top10HoldersPercentage",
            "top10_holders_percentage",
            "top10HolderPercentage",
        )),
        "provider_chain_id": chain_id,
        "provider_retrieved_at": observed_at or _now(),
    }


def fetch_audit(chain: str, token: str) -> dict[str, Any]:
    """Fetch point-in-time security audit; unavailable/unsupported is fail-closed."""
    chain = _norm_chain(chain)
    chain_id = CHAIN_IDS.get(chain)
    if not chain_id:
        raise ProviderError(f"unsupported Binance Web3 chain: {chain}")
    payload = _request_json(
        AUDIT_URL,
        method="POST",
        body={
            "binanceChainId": chain_id,
            "contractAddress": token,
            "requestId": str(uuid.uuid4()),
        },
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload
    has_result = data.get("hasResult") is True
    supported = data.get("isSupported") is True
    if not (has_result and supported):
        return {
            "available": False,
            "risk_level": None,
            "risk_level_enum": None,
            "risk_flags": [],
        }

    flags: list[str] = []
    for item in data.get("riskItems") or []:
        if not isinstance(item, dict):
            continue
        for detail in item.get("details") or []:
            if not isinstance(detail, dict) or detail.get("isHit") is not True:
                continue
            title = str(detail.get("title") or item.get("id") or "risk").strip()
            risk_type = str(detail.get("riskType") or "RISK").strip().upper()
            flags.append(f"BINANCE_AUDIT_{risk_type}:{title}")

    extra = data.get("extraInfo") if isinstance(data.get("extraInfo"), dict) else {}
    return {
        "available": True,
        "risk_level": data.get("riskLevel"),
        "risk_level_enum": data.get("riskLevelEnum"),
        "buy_tax": _num(extra.get("buyTax")),
        "sell_tax": _num(extra.get("sellTax")),
        "is_verified": extra.get("isVerified"),
        "risk_flags": sorted(set(flags)),
    }


def _eligible_assets(payload: dict[str, Any], max_assets: int) -> list[dict[str, str]]:
    assets = payload.get("assets") if isinstance(payload, dict) else {}
    if not isinstance(assets, dict):
        return []
    rows: list[dict[str, Any]] = []
    for asset in assets.values():
        if not isinstance(asset, dict):
            continue
        chain = _norm_chain(asset.get("chain"))
        token = str(asset.get("token") or "").strip()
        if chain not in CHAIN_IDS or not token:
            continue
        if asset.get("identity_confidence") not in (None, "EXACT_CHAIN_CONTRACT"):
            continue
        rows.append({
            "chain": chain,
            "token": token,
            "source_count": int(asset.get("source_confirmation_count") or 0),
            "last_seen": str(asset.get("last_seen_any_source_at") or ""),
        })
    rows.sort(key=lambda r: (r["source_count"], r["last_seen"]), reverse=True)
    return [{"chain": str(r["chain"]), "token": str(r["token"])} for r in rows[:max_assets]]


def _existing_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("snapshots") or payload.get("records") or []
    else:
        rows = payload
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def refresh(
    *,
    correlation: dict[str, Any] | None = None,
    existing: Any = None,
    max_assets: int = DEFAULT_MAX_ASSETS,
    with_audit: bool = False,
    request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    correlation = correlation if correlation is not None else _load(CORRELATION, {})
    existing = existing if existing is not None else _load(SNAPSHOTS, {})
    selected = _eligible_assets(correlation, max_assets)
    rows = _existing_rows(existing)

    # Keep every non-Binance provider. Old Binance observations are retained on
    # request failure so freshness logic, rather than silent deletion, marks them stale.
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            _norm_chain(row.get("chain") or row.get("network")),
            str(row.get("token") or row.get("contract") or row.get("mint") or "").strip(),
            str(row.get("source") or row.get("provider") or "").strip().lower(),
        )
        if all(key):
            by_key[key] = row

    ok = 0
    failures: list[dict[str, str]] = []
    audits: dict[str, Any] = {}
    started_at = _now()
    for i, asset in enumerate(selected):
        chain, token = asset["chain"], asset["token"]
        observed_at = _now()
        try:
            row = fetch_dynamic(chain, token, observed_at=observed_at)
            if with_audit:
                audit = fetch_audit(chain, token)
                row["risk_flags"] = audit.get("risk_flags") or []
                audits[f"{chain}:{token}"] = audit
            by_key[(chain, token, SOURCE)] = row
            ok += 1
        except ProviderError as exc:
            failures.append({"asset_key": f"{chain}:{token}", "error": str(exc)[:240]})
        if request_delay_seconds > 0 and i + 1 < len(selected):
            time.sleep(request_delay_seconds)

    payload = {
        "version": 1,
        "updated_at": _now(),
        "snapshots": sorted(
            by_key.values(),
            key=lambda r: (
                str(r.get("chain") or r.get("network") or ""),
                str(r.get("token") or r.get("contract") or r.get("mint") or ""),
                str(r.get("source") or r.get("provider") or ""),
            ),
        ),
    }
    status = {
        "version": 1,
        "source": SOURCE,
        "started_at": started_at,
        "completed_at": _now(),
        "mode": "READ_ONLY_TOKEN_LEVEL_VERIFIER",
        "automatic_trade": False,
        "selected_assets": len(selected),
        "successful_assets": ok,
        "failed_assets": len(failures),
        "failures": failures,
        "audit_enabled": with_audit,
        "audits": audits,
        "truth_boundary": (
            "Binance Web3 is token-level verifier evidence only; it does not grant exact-pair "
            "confirmation or bypass Wallet500 promotion/risk/execution gates."
        ),
    }
    return payload, status


def run() -> tuple[dict[str, Any], dict[str, Any]]:
    max_assets = max(1, int(os.environ.get("W500_MARKET_MAX_ASSETS", DEFAULT_MAX_ASSETS)))
    with_audit = os.environ.get("W500_BINANCE_AUDIT", "0").strip().lower() in {"1", "true", "yes", "on"}
    delay = max(0.0, float(os.environ.get("W500_BINANCE_REQUEST_DELAY_SECONDS", DEFAULT_REQUEST_DELAY_SECONDS)))
    payload, status = refresh(max_assets=max_assets, with_audit=with_audit, request_delay_seconds=delay)
    _write(SNAPSHOTS, payload)
    _write(STATUS, status)
    print(
        "BINANCE_WEB3_MARKET",
        json.dumps(
            {
                "selected": status["selected_assets"],
                "ok": status["successful_assets"],
                "failed": status["failed_assets"],
                "audit": status["audit_enabled"],
            },
            separators=(",", ":"),
        ),
    )
    return payload, status


if __name__ == "__main__":
    run()
