from __future__ import annotations

"""Run the guarded CEX action lane with resilient endpoints and hold confirmation."""

import run_cex_action_guarded as guard
from wallet500.cex_endpoint_fallbacks import install
from wallet500.cex_reactivation_hold import install as install_reactivation_hold

install(guard.promo)
reactivation_hold = install_reactivation_hold(guard)


if __name__ == "__main__":
    guard.promo.run()
    guard.bypass.run()
    reactivation_hold.persist()
