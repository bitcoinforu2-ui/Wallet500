from __future__ import annotations

"""Run the guarded CEX action lane with official Binance/Bybit endpoint failover."""

import run_cex_action_guarded as guard
from wallet500.cex_endpoint_fallbacks import install

install(guard.promo)


if __name__ == "__main__":
    guard.promo.run()
    guard.bypass.run()
