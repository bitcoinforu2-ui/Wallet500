from wallet500 import holder_cluster_gate as h


def _holders(*pcts):
    return [{"owner": f"0x{i+1:040x}", "pct": pct} for i, pct in enumerate(pcts)]


def test_exact_pair_is_excluded_and_replaced_by_next_holder():
    holders = _holders(25, 15, 12, 10, 8, 7, 6, 5, 4, 3, 2, 1)
    pair = holders[0]["owner"]
    d = h._role_aware_distribution("BSC", holders, pair_address=pair, registry=[])
    assert d["gross_top1_pct"] == 25
    assert d["adjusted_top1_pct"] == 15
    assert d["adjusted_top10_pct"] == sum(x["pct"] for x in holders[1:11])
    assert d["adjusted_top10_complete"] is True
    assert d["dex_lp_pct"] == 25


def test_high_confidence_cex_custody_is_not_a_single_whale_but_is_tracked():
    custody = "0x73d8bd54f7cf5fab43fe4ef40a62d390644946db"
    pair = "0x9b487fe6c7f4d62df0a63dbfb0b56b60e55c55f5"
    holders = [{"owner": custody, "pct": 42.59}, {"owner": pair, "pct": 21.66}] + _holders(3.08, 1.21, 1.01, 1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7)
    registry = [{"chain": "BSC", "address": custody, "role": "CEX_CUSTODY", "label": "Binance Wallet", "confidence": 0.95}]
    d = h._role_aware_distribution("BSC", holders, pair_address=pair, registry=registry)
    assert round(d["cex_custody_pct"], 2) == 42.59
    assert round(d["dex_lp_pct"], 2) == 21.66
    assert round(d["known_infrastructure_pct"], 2) == 64.25
    assert d["adjusted_top1_pct"] == 3.08
    assert d["adjusted_top10_complete"] is True


def test_low_confidence_cex_label_remains_counted_fail_closed():
    custody = "0x73d8bd54f7cf5fab43fe4ef40a62d390644946db"
    holders = [{"owner": custody, "pct": 42.59}] + _holders(5, 4, 3, 2, 1, 1, 1, 1, 1, 1)
    registry = [{"chain": "BSC", "address": custody, "role": "CEX_CUSTODY", "confidence": 0.70}]
    d = h._role_aware_distribution("BSC", holders, registry=registry)
    assert d["adjusted_top1_pct"] == 42.59
    assert d["cex_custody_pct"] == 42.59
    assert d["known_infrastructure_pct"] == 0
    assert d["holders"][0]["excluded_from_whale_concentration"] is False


def test_registry_is_chain_and_exact_address_scoped():
    address = "0x73d8bd54f7cf5fab43fe4ef40a62d390644946db"
    registry = [{"chain": "BSC", "address": address, "role": "CEX_CUSTODY", "confidence": 0.95}]
    assert h._registered_role("BSC", address.upper(), registry)["role"] == "CEX_CUSTODY"
    assert h._registered_role("ETHEREUM", address, registry) is None
    assert h._registered_role("BSC", "0x0000000000000000000000000000000000000001", registry) is None


def test_unknown_large_holder_still_blocks_complete_evm(monkeypatch):
    holders = [{"owner": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "pct": 45.0}] + _holders(5, 4, 3, 2, 1, 1, 1, 1, 1, 1, 1)
    monkeypatch.setattr(h, "_evm_holders", lambda chain, token, row: (holders, [], [], {"complete": True, "reason": "FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK"}))
    monkeypatch.setattr(h, "_role_registry", lambda: [])
    out = h.analyze({"chain": "BSC", "token": "0x123", "deployment_block": 1})
    assert out["status"] == "BLOCK"
    assert out["adjusted_real_top1_pct"] == 45.0
    assert "TOP1_OWNER_CONCENTRATION_HIGH" in out["reasons"]


