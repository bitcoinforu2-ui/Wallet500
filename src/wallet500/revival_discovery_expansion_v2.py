from __future__ import annotations

import json

from wallet500.revival_discovery_expansion import LATEST, main as expand_main


def main() -> None:
    expand_main()
    payload = json.loads(LATEST.read_text())
    coins = payload.get("coins") or []
    counts = payload.setdefault("counts", {})
    counts["universe"] = len(coins)
    counts["dex_verified_pairs"] = sum(
        1 for x in coins if x.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
    )
    counts["absorption_proxy_watch"] = sum(
        1 for x in coins if (x.get("order_flow_absorption") or {}).get("signal") is True
    )
    counts["absorption_proxy_outside_core"] = sum(
        1 for x in coins
        if (x.get("order_flow_absorption") or {}).get("signal") is True
        and x.get("watch_status") in {"ABSORPTION_WATCH", "ABSORPTION_WATCH_DISCOVERY_EXPANSION"}
    )
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({
        "combined_universe": counts.get("universe"),
        "dex_verified_pairs": counts.get("dex_verified_pairs"),
        "absorption_proxy_watch": counts.get("absorption_proxy_watch"),
        "absorption_proxy_outside_core": counts.get("absorption_proxy_outside_core"),
    }))


if __name__ == "__main__":
    main()
