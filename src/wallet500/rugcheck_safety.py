from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RUGCHECK_SUMMARY_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
MIN_LP_LOCKED_PCT = 95.0
BLOCKING_RISK_LEVELS = {"danger", "critical"}


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def interpret_summary(payload: Any, min_lp_locked_pct: float = MIN_LP_LOCKED_PCT) -> dict:
    if not isinstance(payload, dict):
        return {
            "verified": False,
            "status": "RUGCHECK_INVALID_RESPONSE",
            "lp_integrity_safe": None,
            "lp_locked_pct": None,
            "blocking_risks": [],
        }
    if payload.get("error"):
        return {
            "verified": False,
            "status": "RUGCHECK_ERROR_RESPONSE",
            "error": str(payload.get("error"))[:200],
            "lp_integrity_safe": None,
            "lp_locked_pct": _number(payload.get("lpLockedPct")),
            "blocking_risks": [],
        }

    lp_locked_pct = _number(payload.get("lpLockedPct"))
    risks = [x for x in (payload.get("risks") or []) if isinstance(x, dict)]
    blocking = [
        {
            "name": str(risk.get("name") or ""),
            "level": str(risk.get("level") or ""),
            "score": risk.get("score"),
            "value": risk.get("value"),
        }
        for risk in risks
        if str(risk.get("level") or "").strip().lower() in BLOCKING_RISK_LEVELS
    ]

    if lp_locked_pct is None:
        lp_safe = None
        status = "RUGCHECK_LP_UNKNOWN"
    elif lp_locked_pct < min_lp_locked_pct:
        lp_safe = False
        status = "RUGCHECK_LP_BELOW_THRESHOLD"
    elif blocking:
        lp_safe = False
        status = "RUGCHECK_BLOCKING_RISK"
    else:
        lp_safe = True
        status = "RUGCHECK_LP_VERIFIED"

    return {
        "verified": lp_locked_pct is not None,
        "status": status,
        "lp_integrity_safe": lp_safe,
        "lp_locked_pct": lp_locked_pct,
        "min_lp_locked_pct": float(min_lp_locked_pct),
        "blocking_risks": blocking,
        "risk_count": len(risks),
        "score": payload.get("score"),
        "score_normalised": payload.get("score_normalised"),
        "token_program": payload.get("tokenProgram"),
        "token_type": payload.get("tokenType"),
    }


def fetch_rugcheck_safety(mint: str, timeout: int = 10) -> dict:
    mint = str(mint or "").strip()
    if not mint:
        return {
            "verified": False,
            "status": "RUGCHECK_MINT_MISSING",
            "lp_integrity_safe": None,
            "lp_locked_pct": None,
            "blocking_risks": [],
        }
    req = Request(
        RUGCHECK_SUMMARY_URL.format(mint=mint),
        headers={"Accept": "application/json", "User-Agent": "Wallet500-Genesis/1.0"},
    )
    try:
        with urlopen(req, timeout=max(3, int(timeout))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return interpret_summary(payload)
    except HTTPError as exc:
        return {
            "verified": False,
            "status": f"RUGCHECK_HTTP_{exc.code}",
            "lp_integrity_safe": None,
            "lp_locked_pct": None,
            "blocking_risks": [],
        }
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "verified": False,
            "status": f"RUGCHECK_UNAVAILABLE:{type(exc).__name__}",
            "lp_integrity_safe": None,
            "lp_locked_pct": None,
            "blocking_risks": [],
        }
