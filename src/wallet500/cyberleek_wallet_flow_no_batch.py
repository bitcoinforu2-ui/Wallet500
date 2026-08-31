from __future__ import annotations

import json
import time

from wallet500 import cyberleek_wallet_flow as flow


def _rpc_individual(method: str, params_list: list[list]) -> list:
    """Compatibility path for RPC providers that reject JSON-RPC batch bodies.

    Truth behavior stays fail-closed: an individual failed read is unresolved, and if
    every transport/RPC read in the chunk fails we raise so the parent writer emits
    RPC_ERROR_FAIL_CLOSED rather than pretending there were zero traders.
    """
    if not params_list:
        return []
    out: list = []
    failures = 0
    for index, params in enumerate(params_list):
        try:
            out.append(flow._rpc(method, params))
        except Exception:
            failures += 1
            out.append(None)
        if index + 1 < len(params_list):
            time.sleep(0.04)
    if failures == len(params_list):
        raise RuntimeError(f"RPC_{method}_ALL_INDIVIDUAL_READS_FAILED")
    return out


def main() -> None:
    flow._rpc_batch = _rpc_individual
    result = flow.run()
    print(json.dumps({"status": result.get("status"), "coverage": result.get("coverage")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
