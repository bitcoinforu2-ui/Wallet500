from __future__ import annotations

import json
import time
import urllib.error
from pathlib import Path
from typing import Any

from . import kol_revival_convergence as engine


LEDGER = Path("data/kol-revival-convergence-ledger.json")
SUMMARY = Path("data/kol-revival-convergence-summary.json")


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def install_rpc_hardening() -> None:
    original_rpc = engine._rpc
    original_tx = engine._tx_for_signature
    last_call = {"at": 0.0}
    tx_cache: dict[tuple[str, str], dict[str, Any] | None] = {}

    def throttled_retry_rpc(rpc_url: str, method: str, params: list[Any]) -> Any:
        # Public/free Solana RPCs commonly rate-limit bursty getTransaction traffic.
        # A small cross-call gap plus exponential retry is cheaper than silently losing a BUY.
        for attempt in range(6):
            gap = 0.16 - (time.monotonic() - last_call["at"])
            if gap > 0:
                time.sleep(gap)
            try:
                out = original_rpc(rpc_url, method, params)
                last_call["at"] = time.monotonic()
                return out
            except urllib.error.HTTPError as exc:
                last_call["at"] = time.monotonic()
                if exc.code != 429 or attempt >= 5:
                    raise
                time.sleep(min(8.0, 0.8 * (2**attempt)))
            except (urllib.error.URLError, TimeoutError, RuntimeError):
                last_call["at"] = time.monotonic()
                if attempt >= 5:
                    raise
                time.sleep(min(8.0, 0.6 * (2**attempt)))
        raise RuntimeError("RPC_RETRY_EXHAUSTED")

    engine._rpc = throttled_retry_rpc

    def cached_tx(rpc_url: str, signature: str) -> dict[str, Any] | None:
        key = (rpc_url, signature)
        if key in tx_cache:
            return tx_cache[key]
        # original_tx resolves engine._rpc dynamically, so it receives the hardened RPC above.
        tx = original_tx(rpc_url, signature)
        tx_cache[key] = tx
        return tx

    engine._tx_for_signature = cached_tx


def run() -> dict[str, Any]:
    before = _load(LEDGER)
    before_boundaries = dict(before.get("wallet_boundaries") or {})
    install_rpc_hardening()
    summary = engine.run_once()

    # Critical no-loss rule: the engine historically advances a wallet boundary even when one
    # transaction in that interval could not be parsed because the RPC rate-limited us. Roll that
    # wallet back to the previous boundary so the next 5-minute run retries the interval. Event IDs
    # are immutable/deduped, therefore already-recorded BUYs are not double-booked.
    retry_wallets = {
        str(e.get("wallet_id") or "")
        for e in (summary.get("errors") or [])
        if str(e.get("stage") or "") == "PARSE_SWAP"
        and any(x in str(e.get("error") or "").upper() for x in ("429", "TIMEOUT", "URLERROR", "RPC"))
    }
    retry_wallets.discard("")
    if retry_wallets:
        ledger = _load(LEDGER)
        boundaries = ledger.setdefault("wallet_boundaries", {})
        rolled_back = []
        for wid in sorted(retry_wallets):
            prior = before_boundaries.get(wid)
            if prior:
                boundaries[wid] = prior
                rolled_back.append(wid)
        ledger["rpc_retry_wallets"] = rolled_back
        ledger["rpc_no_loss_boundary_rollback"] = bool(rolled_back)
        _write(LEDGER, ledger)
        summary["rpc_retry_wallets"] = rolled_back
        summary["rpc_no_loss_boundary_rollback"] = bool(rolled_back)
        _write(SUMMARY, summary)
    else:
        summary["rpc_retry_wallets"] = []
        summary["rpc_no_loss_boundary_rollback"] = False
        _write(SUMMARY, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
