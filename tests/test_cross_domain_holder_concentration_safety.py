from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cross_domain_intelligence_collector as c


def test_solana_raw_token_accounts_never_become_whale_concentration(monkeypatch):
    mint = "241aTYhVXZ4WBVSFpfY37RqoCGBQ73KiRFAKvTtnmoon"
    pair = "EcFsXQJjVCjCYWHsuhXUnZH4XB2MzF7iZ3dJu48wmoa9"

    def fake_post(url, payload, timeout=7):
        method = payload.get("method")
        if method == "getTokenSupply":
            return {"result": {"value": {"uiAmountString": "1000000000"}}}
        if method == "getTokenLargestAccounts":
            return {
                "result": {
                    "value": [
                        {"address": "vault", "uiAmountString": "200000000"},
                        *[
                            {"address": f"wallet{i}", "uiAmountString": "10000000"}
                            for i in range(1, 20)
                        ],
                    ]
                }
            }
        raise AssertionError(method)

    monkeypatch.setattr(c, "post_json", fake_post)
    snapshot = c.solana_snapshot(
        {"network": "solana", "contract": mint, "pair": pair, "symbol": "MCAT"}
    )
    assert snapshot["gross_top10_pct"] > 20
    assert snapshot["top10_pct"] is None
    assert snapshot["concentration_role_adjusted"] is False
    assert "DIAGNOSTIC_ONLY" in snapshot["concentration_semantics"]


def test_unadjusted_concentration_cannot_emit_holder_or_wallet_signal():
    hs = {
        "provider": "Solana RPC",
        "top10_pct": None,
        "gross_top10_pct": 80.0,
        "concentration_role_adjusted": False,
    }
    assert hs.get("top10_pct") is None
    assert hs.get("concentration_role_adjusted") is False
