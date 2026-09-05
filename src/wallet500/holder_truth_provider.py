from __future__ import annotations

import base64
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .cmc_holder_truth import SOURCE as CMC_PROVIDER, fetch_holder_truth as fetch_cmc_holder_truth
from .solscan_holder_truth import SOURCE as SOLSCAN_PROVIDER, fetch_holder_truth as fetch_solscan_holder_truth

SOURCE = "VERIFIED_DUAL_HOLDER_INTELLIGENCE_V1"
RPC_PROVIDER = "SOLANA_RPC_UNIQUE_POSITIVE_OWNER_COUNT"
DUAL_PROVIDER_TOLERANCE_PCT = 20.0
LEGACY_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SUPPORTED_PROGRAMS = {LEGACY_TOKEN_PROGRAM, TOKEN_2022_PROGRAM}
DEFAULT_RPC_URLS = (
    "https://solana-rpc.publicnode.com",
    "https://api.mainnet.solana.com",
)

# Exposed for the tracker wrapper so the persisted research record can preserve
# CMC wallet/tag intelligence without changing the battle-tested rotation engine.
LAST_RESULTS: dict[str, dict] = {}


def _safe_error(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code:
        return f"HTTP_{code}"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _rpc(url: str, method: str, params: list, timeout: int = 25):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Wallet500-HolderTruth/4.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("RPC_INVALID_RESPONSE")
    if payload.get("error"):
        err = payload.get("error") or {}
        raise RuntimeError(f"RPC_ERROR_{err.get('code')}:{str(err.get('message') or '')[:100]}")
    return payload.get("result")


def _rpc_urls() -> list[str]:
    candidates = []
    for env_name in ("SOLANA_HOLDER_RPC_URL", "SOLANA_RPC_URL"):
        value = str(os.getenv(env_name) or "").strip()
        if value:
            candidates.append(value)
    candidates.extend(DEFAULT_RPC_URLS)
    out = []
    seen = set()
    for url in candidates:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _endpoint_label(url: str) -> str:
    try:
        return urlparse(url).netloc or "rpc"
    except Exception:
        return "rpc"


def parse_program_accounts(result) -> dict:
    if not isinstance(result, list):
        return {"verified": False, "status": "RPC_ACCOUNTS_INVALID"}
    owners: set[bytes] = set()
    positive_accounts = 0
    malformed = 0
    for row in result:
        try:
            account = (row or {}).get("account") or {}
            data = account.get("data")
            encoded = data[0] if isinstance(data, list) and data else data
            raw = base64.b64decode(str(encoded), validate=True)
            if len(raw) < 40:
                malformed += 1
                continue
            owner = raw[:32]
            amount = int.from_bytes(raw[32:40], "little", signed=False)
            if amount <= 0:
                continue
            positive_accounts += 1
            owners.add(owner)
        except Exception:
            malformed += 1
    if result and malformed == len(result):
        return {"verified": False, "status": "RPC_ACCOUNT_LAYOUT_UNUSABLE"}
    return {
        "verified": True,
        "status": "OK",
        "holder_count": len(owners),
        "positive_token_accounts": positive_accounts,
        "sample_owner_rows": positive_accounts,
        "sample_unique_owners": len(owners),
        "malformed_rows": malformed,
        "semantics": "Unique owners of positive-balance exact-mint token accounts from the mint-owning SPL Token program",
    }


def fetch_rpc_holder_truth(address: str, timeout: int = 25) -> dict:
    attempts = []
    for url in _rpc_urls():
        label = _endpoint_label(url)
        try:
            mint_info = _rpc(url, "getAccountInfo", [address, {"encoding": "base64", "commitment": "confirmed", "dataSlice": {"offset": 0, "length": 0}}], timeout=timeout)
            value = (mint_info or {}).get("value") if isinstance(mint_info, dict) else None
            program = str((value or {}).get("owner") or "")
            if not value:
                attempts.append({"endpoint": label, "status": "MINT_NOT_FOUND"})
                continue
            if program not in SUPPORTED_PROGRAMS:
                attempts.append({"endpoint": label, "status": "UNSUPPORTED_MINT_PROGRAM", "program": program})
                continue
            filters = [{"memcmp": {"offset": 0, "bytes": address}}]
            if program == LEGACY_TOKEN_PROGRAM:
                filters.insert(0, {"dataSize": 165})
            params = [
                program,
                {
                    "encoding": "base64",
                    "commitment": "confirmed",
                    "filters": filters,
                    "dataSlice": {"offset": 32, "length": 40},
                },
            ]
            result = _rpc(url, "getProgramAccounts", params, timeout=timeout)
            parsed = parse_program_accounts(result)
            if parsed.get("verified") is True:
                parsed.update({
                    "source": SOURCE,
                    "provider_actual": RPC_PROVIDER,
                    "rpc_endpoint": label,
                    "mint_program": program,
                    "attempts": attempts,
                })
                return parsed
            attempts.append({"endpoint": label, "status": parsed.get("status")})
        except Exception as exc:
            attempts.append({"endpoint": label, "status": _safe_error(exc)})
    return {
        "verified": False,
        "status": "PUBLIC_RPC_HOLDER_TRUTH_UNAVAILABLE",
        "source": SOURCE,
        "provider_actual": RPC_PROVIDER,
        "attempts": attempts,
    }


def _relative_difference_pct(a: int, b: int) -> float:
    denom = max(abs(int(a)), abs(int(b)), 1)
    return abs(int(a) - int(b)) / denom * 100.0


def reconcile_provider_results(cmc: dict, solscan: dict, *, tolerance_pct: float = DUAL_PROVIDER_TOLERANCE_PCT) -> dict:
    valid = []
    for name, result in ((CMC_PROVIDER, cmc), (SOLSCAN_PROVIDER, solscan)):
        if result.get("verified") is True:
            try:
                count = int(result.get("holder_count"))
            except (TypeError, ValueError):
                continue
            if count >= 0:
                valid.append((name, count, result))

    provider_counts = {name: count for name, count, _ in valid}
    if len(valid) == 2:
        a_name, a_count, _ = valid[0]
        b_name, b_count, _ = valid[1]
        diff = _relative_difference_pct(a_count, b_count)
        if diff > tolerance_pct:
            return {
                "verified": False,
                "status": "HOLDER_PROVIDER_DISAGREEMENT",
                "source": SOURCE,
                "provider_actual": "CMC_SOLSCAN_DISAGREEMENT",
                "provider_counts": provider_counts,
                "provider_difference_pct": round(diff, 4),
                "cross_validation_status": "DISAGREE_ABOVE_TOLERANCE",
            }
        # Symmetric and conservative: neither peer is privileged. The lower count
        # is used as the forward truth value while both raw counts remain recorded.
        return {
            "verified": True,
            "status": "OK",
            "source": SOURCE,
            "holder_count": min(a_count, b_count),
            "provider_actual": "CMC_SOLSCAN_EQUAL_PEER_CONSENSUS",
            "provider_counts": provider_counts,
            "provider_difference_pct": round(diff, 4),
            "cross_validation_status": "AGREE_WITHIN_TOLERANCE",
            "sample_owner_rows": cmc.get("wallet_sample_count") or solscan.get("sample_owner_rows"),
            "sample_unique_owners": cmc.get("wallet_sample_count") or solscan.get("sample_unique_owners"),
        }

    if len(valid) == 1:
        name, count, result = valid[0]
        return {
            "verified": True,
            "status": "OK",
            "source": SOURCE,
            "holder_count": count,
            "provider_actual": name,
            "provider_counts": provider_counts,
            "provider_difference_pct": None,
            "cross_validation_status": "SINGLE_EQUAL_PEER_AVAILABLE",
            "sample_owner_rows": result.get("wallet_sample_count") or result.get("sample_owner_rows"),
            "sample_unique_owners": result.get("wallet_sample_count") or result.get("sample_unique_owners"),
        }

    return {
        "verified": False,
        "status": "NO_TRUSTED_PRIMARY_HOLDER_PROVIDER",
        "source": SOURCE,
        "provider_actual": None,
        "provider_counts": {},
        "provider_difference_pct": None,
        "cross_validation_status": "NO_PRIMARY_PROVIDER_AVAILABLE",
    }


def fetch_holder_truth(address: str, api_key: str | None, timeout: int = 25) -> dict:
    attempts = []

    cmc = fetch_cmc_holder_truth(address, timeout=min(timeout, 20))
    attempts.append({"provider": CMC_PROVIDER, "status": cmc.get("status")})

    if api_key:
        solscan = fetch_solscan_holder_truth(address, api_key, timeout=min(timeout, 20))
    else:
        solscan = {"verified": False, "status": "SOLSCAN_API_KEY_MISSING", "source": SOLSCAN_PROVIDER}
    attempts.append({"provider": SOLSCAN_PROVIDER, "status": solscan.get("status")})

    combined = reconcile_provider_results(cmc, solscan)
    combined["attempts"] = attempts
    combined["cmc_wallet_intelligence"] = {
        "status": cmc.get("wallet_intelligence_status"),
        "wallet_list_verified": cmc.get("wallet_list_verified") is True,
        "wallet_sample_count": cmc.get("wallet_sample_count", 0),
        "tag_counts": dict(cmc.get("tag_counts") or {}),
        "wallets": list(cmc.get("wallets") or []),
        "auth_mode": cmc.get("auth_mode"),
    }

    if combined.get("verified") is True:
        LAST_RESULTS[address] = dict(combined)
        return combined

    # If the two equal primary peers disagree or are both unavailable, use the
    # exact-mint public RPC only as an adjudicator/fallback, never as a silent override.
    rpc = fetch_rpc_holder_truth(address, timeout=timeout)
    attempts.extend(list(rpc.get("attempts") or []))
    combined["attempts"] = attempts
    if rpc.get("verified") is True:
        rpc_count = int(rpc.get("holder_count") or 0)
        counts = dict(combined.get("provider_counts") or {})
        matching = []
        for name, count in counts.items():
            diff = _relative_difference_pct(int(count), rpc_count)
            if diff <= DUAL_PROVIDER_TOLERANCE_PCT:
                matching.append((name, int(count), diff))
        if matching:
            matching.sort(key=lambda x: x[2])
            name, peer_count, diff = matching[0]
            out = {
                "verified": True,
                "status": "OK",
                "source": SOURCE,
                "holder_count": min(peer_count, rpc_count),
                "provider_actual": f"{name}+{RPC_PROVIDER}_ADJUDICATED",
                "provider_counts": {**counts, RPC_PROVIDER: rpc_count},
                "provider_difference_pct": round(diff, 4),
                "cross_validation_status": "PRIMARY_PEER_CONFIRMED_BY_RPC",
                "sample_owner_rows": rpc.get("sample_owner_rows"),
                "sample_unique_owners": rpc.get("sample_unique_owners"),
                "attempts": attempts,
                "cmc_wallet_intelligence": combined["cmc_wallet_intelligence"],
            }
            LAST_RESULTS[address] = dict(out)
            return out
        if not counts:
            out = dict(rpc)
            out.update({
                "source": SOURCE,
                "provider_counts": {RPC_PROVIDER: rpc_count},
                "provider_difference_pct": None,
                "cross_validation_status": "RPC_ONLY_LAST_RESORT",
                "attempts": attempts,
                "cmc_wallet_intelligence": combined["cmc_wallet_intelligence"],
            })
            LAST_RESULTS[address] = dict(out)
            return out

    combined["status"] = "NO_CONSENSUS_TRUSTED_HOLDER_PROVIDER"
    LAST_RESULTS[address] = dict(combined)
    return combined
