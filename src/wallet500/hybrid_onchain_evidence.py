from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .revival_1000 import looks_like_solana_address

DATA = Path("data")
SOURCE = DATA / "revival-1000-latest.json"
OUTPUT = DATA / "hybrid-external-evidence.json"
CONTRACT = "HYBRID_EXTERNAL_EVIDENCE_V1"
NETWORK = "solana"
OFFICIAL_RPC = "https://api.mainnet.solana.com"
PUBLICNODE_RPC = "https://solana-rpc.publicnode.com"
DEFAULT_BUDGET = 12

STATUS_VERIFIED = "VERIFIED"
STATUS_RATE_LIMITED = "RATE_LIMITED"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_ERROR = "ERROR"
VALID_SCAN_STATUSES = {
    STATUS_VERIFIED,
    STATUS_RATE_LIMITED,
    STATUS_UNAVAILABLE,
    STATUS_ERROR,
}


class RpcEvidenceError(RuntimeError):
    def __init__(self, status: str, message: str):
        if status not in VALID_SCAN_STATUSES - {STATUS_VERIFIED}:
            status = STATUS_ERROR
        self.status = status
        super().__init__(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _endpoint_label(url: str) -> str:
    """Return a safe provider label without leaking secret paths/query parameters."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or "configured_rpc"
    except Exception:
        return "configured_rpc"


def _classify_exception(exc: BaseException) -> str:
    if isinstance(exc, RpcEvidenceError):
        return exc.status
    if isinstance(exc, HTTPError):
        if exc.code == 429:
            return STATUS_RATE_LIMITED
        if exc.code in {403, 408, 425, 500, 502, 503, 504}:
            return STATUS_UNAVAILABLE
        return STATUS_ERROR
    if isinstance(exc, (URLError, TimeoutError, ConnectionError)):
        return STATUS_UNAVAILABLE
    text = str(exc).lower()
    if any(term in text for term in ("429", "rate limit", "too many requests")):
        return STATUS_RATE_LIMITED
    if any(term in text for term in ("timeout", "timed out", "temporar", "connection", "unavailable", "blocked")):
        return STATUS_UNAVAILABLE
    return STATUS_ERROR


def _retry_delay(exc: BaseException, attempt: int) -> float:
    if isinstance(exc, HTTPError) and exc.code == 429:
        try:
            retry_after = float((exc.headers or {}).get("Retry-After") or 0)
            if retry_after > 0:
                return min(5.0, retry_after)
        except (TypeError, ValueError):
            pass
    return min(4.0, 0.9 * (attempt + 1))


def _rpc(url: str, method: str, params: list, retries: int = 2):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last_exc: BaseException | None = None
    retries = max(1, retries)
    for attempt in range(retries):
        try:
            req = Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "Wallet500-Hybrid/1.1"},
            )
            with urlopen(req, timeout=18) as response:
                payload = json.loads(response.read().decode())
            error = payload.get("error")
            if error:
                code = error.get("code") if isinstance(error, dict) else None
                message = str(error.get("message") if isinstance(error, dict) else error)
                lower = message.lower()
                if "429" in lower or "rate limit" in lower or "too many requests" in lower:
                    raise RpcEvidenceError(STATUS_RATE_LIMITED, f"RPC_{method}_RATE_LIMITED:{code}:{message}")
                if code in {-32004, -32005, -32007, -32009, -32010} or any(
                    term in lower for term in ("node is unhealthy", "unavailable", "temporarily")
                ):
                    raise RpcEvidenceError(STATUS_UNAVAILABLE, f"RPC_{method}_UNAVAILABLE:{code}:{message}")
                raise RpcEvidenceError(STATUS_ERROR, f"RPC_{method}_ERROR:{code}:{message}")
            return payload.get("result")
        except (HTTPError, URLError, TimeoutError, RpcEvidenceError, ValueError) as exc:
            last_exc = exc
            status = _classify_exception(exc)
            if attempt + 1 >= retries or status == STATUS_ERROR:
                raise RpcEvidenceError(
                    status,
                    f"RPC_{method}_FAILED:{type(exc).__name__}:{str(exc)[:180]}",
                ) from exc
            time.sleep(_retry_delay(exc, attempt))
    raise RpcEvidenceError(_classify_exception(last_exc or RuntimeError("UNKNOWN_RPC_FAILURE")), f"RPC_{method}_FAILED")


def _rpc_urls() -> list[str]:
    configured = (os.getenv("SOLANA_RPC_URL") or "").strip()
    candidates = [configured, PUBLICNODE_RPC, OFFICIAL_RPC]
    urls: list[str] = []
    for url in candidates:
        if url and url not in urls:
            urls.append(url)
    return urls


def _raw_amount(row: dict) -> int:
    try:
        return max(0, int(str(row.get("amount") or "0")))
    except (TypeError, ValueError):
        return 0


def concentration_score(top1: float, top10: float) -> tuple[float, float, list[str]]:
    """Return confirmation score, concentration risk, and transparent rules."""
    penalty = 0.0
    signals: list[str] = []
    if top1 >= 20:
        penalty += 35
        signals.append("TOP1_OWNER_GE_20PCT")
    elif top1 >= 10:
        penalty += 18
        signals.append("TOP1_OWNER_GE_10PCT")
    else:
        signals.append("TOP1_OWNER_LT_10PCT")
    if top10 >= 60:
        penalty += 30
        signals.append("TOP10_OWNERS_GE_60PCT")
    elif top10 >= 40:
        penalty += 15
        signals.append("TOP10_OWNERS_GE_40PCT")
    else:
        signals.append("TOP10_OWNERS_LT_40PCT")
    risk = min(100.0, penalty)
    score = max(0.0, 100.0 - risk)
    return round(score, 2), round(risk, 2), signals


def fetch_holder_evidence(token_address: str, rpc_url: str, observed_at: str | None = None) -> dict:
    if not looks_like_solana_address(token_address):
        raise ValueError("INVALID_SOLANA_MINT")
    observed_at = observed_at or now_iso()
    supply = _rpc(rpc_url, "getTokenSupply", [token_address, {"commitment": "confirmed"}]) or {}
    supply_value = supply.get("value") or {}
    total_raw = _raw_amount(supply_value)
    if total_raw <= 0:
        raise RpcEvidenceError(STATUS_ERROR, "TOKEN_SUPPLY_UNAVAILABLE")

    largest = _rpc(rpc_url, "getTokenLargestAccounts", [token_address, {"commitment": "confirmed"}]) or {}
    rows = [x for x in (largest.get("value") or [])[:20] if isinstance(x, dict) and x.get("address")]
    if not rows:
        raise RpcEvidenceError(STATUS_ERROR, "LARGEST_TOKEN_ACCOUNTS_UNAVAILABLE")

    addresses = [str(x["address"]) for x in rows]
    infos = _rpc(
        rpc_url,
        "getMultipleAccounts",
        [addresses, {"encoding": "jsonParsed", "commitment": "confirmed"}],
    ) or {}
    values = infos.get("value") or []
    if len(values) != len(rows):
        raise RpcEvidenceError(STATUS_ERROR, "TOKEN_ACCOUNT_OWNER_RESOLUTION_LENGTH_MISMATCH")

    by_owner: dict[str, int] = defaultdict(int)
    resolved = 0
    for row, info in zip(rows, values):
        owner = None
        try:
            owner = (((((info or {}).get("data") or {}).get("parsed") or {}).get("info") or {}).get("owner"))
        except Exception:
            owner = None
        amount = _raw_amount(row)
        if owner and amount > 0:
            resolved += 1
            by_owner[str(owner)] += amount

    if resolved != len(rows) or not by_owner:
        raise RpcEvidenceError(STATUS_ERROR, f"TOKEN_ACCOUNT_OWNER_RESOLUTION_INCOMPLETE:{resolved}/{len(rows)}")

    owner_amounts = sorted(by_owner.values(), reverse=True)
    pcts = [(amount / total_raw) * 100.0 for amount in owner_amounts]
    top1 = sum(pcts[:1])
    top5 = sum(pcts[:5])
    top10 = sum(pcts[:10])
    top20 = sum(pcts[:20])
    score, risk_score, signals = concentration_score(top1, top10)
    signals = ["EXACT_MINT_OWNER_RESOLUTION_COMPLETE", *signals]

    return {
        "verified": True,
        "contract_match": True,
        "source": "SOLANA_JSON_RPC_LARGEST_ACCOUNTS+OWNER_RESOLUTION",
        "source_rpc_provider": _endpoint_label(rpc_url),
        "observed_at": observed_at,
        "anomaly_score": score,
        "risk_score": risk_score,
        "score_semantics": "HOLDER_DISTRIBUTION_CONFIRMATION_NOT_MOMENTUM",
        "signals": signals,
        "metrics": {
            "top_token_accounts_requested": len(rows),
            "top_token_accounts_owner_resolved": resolved,
            "distinct_top_owners": len(owner_amounts),
            "top1_owner_pct": round(top1, 4),
            "top5_owners_pct": round(top5, 4),
            "top10_owners_pct": round(top10, 4),
            "top20_owners_pct": round(top20, 4),
            "total_supply_raw": str(total_raw),
        },
        "limitations": [
            "top-owner concentration is measured on-chain from the largest token accounts",
            "LP/burn/infrastructure owner labels are not independently verified in this collector",
            "therefore this channel is confirmation/research evidence, not a standalone buy signal",
        ],
    }


def fetch_holder_evidence_with_fallback(
    token_address: str,
    rpc_urls: list[str],
    observed_at: str | None = None,
) -> tuple[dict, list[dict]]:
    failures: list[dict] = []
    for rpc_url in rpc_urls:
        try:
            return fetch_holder_evidence(token_address, rpc_url, observed_at), failures
        except Exception as exc:
            failures.append(
                {
                    "provider": _endpoint_label(rpc_url),
                    "status": _classify_exception(exc),
                    "reason": f"{type(exc).__name__}:{str(exc)}"[:240],
                }
            )
    statuses = {x["status"] for x in failures}
    if statuses and statuses <= {STATUS_RATE_LIMITED}:
        final_status = STATUS_RATE_LIMITED
    elif statuses and statuses <= {STATUS_RATE_LIMITED, STATUS_UNAVAILABLE}:
        final_status = STATUS_UNAVAILABLE
    else:
        final_status = STATUS_ERROR
    raise RpcEvidenceError(final_status, json.dumps(failures, separators=(",", ":"))[:700])


def _latest_by_address(payload: dict) -> dict[str, dict]:
    latest: dict[str, tuple[datetime, dict]] = {}
    for row in payload.get("observations") or []:
        if not isinstance(row, dict):
            continue
        address = str(row.get("token_address") or "")
        try:
            dt = datetime.fromisoformat(str(row.get("observed_at") or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        old = latest.get(address)
        holders = row.get("holders") or {}
        if (
            looks_like_solana_address(address)
            and holders.get("verified") is True
            and holders.get("contract_match") is True
            and (old is None or dt > old[0])
        ):
            latest[address] = (dt, row)
    return {k: v[1] for k, v in latest.items()}


def run() -> dict:
    source = _load(SOURCE, {})
    if (
        source.get("mode") != "RESEARCH_ONLY_REVIVAL_SOLANA_EXPANDED_V6"
        or source.get("network") != NETWORK
        or source.get("production_portfolio_impact") != "NONE"
        or source.get("no_hindsight") is not True
    ):
        raise RuntimeError("HOLDER_EVIDENCE_SOURCE_TRUTH_CONTRACT_REJECTED")
    coins = [
        x
        for x in (source.get("coins") or [])
        if isinstance(x, dict) and looks_like_solana_address(str(x.get("token_address") or ""))
    ]
    if not coins:
        raise RuntimeError("HOLDER_EVIDENCE_EMPTY_SOURCE")

    old = _load(OUTPUT, {})
    old_latest = _latest_by_address(old) if isinstance(old, dict) else {}
    scan = old.get("scan") or {} if isinstance(old, dict) else {}
    cursor = int(scan.get("cursor") or 0) % len(coins)
    budget = max(1, min(30, int(os.getenv("HYBRID_HOLDER_SCAN_BUDGET", str(DEFAULT_BUDGET)))))
    rpc_urls = _rpc_urls()
    selected = [coins[(cursor + i) % len(coins)] for i in range(min(budget, len(coins)))]

    status_counts = {status: 0 for status in VALID_SCAN_STATUSES}
    errors: list[dict] = []
    attempted: list[str] = []
    for coin in selected:
        address = str(coin.get("token_address"))
        attempted.append(address)
        observed_at = now_iso()
        try:
            holders, provider_failures = fetch_holder_evidence_with_fallback(address, rpc_urls, observed_at)
            old_latest[address] = {
                "network": NETWORK,
                "token_address": address,
                "symbol": coin.get("symbol"),
                "name": coin.get("name"),
                "observed_at": observed_at,
                "holders": holders,
            }
            status_counts[STATUS_VERIFIED] += 1
            if provider_failures:
                holders["fallback_provider_failures"] = provider_failures
        except Exception as exc:
            status = _classify_exception(exc)
            status_counts[status] += 1
            errors.append(
                {
                    "token_address": address,
                    "symbol": coin.get("symbol"),
                    "status": status,
                    "error": f"{type(exc).__name__}:{str(exc)}"[:760],
                }
            )
        time.sleep(0.2)

    next_cursor = (cursor + len(selected)) % len(coins)
    observations = sorted(old_latest.values(), key=lambda x: str(x.get("token_address") or ""))
    failed = len(selected) - status_counts[STATUS_VERIFIED]
    payload = {
        "version": 1,
        "contract": CONTRACT,
        "network": NETWORK,
        "updated_at": now_iso(),
        "source_generated_at": source.get("generated_at"),
        "production_portfolio_impact": "NONE",
        "truth_rules": [
            "holder evidence is queried by exact Solana mint",
            "a holder row is published only when all returned top token-account owners resolve",
            "failed scans are classified as RATE_LIMITED, UNAVAILABLE, or ERROR; no zero score is fabricated",
            "prior verified evidence is preserved when a later RPC scan fails",
            "holder distribution is confirmation/research evidence and never a standalone momentum claim",
        ],
        "scan": {
            "cursor": next_cursor,
            "universe_size": len(coins),
            "budget": budget,
            "attempted": len(selected),
            "verified": status_counts[STATUS_VERIFIED],
            "failed": failed,
            "status_counts": status_counts,
            "rpc_providers": [_endpoint_label(url) for url in rpc_urls],
            "attempted_token_addresses": attempted,
            "errors": errors[:30],
        },
        "observations": observations,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        "HYBRID_HOLDER_EVIDENCE_OK",
        {
            "attempted": len(selected),
            "status_counts": status_counts,
            "stored": len(observations),
            "next_cursor": next_cursor,
        },
    )
    return payload


if __name__ == "__main__":
    run()