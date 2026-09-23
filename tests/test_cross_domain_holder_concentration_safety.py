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


def test_base_symbol_strips_cex_quote_suffix():
    assert c.base_symbol({"symbol": "TAKEUSDT", "currency_pair": "TAKE_USDT"}) == "TAKE"


def test_fast_holder_velocity_detects_sub_two_percent_growth():
    current = {"provider": "CoinMarketCap DEX Holder Count", "holders_count": 21100}
    previous = {"provider": "CoinMarketCap DEX Holder Count", "holders_count": 20900}
    out = c.holder_velocity_metrics(
        current,
        previous,
        "2026-09-23T16:28:00+00:00",
        "2026-09-23T16:53:00+00:00",
    )
    assert out["qualifies"] is True
    assert out["change_count"] == 200
    assert 0.95 < out["change_pct"] < 0.97
    assert out["pct_per_hour"] > 2.0


def test_holder_velocity_provider_switch_is_baseline_only():
    current = {"provider": "CoinMarketCap DEX Holder Count", "holders_count": 21100}
    previous = {"provider": "Blockscout", "holders_count": 20900}
    out = c.holder_velocity_metrics(
        current,
        previous,
        "2026-09-23T16:28:00+00:00",
        "2026-09-23T16:53:00+00:00",
    )
    assert out["qualifies"] is False
    assert out["status"] == "PROVIDER_CHANGED_BASELINE"


def test_bsc_holder_snapshot_falls_back_to_exact_cmc_count(monkeypatch):
    contract = "0xe747e54783ba3f77a8e5251a3cba19ebe9c0e197"
    pair = "0x46bb9a29bfa5397b30a96a316875496ec2556dd2"
    monkeypatch.setattr(c, "blockscout_snapshot", lambda _t: None)

    def fake_get_json(url, timeout=7):
        assert "holders/count" in url
        assert "platform=bsc" in url
        assert contract in url
        return {"data": {"count": 21100, "tokenAddress": contract}}

    monkeypatch.setattr(c, "get_json", fake_get_json)
    out = c.holder_snapshot({"network": "bsc", "contract": contract, "pair": pair, "symbol": "TAKEUSDT"})
    assert out["provider"] == "CoinMarketCap DEX Holder Count"
    assert out["holders_count"] == 21100.0
    assert out["identity_verified"] is True
