from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE = "SOLSCAN_V2_TOKEN_HOLDERS_TOTAL"
ENDPOINT = "https://pro-api.solscan.io/v2.0/token/holders"


def _safe_error(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code:
        return f"HTTP_{code}"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def parse_holder_response(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return {"verified": False, "status": "INVALID_RESPONSE"}
    data = payload.get("data") or {}
    total = data.get("total")
    items = data.get("items") or []
    try:
        total = int(total)
    except (TypeError, ValueError):
        return {"verified": False, "status": "TOTAL_MISSING"}
    if total < 0:
        return {"verified": False, "status": "TOTAL_NEGATIVE"}
    sampled_owners = []
    for row in items:
        if not isinstance(row, dict):
            continue
        owner = str(row.get("owner") or "").strip()
        if owner:
            sampled_owners.append(owner)
    if items and not sampled_owners:
        return {"verified": False, "status": "OWNER_FIELD_MISSING"}
    return {
        "verified": True,
        "status": "OK",
        "source": SOURCE,
        "holder_count": total,
        "sample_owner_rows": len(sampled_owners),
        "sample_unique_owners": len(set(sampled_owners)),
        "semantics": "Solscan v2 token holders total; rows expose token-account address and owner separately",
    }


def fetch_holder_truth(address: str, api_key: str | None, timeout: int = 20) -> dict:
    if not api_key:
        return {
            "verified": False,
            "status": "SOLSCAN_API_KEY_MISSING",
            "source": SOURCE,
        }
    url = ENDPOINT + "?" + urlencode({"address": address, "page": 1, "page_size": 40})
    req = Request(
        url,
        headers={
            "accept": "application/json",
            "token": api_key,
            "User-Agent": "Wallet500-HolderTruth/2.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "verified": False,
            "status": _safe_error(exc),
            "source": SOURCE,
        }
    result = parse_holder_response(payload)
    result.setdefault("source", SOURCE)
    return result


def suspicious_jump(previous_count: int | None, current_count: int, threshold_pct: float = 25.0) -> bool:
    if previous_count is None or previous_count <= 0:
        return False
    delta_pct = abs((float(current_count) / float(previous_count) - 1.0) * 100.0)
    return delta_pct > threshold_pct
