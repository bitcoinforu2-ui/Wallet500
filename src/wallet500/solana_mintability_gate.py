from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA = Path("data")
STATE = DATA / "solana-mintability-state.json"
REVIVAL_REPORT = DATA / "solana-mintability-revival-report.json"
ACTIVE_REPORT = DATA / "solana-mintability-active-report.json"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
BATCH_SIZE = 100
SPL_TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _token(row: dict) -> str:
    return str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()


def _chain(row: dict) -> str:
    return str(row.get("chain") or row.get("network") or "").strip().lower()


def _rpc_urls() -> list[str]:
    preferred = os.getenv("SOLANA_RPC_URL", "").strip()
    values = [preferred, DEFAULT_RPC]
    return list(dict.fromkeys(x for x in values if x))


def _post_rpc(url: str, method: str, params: list, timeout: int = 35):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "Wallet500-Mintability/1.0"})
    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError(f"RPC_{method}_ERROR:{payload['error']}")
    return payload.get("result")


def _parse_mint_account(mint: str, account: dict | None, checked_at: str) -> dict:
    if not isinstance(account, dict):
        return {
            "token_address": mint,
            "status": "UNVERIFIED_BLOCKED",
            "mintability_verified": False,
            "mintable": None,
            "mint_authority": None,
            "checked_at": checked_at,
            "reason": "MINT_ACCOUNT_MISSING_OR_UNPARSED",
            "immutable_safe": False,
        }
    owner = str(account.get("owner") or "")
    data = account.get("data") if isinstance(account.get("data"), dict) else {}
    parsed = data.get("parsed") if isinstance(data.get("parsed"), dict) else {}
    info = parsed.get("info") if isinstance(parsed.get("info"), dict) else {}
    if owner not in SPL_TOKEN_PROGRAMS or parsed.get("type") != "mint" or "mintAuthority" not in info:
        return {
            "token_address": mint,
            "status": "UNVERIFIED_BLOCKED",
            "mintability_verified": False,
            "mintable": None,
            "mint_authority": None,
            "program_owner": owner or None,
            "checked_at": checked_at,
            "reason": "NOT_VERIFIED_SPL_MINT_ACCOUNT",
            "immutable_safe": False,
        }
    authority = info.get("mintAuthority")
    if authority is None:
        return {
            "token_address": mint,
            "status": "NON_MINTABLE_VERIFIED",
            "mintability_verified": True,
            "mintable": False,
            "mint_authority": None,
            "freeze_authority": info.get("freezeAuthority"),
            "program_owner": owner,
            "checked_at": checked_at,
            "reason": "MINT_AUTHORITY_REVOKED_NULL",
            "immutable_safe": True,
        }
    return {
        "token_address": mint,
        "status": "MINTABLE_BLOCKED",
        "mintability_verified": True,
        "mintable": True,
        "mint_authority": authority,
        "freeze_authority": info.get("freezeAuthority"),
        "program_owner": owner,
        "checked_at": checked_at,
        "reason": "MINT_AUTHORITY_PRESENT_HARD_BLOCK",
        "immutable_safe": False,
    }


def _fetch_batch(mints: list[str], checked_at: str) -> dict[str, dict]:
    last_error = None
    for rpc in _rpc_urls():
        try:
            result = _post_rpc(rpc, "getMultipleAccounts", [mints, {"encoding": "jsonParsed", "commitment": "confirmed"}]) or {}
            values = result.get("value") if isinstance(result, dict) else None
            if not isinstance(values, list) or len(values) != len(mints):
                raise RuntimeError("RPC_GET_MULTIPLE_ACCOUNTS_LENGTH_MISMATCH")
            return {mint: _parse_mint_account(mint, account, checked_at) for mint, account in zip(mints, values)}
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{exc}"
    return {
        mint: {
            "token_address": mint,
            "status": "UNVERIFIED_BLOCKED",
            "mintability_verified": False,
            "mintable": None,
            "mint_authority": None,
            "checked_at": checked_at,
            "reason": "RPC_MINTABILITY_VERIFICATION_FAILED",
            "error": last_error,
            "immutable_safe": False,
        }
        for mint in mints
    }


