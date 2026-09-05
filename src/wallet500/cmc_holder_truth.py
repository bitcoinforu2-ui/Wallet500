from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE = "COINMARKETCAP_HOLDER_INTELLIGENCE"
KEYLESS_ROOT = "https://pro-api.coinmarketcap.com/public-api"
KEYED_ROOT = "https://pro-api.coinmarketcap.com"
PLATFORM = "solana"


def _safe_error(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code:
        return f"HTTP_{code}"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _request_json(url: str, *, data: dict | None = None, api_key: str | None = None, timeout: int = 20, retries: int = 3):
    headers = {"Accept": "application/json", "User-Agent": "Wallet500-CMC-Holder/1.0"}
    body = None
    method = "GET"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    if api_key:
        headers["X-CMC_PRO_API_KEY"] = api_key
    last: BaseException | None = None
    for attempt in range(retries):
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last = exc
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except Exception as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    if last:
        raise last
    raise RuntimeError("CMC_REQUEST_FAILED")


def _unwrap(payload):
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data")
    if isinstance(data, (dict, list)):
        return data
    return payload


def parse_count_response(payload: dict, token_address: str) -> dict:
    obj = _unwrap(payload)
    if not isinstance(obj, dict):
        return {"verified": False, "status": "CMC_COUNT_INVALID_RESPONSE", "source": SOURCE}
    count = obj.get("count")
    returned = str(obj.get("tokenAddress") or obj.get("token_address") or "").strip()
    try:
        count = int(count)
    except (TypeError, ValueError):
        return {"verified": False, "status": "CMC_COUNT_MISSING", "source": SOURCE}
    if count < 0:
        return {"verified": False, "status": "CMC_COUNT_NEGATIVE", "source": SOURCE}
    if returned and returned != token_address:
        return {"verified": False, "status": "CMC_TOKEN_IDENTITY_MISMATCH", "source": SOURCE}
    return {
        "verified": True,
        "status": "OK",
        "source": SOURCE,
        "holder_count": count,
        "platform_id": obj.get("platformId") or obj.get("platform_id"),
        "semantics": "CoinMarketCap exact-token holder count for Solana",
    }


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_holder_list_response(payload, token_address: str, max_rows: int = 50) -> dict:
    obj = _unwrap(payload)
    holders = obj.get("holders") if isinstance(obj, dict) else None
    if not isinstance(holders, list):
        return {"verified": False, "status": "CMC_HOLDER_LIST_INVALID", "wallets": [], "tag_counts": {}}
    wallets = []
    tag_counts: dict[str, int] = {}
    for row in holders[:max_rows]:
        if not isinstance(row, dict):
            continue
        returned_token = str(row.get("tokenAddress") or "").strip()
        if returned_token and returned_token != token_address:
            continue
        wallet = str(row.get("walletAddress") or "").strip()
        if not wallet:
            continue
        raw_tags = row.get("tags")
        if isinstance(raw_tags, str):
            tags = [x.strip() for x in raw_tags.replace(";", ",").split(",") if x.strip()]
        elif isinstance(raw_tags, list):
            tags = [str(x).strip() for x in raw_tags if str(x).strip()]
        else:
            tags = []
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        wallets.append({
            "wallet_address": wallet,
            "percent": _num(row.get("percent")),
            "balance": row.get("balance"),
            "actual_balance": row.get("actualBalance"),
            "buy_usd": _num(row.get("buyUsd")),
            "sell_usd": _num(row.get("sellUsd")),
            "buy_count": row.get("buyCount"),
            "sell_count": row.get("sellCount"),
            "realized_pnl": _num(row.get("realizedPnl")),
            "realized_pnl_percent": _num(row.get("realizedPnlPercent")),
            "funding_source": row.get("fundingSource"),
            "first_active_time": row.get("firstActiveTime"),
            "last_active_time": row.get("lastActiveTime"),
            "wallet_create_time": row.get("walletCreateTime"),
            "tags": tags,
            "risk_level_flag": row.get("riskLevelFlag"),
            "blacklist_flag": row.get("blackListFlag"),
        })
    return {
        "verified": True,
        "status": "OK",
        "wallets": wallets,
        "wallet_sample_count": len(wallets),
        "tag_counts": tag_counts,
    }


def _root(api_key: str | None) -> str:
    return KEYED_ROOT if api_key else KEYLESS_ROOT


def fetch_holder_count(token_address: str, *, api_key: str | None = None, timeout: int = 20) -> dict:
    root = _root(api_key)
    url = root + "/v1/dex/holders/count?" + urlencode({"platform": PLATFORM, "tokenAddress": token_address})
    try:
        payload = _request_json(url, api_key=api_key, timeout=timeout)
    except Exception as exc:
        return {"verified": False, "status": _safe_error(exc), "source": SOURCE}
    return parse_count_response(payload, token_address)


def fetch_holder_list(token_address: str, *, api_key: str | None = None, timeout: int = 20) -> dict:
    root = _root(api_key)
    # Keyless documentation states public endpoints accept GET. The holder endpoint
    # reference still shows POST, so we use GET first and only fall back to POST.
    query = urlencode({"platform": PLATFORM, "tokenAddress": token_address, "tag": "tag_all"})
    try:
        payload = _request_json(root + "/v1/dex/holders/list?" + query, api_key=api_key, timeout=timeout)
        parsed = parse_holder_list_response(payload, token_address)
        if parsed.get("verified") is True:
            return parsed
    except Exception as first_exc:
        first_status = _safe_error(first_exc)
    else:
        first_status = "CMC_HOLDER_LIST_GET_INVALID"
    try:
        payload = _request_json(
            root + "/v1/dex/holders/list",
            data={"tokenAddress": token_address, "platform": PLATFORM, "tag": "tag_all"},
            api_key=api_key,
            timeout=timeout,
        )
        parsed = parse_holder_list_response(payload, token_address)
        if parsed.get("verified") is True:
            parsed["transport_fallback"] = "POST"
            return parsed
        return {**parsed, "first_attempt_status": first_status}
    except Exception as exc:
        return {
            "verified": False,
            "status": _safe_error(exc),
            "first_attempt_status": first_status,
            "wallets": [],
            "tag_counts": {},
        }


def fetch_holder_truth(token_address: str, timeout: int = 20) -> dict:
    api_key = str(os.getenv("CMC_PRO_API_KEY") or "").strip() or None
    count = fetch_holder_count(token_address, api_key=api_key, timeout=timeout)
    if count.get("verified") is not True:
        return count
    holder_list = fetch_holder_list(token_address, api_key=api_key, timeout=timeout)
    out = dict(count)
    out.update({
        "provider_actual": SOURCE,
        "auth_mode": "CMC_KEYED" if api_key else "CMC_KEYLESS_PUBLIC",
        "wallet_intelligence_status": holder_list.get("status"),
        "wallet_sample_count": holder_list.get("wallet_sample_count", 0),
        "wallets": list(holder_list.get("wallets") or []),
        "tag_counts": dict(holder_list.get("tag_counts") or {}),
        "wallet_list_verified": holder_list.get("verified") is True,
    })
    return out
