from wallet500 import global_listing_intelligence as gli


def test_unknown_evm_listing_is_tested_on_every_supported_core_evm_chain():
    token = "0x1111111111111111111111111111111111111111"
    rows = gli._deep_scan_rows([{"token": token, "chain": "evm_unknown", "source": "test", "surface": "test", "observed_at": "2026-09-06T00:00:00+00:00"}])
    assert {x["chain"] for x in rows} == {"ethereum", "bsc", "arbitrum", "base"}
    assert all(x["token"] == token for x in rows)
