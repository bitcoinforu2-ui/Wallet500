from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import cyberleek_wallet_flow as rpcbase
from . import revival_forensics_v2 as forensic

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-wallet-coverage-probe-state.json"
LATEST = DATA / "revival-wallet-coverage-probe.json"
VERSION = "REVIVAL_WALLET_COVERAGE_PROBE_V1"
MODE = "RESEARCH_ONLY_EXACT_PAIR_WALLET_COVERAGE_PROBE"
MAX_TARGETS = int(os.environ.get("REVIVAL_WALLET_PROBE_MAX_TARGETS", "96"))
FRESH_SECONDS = int(os.environ.get("REVIVAL_WALLET_PROBE_FRESH_SECONDS", "7200"))
MIN_AGE_DAYS = 180


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _iso(epoch: int | float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _targets(revival: dict) -> list[dict]:
    if revival.get("network") != "solana" or revival.get("no_hindsight") is not True:
        raise RuntimeError("WALLET_PROBE_REVIVAL_TRUTH_INVALID")
    out = []
    for coin in revival.get("coins") or []:
        if not isinstance(coin, dict):
            continue
        if coin.get("network_verified") is not True or str(coin.get("network") or "").lower() != "solana":
            continue
        if coin.get("market_age_verified") is not True or int(float(coin.get("market_age_min_days") or 0)) < MIN_AGE_DAYS:
            continue
        mint = forensic.token_key(coin)
        pair = forensic.exact_pair(coin)
        if not mint or not pair or coin.get("dex_link_type") != "DEXSCREENER_VERIFIED_PAIR":
            continue
        out.append({
            "token_address": mint,
            "symbol": coin.get("symbol"),
            "pair_address": pair,
            "watch_status": coin.get("watch_status"),
            "revival_score_verified": coin.get("revival_score_verified"),
        })
    out.sort(key=lambda row: str(row["token_address"]))
    return out


def _select(targets: list[dict], state: dict) -> list[dict]:
    if not targets or MAX_TARGETS <= 0:
        return []
    last = str(state.get("rotation_cursor_token") or "")
    index = next((i for i, row in enumerate(targets) if row["token_address"] == last), -1)
    start = (index + 1) % len(targets) if index >= 0 else 0
    count = min(MAX_TARGETS, len(targets))
    return [targets[(start + offset) % len(targets)] for offset in range(count)]


def _probe(target: dict, now: int) -> dict:
    mint = str(target["token_address"])
    pair = str(target["pair_address"])
    result = {
        "token_address": mint,
        "symbol": target.get("symbol"),
        "pair_address": pair,
        "observed_at": _iso(now),
        "coverage_verified": False,
        "promotion_eligible": False,
        "positive": False,
        "sample_depth": 1,
        "status": "RPC_ERROR_FAIL_CLOSED",
        "resolved_signed_owner": False,
        "target_mint_touched": False,
        "unresolved_target_touch": False,
        "truth_contract": {
            "exact_pair_only": True,
            "single_latest_pair_transaction_probe": True,
            "does_not_claim_full_accumulation_coverage": True,
            "does_not_contribute_positive_alpha": True,
            "does_not_change_real_alert_gate": True,
        },
    }
    try:
        sigs = rpcbase._rpc("getSignaturesForAddress", [pair, {"limit": 1, "commitment": "confirmed"}]) or []
        valid = [row for row in sigs if isinstance(row, dict) and row.get("signature")]
        if not valid:
            result.update({"coverage_verified": True, "status": "VERIFIED_NO_RECENT_PAIR_TRANSACTION"})
            return result
        row = valid[0]
        tx = rpcbase._rpc(
            "getTransaction",
            [row["signature"], {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
        )
        if not isinstance(tx, dict):
            result["status"] = "RPC_TRANSACTION_READ_FAILED"
            return result
        if (tx.get("meta") or {}).get("err") is not None:
            result.update({"coverage_verified": True, "status": "VERIFIED_LATEST_PAIR_TRANSACTION_FAILED"})
            return result
        deltas = rpcbase._mint_owner_deltas(tx, mint)
        if not deltas:
            result.update({"coverage_verified": True, "status": "VERIFIED_LATEST_PAIR_TRANSACTION_NOT_TARGET_MINT"})
            return result
        result["target_mint_touched"] = True
        signers = rpcbase._signers(tx)
        signed = [(wallet, delta) for wallet, delta in deltas.items() if wallet in signers and abs(float(delta)) > 1e-12]
        if signed:
            result.update({
                "coverage_verified": True,
                "resolved_signed_owner": True,
                "status": "VERIFIED_SIGNED_OWNER_TARGET_TOUCH",
            })
        else:
            result.update({
                "unresolved_target_touch": True,
                "status": "PARTIAL_TARGET_TOUCH_OWNER_UNRESOLVED",
            })
        return result
    except Exception as exc:
        result["error"] = type(exc).__name__
        return result


def run() -> dict:
    now = _now()
    revival = _load(REVIVAL, {})
    targets = _targets(revival)
    state = _load(STATE, {"version": VERSION, "tokens": {}, "rotation_cursor_token": None})
    token_state = state.setdefault("tokens", {})
    selected = _select(targets, state)
    target_by = {row["token_address"]: row for row in targets}

    for target in selected:
        token_state[target["token_address"]] = _probe(target, now)
    if selected:
        state["rotation_cursor_token"] = selected[-1]["token_address"]

    fresh_rows = []
    for mint, target in target_by.items():
        row = token_state.get(mint)
        if not isinstance(row, dict):
            continue
        if str(row.get("pair_address") or "").lower() != str(target["pair_address"]).lower():
            continue
        stamp = row.get("observed_at")
        try:
            observed = int(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp())
        except Exception:
            continue
        age = now - observed
        if age < 0 or age > FRESH_SECONDS:
            continue
        published = dict(row)
        published["evidence_age_seconds"] = age
        fresh_rows.append(published)

    state["version"] = VERSION
    state["updated_at"] = _iso(now)
    state["candidate_universe"] = len(targets)
    _write(STATE, state)

    payload = {
        "version": VERSION,
        "mode": MODE,
        "generated_at": _iso(now),
        "network": "solana",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "candidate_universe": len(targets),
        "selected_this_run": len(selected),
        "published_fresh_rows": len(fresh_rows),
        "coverage_verified": sum(1 for row in fresh_rows if row.get("coverage_verified") is True),
        "coverage_partial": sum(1 for row in fresh_rows if row.get("coverage_verified") is not True),
        "rotation": {
            "max_targets_per_run": MAX_TARGETS,
            "freshness_seconds": FRESH_SECONDS,
            "cursor_token": state.get("rotation_cursor_token"),
            "future_data_used": False,
        },
        "truth_contract": {
            "minimum_market_age_days": MIN_AGE_DAYS,
            "exact_pair_required": True,
            "probe_is_coverage_only_not_accumulation_alpha": True,
            "probe_verified_never_counts_as_positive_wallet_accumulation": True,
            "probe_never_changes_candidate_promotion": True,
            "probe_never_changes_real_alert_gate": True,
            "unresolved_target_mint_touch_fails_closed": True,
            "no_hindsight": True,
        },
        "tokens": sorted(fresh_rows, key=lambda row: str(row.get("token_address") or "")),
    }
    _write(LATEST, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "candidate_universe": payload["candidate_universe"],
        "selected_this_run": payload["selected_this_run"],
        "published_fresh_rows": payload["published_fresh_rows"],
        "coverage_verified": payload["coverage_verified"],
        "coverage_partial": payload["coverage_partial"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
