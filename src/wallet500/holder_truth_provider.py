from __future__ import annotations

import base64
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .solscan_holder_truth import fetch_holder_truth as fetch_solscan_holder_truth

SOURCE = "VERIFIED_UNIQUE_POSITIVE_OWNER_COUNT"
SOLSCAN_PROVIDER = "SOLSCAN_V2_TOKEN_HOLDERS_TOTAL"
RPC_PROVIDER = "SOLANA_RPC_UNIQUE_POSITIVE_OWNER_COUNT"
LEGACY_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SUPPORTED_PROGRAMS = {LEGACY_TOKEN_PROGRAM, TOKEN_2022_PROGRAM}
DEFAULT_RPC_URLS = (
    "https://solana-rpc.publicnode.com",
    "https://api.mainnet.solana.com",
)


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
            "User-Agent": "Wallet500-HolderTruth/3.0",
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


def fetch_holder_truth(address: str, api_key: str | None, timeout: int = 25) -> dict:
    attempts = []
    if api_key:
        solscan = fetch_solscan_holder_truth(address, api_key, timeout=min(timeout, 20))
        attempts.append({"provider": SOLSCAN_PROVIDER, "status": solscan.get("status")})
        if solscan.get("verified") is True:
            out = dict(solscan)
            out.update({
                "source": SOURCE,
                "provider_actual": SOLSCAN_PROVIDER,
                "attempts": attempts,
            })
            return out
    else:
        attempts.append({"provider": SOLSCAN_PROVIDER, "status": "SOLSCAN_API_KEY_MISSING"})

    rpc = fetch_rpc_holder_truth(address, timeout=timeout)
    if rpc.get("verified") is True:
        rpc["attempts"] = attempts + list(rpc.get("attempts") or [])
        return rpc
    return {
        "verified": False,
        "status": "NO_TRUSTED_HOLDER_PROVIDER",
        "source": SOURCE,
        "attempts": attempts + list(rpc.get("attempts") or []),
    }