def resolve(mints: list[str], state: dict | None = None, checked_at: str | None = None) -> tuple[dict[str, dict], dict]:
    checked_at = checked_at or _now()
    state = state if isinstance(state, dict) else {}
    cached = state.get("tokens") if isinstance(state.get("tokens"), dict) else {}
    unique = list(dict.fromkeys(str(x or "").strip() for x in mints if str(x or "").strip()))
    resolved: dict[str, dict] = {}
    to_check: list[str] = []
    for mint in unique:
        row = cached.get(mint) if isinstance(cached.get(mint), dict) else None
        # A revoked/null mint authority is irreversible in the SPL mint account,
        # so a previously verified safe result can be reused permanently.
        if row and row.get("status") == "NON_MINTABLE_VERIFIED" and row.get("mintability_verified") is True and row.get("mintable") is False and row.get("mint_authority") is None:
            resolved[mint] = row
        else:
            # Mintable and unknown tokens are rechecked every run because a project
            # may revoke its authority later and become eligible in the future.
            to_check.append(mint)
    for start in range(0, len(to_check), BATCH_SIZE):
        resolved.update(_fetch_batch(to_check[start:start + BATCH_SIZE], checked_at))
    merged = dict(cached)
    merged.update(resolved)
    next_state = {
        "version": 1,
        "updated_at": checked_at,
        "policy": "SOLANA_MINT_AUTHORITY_MUST_BE_REVOKED_NULL",
        "fail_closed_unknown": True,
        "tokens": merged,
    }
    return resolved, next_state


def _enrich(row: dict, truth: dict) -> dict:
    return {
        **row,
        "mintability_verified": truth.get("mintability_verified") is True,
        "mintable": truth.get("mintable"),
        "mint_authority": truth.get("mint_authority"),
        "mintability_status": truth.get("status"),
        "mintability_checked_at": truth.get("checked_at"),
        "mint_program_owner": truth.get("program_owner"),
    }


def _is_safe(truth: dict) -> bool:
    return bool(
        truth.get("status") == "NON_MINTABLE_VERIFIED"
        and truth.get("mintability_verified") is True
        and truth.get("mintable") is False
        and truth.get("mint_authority") is None
    )