def test_cex_custody_monitor_does_not_claim_funds_are_locked(monkeypatch):
    custody = "0x73d8bd54f7cf5fab43fe4ef40a62d390644946db"
    pair = "0x9b487fe6c7f4d62df0a63dbfb0b56b60e55c55f5"
    holders = [{"owner": custody, "pct": 42.0}, {"owner": pair, "pct": 20.0}] + _holders(5, 4, 3, 2, 1, 1, 1, 1, 1, 1, 1, 1)
    monkeypatch.setattr(h, "_evm_holders", lambda chain, token, row: (holders, [], [], {"complete": True, "reason": "FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK"}))
    monkeypatch.setattr(h, "_role_registry", lambda: [{"chain": "BSC", "address": custody, "role": "CEX_CUSTODY", "confidence": 0.95}])
    out = h.analyze({"chain": "BSC", "token": "0x123", "pair_address": pair, "deployment_block": 1})
    assert out["status"] == "PASS"
    assert out["cex_custody_pct"] == 42.0
    assert "CEX_CUSTODY_SUPPLY_GE_30PCT_MONITOR_FLOW" in out["reasons"]


def test_fomobag_pons_locker_is_excluded_but_unknown_wallets_remain_counted():
    locker = "0x267444D099b10fB5Ed7c3Cc7B7c767AdcA574952"
    registry = [{"chain": "ROBINHOOD", "address": locker, "role": "LOCKED_VAULT", "label": "Pons V2 Launch Locker", "confidence": 1.0}]
    holders = [{"owner": locker, "pct": 8.16}] + _holders(7.0, 6.0, 5.0, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.8)
    d = h._role_aware_distribution("ROBINHOOD", holders, registry=registry)
    assert round(d["gross_top1_pct"], 2) == 8.16
    assert round(d["locked_vault_pct"], 2) == 8.16
    assert d["adjusted_top1_pct"] == 7.0
    assert d["holders"][1]["holder_role"] == "UNKNOWN"
    assert d["holders"][1]["excluded_from_whale_concentration"] is False


def test_fomobag_locker_role_is_chain_scoped():
    locker = "0x267444D099b10fB5Ed7c3Cc7B7c767AdcA574952"
    registry = [{"chain": "ROBINHOOD", "address": locker, "role": "LOCKED_VAULT", "confidence": 1.0}]
    on_robinhood = h._role_aware_distribution("ROBINHOOD", [{"owner": locker, "pct": 8.16}], registry=registry)
    on_ethereum = h._role_aware_distribution("ETHEREUM", [{"owner": locker, "pct": 8.16}], registry=registry)
    assert on_robinhood["known_infrastructure_pct"] == 8.16
    assert on_ethereum["known_infrastructure_pct"] == 0
    assert on_ethereum["adjusted_top1_pct"] == 8.16


def test_robinhood_is_supported_as_evm_and_uses_adjusted_real_concentration(monkeypatch):
    locker = "0x267444D099b10fB5Ed7c3Cc7B7c767AdcA574952"
    holders = [{"owner": locker, "pct": 30.0}] + _holders(9, 8, 7, 6, 5, 4, 3, 2, 1.5, 1.0, 0.5)
    monkeypatch.setattr(h, "_evm_holders", lambda chain, token, row: (holders, [], [], {"complete": True, "reason": "FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK"}))
    monkeypatch.setattr(h, "_role_registry", lambda: [{"chain": "ROBINHOOD", "address": locker, "role": "LOCKED_VAULT", "confidence": 1.0}])
    monkeypatch.setattr(h, "verify_evm_deployer", lambda rpc, token, row: {"verified": False, "reason": "NOT_REQUIRED_FOR_CASE"})
    monkeypatch.setattr(h, "verified_native_funding_edges", lambda row: [])
    out = h.analyze({"chain": "robinhood", "token": "0x776357e4295564828ca013ebc601d85ade708f3f", "deployment_block": 1})
    assert out["status"] == "PASS"
    assert out["gross_top1_pct"] == 30.0
    assert out["locked_vault_pct"] == 30.0
    assert out["adjusted_real_top1_pct"] == 9.0
    assert "UNSUPPORTED_CHAIN" not in out["reasons"]
