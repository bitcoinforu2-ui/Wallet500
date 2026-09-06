from __future__ import annotations

import json
import time

from . import cyberleek_wallet_flow as rpcbase
from . import revival_prewaking_wallet_evidence as pre
from . import revival_prewaking_wallet_retention as retention
from . import revival_wallet_evidence as collector


def _fetch_transactions_resilient(rows: list[dict], mint: str) -> tuple[list[dict], int]:
    """Resolve exact-mint signed-owner swaps without treating unrelated pair traffic as missing data.

    A pair address can receive LP maintenance, routing, failed transactions and other
    instructions that do not touch the target mint. Those rows are not swaps and must
    not dilute the wallet-resolution denominator. A transaction is still unresolved
    when it does touch the target mint but a signed token owner cannot be proven.
    """
    events: list[dict] = []
    unresolved = 0
    valid = [row for row in rows if row.get("signature")]
    read_failures = 0
    for index, row in enumerate(valid):
        signature = str(row.get("signature") or "")
        try:
            tx = rpcbase._rpc(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "commitment": "confirmed",
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            )
        except Exception:
            tx = None
            read_failures += 1

        if not isinstance(tx, dict):
            unresolved += 1
        elif (tx.get("meta") or {}).get("err") is not None:
            pass
        else:
            deltas = rpcbase._mint_owner_deltas(tx, mint)
            if not deltas:
                pass
            else:
                event = collector._extract_trade(tx, signature, mint, row.get("blockTime"))
                if event:
                    events.append(event)
                else:
                    unresolved += 1

        if index + 1 < len(valid):
            time.sleep(0.035)

    if valid and read_failures == len(valid):
        raise RuntimeError("RPC_GETTRANSACTION_ALL_READS_FAILED")
    return events, unresolved


def run() -> dict:
    collector._fetch_transactions = _fetch_transactions_resilient
    payload = pre.run()
    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth["pair_signatures_without_target_mint_delta_excluded_from_resolution_denominator"] = True
    truth["target_mint_touch_without_signed_owner_remains_unresolved"] = True
    payload["truth_contract"] = truth
    payload["resolution_policy"] = "EXACT_MINT_TOUCH_DENOMINATOR_V2"
    collector._write(pre.LATEST, payload)
    payload = retention.retain_fresh_rotation_evidence(payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "version": payload.get("version"),
        "targets": payload.get("targets"),
        "published_wallet_evidence_rows": payload.get("published_wallet_evidence_rows"),
        "resolution_policy": payload.get("resolution_policy"),
        "selection_policy": payload.get("selection_policy"),
        "rotation_retention": payload.get("rotation_retention"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