def enforce_revival(data_dir: Path = DATA) -> dict:
    latest_path = data_dir / "revival-1000-latest.json"
    payload = _load(latest_path, {})
    coins = [x for x in (payload.get("coins") or []) if isinstance(x, dict)]
    state_path = data_dir / STATE.name
    current_state = _load(state_path, {})
    solana = [x for x in coins if _chain(x) == "solana" and _token(x)]
    truth, next_state = resolve([_token(x) for x in solana], current_state)
    accepted, rejected = [], []
    for row in coins:
        if _chain(row) != "solana":
            # Revival Solana should never contain another chain; fail closed anyway.
            rejected.append({"symbol": row.get("symbol"), "token_address": _token(row), "status": "NON_SOLANA_BLOCKED"})
            continue
        t = truth.get(_token(row)) or (next_state.get("tokens") or {}).get(_token(row)) or {}
        enriched = _enrich(row, t)
        if _is_safe(t):
            accepted.append(enriched)
        else:
            rejected.append({
                "symbol": row.get("symbol"),
                "token_address": _token(row),
                "pair_address": row.get("dex_pair_address") or row.get("pair_address"),
                "status": t.get("status") or "UNVERIFIED_BLOCKED",
                "mintable": t.get("mintable"),
                "mint_authority": t.get("mint_authority"),
                "reason": t.get("reason") or "MINTABILITY_NOT_VERIFIED_SAFE",
            })
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    counts["universe"] = len(accepted)
    counts["mintability_verified_non_mintable"] = len(accepted)
    counts["mintable_rejected"] = sum(x.get("status") == "MINTABLE_BLOCKED" for x in rejected)
    counts["mintability_unverified_rejected"] = sum(x.get("status") != "MINTABLE_BLOCKED" for x in rejected)
    counts["dex_verified_pairs"] = sum(x.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR" for x in accepted)
    counts["absorption_proxy_watch"] = sum((x.get("order_flow_absorption") or {}).get("signal") is True for x in accepted)
    counts["absorption_candidate_proxy_watch"] = sum(x.get("absorption_candidate_proxy") is True for x in accepted)
    counts["absorption_discovery_expansion_added"] = sum(x.get("source") == "revival_discovery_state+dexscreener_absorption_expansion" for x in accepted)
    counts["absorption_discovery_strict_added"] = sum(x.get("source") == "revival_discovery_state+dexscreener_absorption_expansion" and x.get("watch_status") == "ABSORPTION_WATCH_DISCOVERY_EXPANSION" for x in accepted)
    counts["absorption_discovery_candidate_added"] = sum(x.get("source") == "revival_discovery_state+dexscreener_absorption_expansion" and x.get("watch_status") == "ABSORPTION_CANDIDATE_DISCOVERY_EXPANSION" for x in accepted)
    payload["coins"] = accepted
    payload["counts"] = counts
    payload["mintability_gate"] = {
        "version": 1,
        "status": "ENFORCED_FAIL_CLOSED",
        "chain": "solana",
        "hard_rule": "MINT_AUTHORITY_MUST_BE_REVOKED_NULL",
        "mintable_tokens_allowed": False,
        "unverified_tokens_allowed": False,
        "verified_non_mintable": len(accepted),
        "rejected_total": len(rejected),
        "mintable_rejected": counts["mintable_rejected"],
        "unverified_rejected": counts["mintability_unverified_rejected"],
    }
    _write(latest_path, payload)
    _write(state_path, next_state)
    report = {
        "version": 1,
        "generated_at": next_state["updated_at"],
        "mode": "SOLANA_NON_MINTABLE_HARD_GATE_REVIVAL",
        "status": "ENFORCED_FAIL_CLOSED",
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejections": rejected,
    }
    _write(data_dir / REVIVAL_REPORT.name, report)
    return report


def enforce_active(data_dir: Path = DATA) -> dict:
    active_path = data_dir / "active-qualified-candidates.json"
    watch_path = data_dir / "watchlist.json"
    active = _load(active_path, [])
    active = [x for x in active if isinstance(x, dict)] if isinstance(active, list) else []
    state_path = data_dir / STATE.name
    current_state = _load(state_path, {})
    solana_mints = [_token(x) for x in active if _chain(x) == "solana" and _token(x)]
    truth, next_state = resolve(solana_mints, current_state)
    accepted, rejected = [], []
    blocked_tokens = set()
    for row in active:
        if _chain(row) != "solana":
            accepted.append(row)
            continue
        token = _token(row)
        t = truth.get(token) or (next_state.get("tokens") or {}).get(token) or {}
        enriched = _enrich(row, t)
        if _is_safe(t):
            accepted.append(enriched)
        else:
            blocked_tokens.add(token)
            rejected.append({
                "symbol": row.get("symbol"),
                "token_address": token,
                "pair_address": row.get("pair_address") or row.get("dex_pair_address"),
                "status": t.get("status") or "UNVERIFIED_BLOCKED",
                "mintable": t.get("mintable"),
                "mint_authority": t.get("mint_authority"),
                "reason": t.get("reason") or "MINTABILITY_NOT_VERIFIED_SAFE",
            })
    watch = _load(watch_path, [])
    if isinstance(watch, list) and blocked_tokens:
        watch = [x for x in watch if not (isinstance(x, dict) and _chain(x) == "solana" and _token(x) in blocked_tokens)]
        _write(watch_path, watch)
    _write(active_path, accepted)
    _write(state_path, next_state)
    report = {
        "version": 1,
        "generated_at": next_state["updated_at"],
        "mode": "SOLANA_NON_MINTABLE_HARD_GATE_ACTIVE",
        "status": "ENFORCED_FAIL_CLOSED",
        "active_before": len(active),
        "active_after": len(accepted),
        "rejected": len(rejected),
        "rejections": rejected,
    }
    _write(data_dir / ACTIVE_REPORT.name, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revival", action="store_true")
    parser.add_argument("--active", action="store_true")
    args = parser.parse_args()
    if not args.revival and not args.active:
        args.revival = True
    outputs = {}
    if args.revival:
        outputs["revival"] = enforce_revival()
    if args.active:
        outputs["active"] = enforce_active()
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
