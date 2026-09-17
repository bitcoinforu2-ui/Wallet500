from wallet500 import binance_web3_market as bwm


MINT = "3DmF2srrZX1d47W1x7JQn49yk6QwEWoJBNkRvJ3Ppump"


def test_dynamic_normalizes_public_market_fields(monkeypatch):
    monkeypatch.setattr(
        bwm,
        "_request_json",
        lambda *a, **k: {
            "code": "000000",
            "data": {
                "price": "0.001234",
                "liquidity": "98765.43",
                "volume24h": "543210.12",
                "holders": "1820",
                "marketCap": "2500000",
                "top10HoldersPercentage": "31.55",
            },
        },
    )
    row = bwm.fetch_dynamic("sol", MINT, observed_at="2026-09-17T18:00:00+00:00")
    assert row["chain"] == "solana"
    assert row["source"] == "binance_web3"
    assert row["market_scope"] == "token_aggregate"
    assert row["price_usd"] == 0.001234
    assert row["liquidity_usd"] == 98765.43
    assert row["volume_24h_usd"] == 543210.12
    assert row["holders"] == 1820
    assert row["market_cap_usd"] == 2500000
    assert row["top10_pct"] == 31.55


def test_missing_optional_metric_stays_none_not_zero(monkeypatch):
    monkeypatch.setattr(
        bwm,
        "_request_json",
        lambda *a, **k: {"code": "000000", "data": {"price": "0.1", "holders": "12"}},
    )
    row = bwm.fetch_dynamic("solana", MINT, observed_at="2026-09-17T18:00:00+00:00")
    assert row["liquidity_usd"] is None
    assert row["top10_pct"] is None


def test_audit_only_emits_hit_flags(monkeypatch):
    monkeypatch.setattr(
        bwm,
        "_request_json",
        lambda *a, **k: {
            "code": "000000",
            "data": {
                "hasResult": True,
                "isSupported": True,
                "riskLevel": 2,
                "riskLevelEnum": "MEDIUM",
                "extraInfo": {"buyTax": "1.5", "sellTax": "2.0", "isVerified": True},
                "riskItems": [
                    {
                        "id": "CONTRACT_RISK",
                        "details": [
                            {"title": "Mint authority present", "isHit": True, "riskType": "CAUTION"},
                            {"title": "Honeypot", "isHit": False, "riskType": "RISK"},
                        ],
                    }
                ],
            },
        },
    )
    audit = bwm.fetch_audit("solana", MINT)
    assert audit["available"] is True
    assert audit["risk_level_enum"] == "MEDIUM"
    assert audit["risk_flags"] == ["BINANCE_AUDIT_CAUTION:Mint authority present"]


def test_unsupported_audit_is_not_treated_as_clean(monkeypatch):
    monkeypatch.setattr(
        bwm,
        "_request_json",
        lambda *a, **k: {"code": "000000", "data": {"hasResult": False, "isSupported": False}},
    )
    audit = bwm.fetch_audit("solana", MINT)
    assert audit["available"] is False
    assert audit["risk_level"] is None
    assert audit["risk_flags"] == []


def test_refresh_preserves_other_providers_and_replaces_binance(monkeypatch):
    correlation = {
        "assets": {
            f"solana:{MINT}": {
                "chain": "solana",
                "token": MINT,
                "identity_confidence": "EXACT_CHAIN_CONTRACT",
                "source_confirmation_count": 3,
                "last_seen_any_source_at": "2026-09-17T17:59:00+00:00",
            }
        }
    }
    existing = {
        "snapshots": [
            {
                "chain": "solana",
                "token": MINT,
                "source": "provider_a",
                "observed_at": "2026-09-17T17:59:00+00:00",
                "price_usd": 0.001,
                "market_scope": "token_aggregate",
            },
            {
                "chain": "solana",
                "token": MINT,
                "source": "binance_web3",
                "observed_at": "2026-09-17T17:00:00+00:00",
                "price_usd": 0.0005,
                "market_scope": "token_aggregate",
            },
        ]
    }
    monkeypatch.setattr(
        bwm,
        "fetch_dynamic",
        lambda chain, token, observed_at=None: {
            "chain": chain,
            "token": token,
            "source": "binance_web3",
            "role": "verifier",
            "observed_at": observed_at,
            "market_scope": "token_aggregate",
            "price_usd": 0.00101,
        },
    )
    payload, status = bwm.refresh(
        correlation=correlation,
        existing=existing,
        max_assets=10,
        request_delay_seconds=0,
    )
    rows = payload["snapshots"]
    assert len(rows) == 2
    assert any(r["source"] == "provider_a" for r in rows)
    binance = next(r for r in rows if r["source"] == "binance_web3")
    assert binance["price_usd"] == 0.00101
    assert status["successful_assets"] == 1
    assert status["automatic_trade"] is False


def test_provider_failure_keeps_old_row_for_freshness_logic(monkeypatch):
    correlation = {
        "assets": {
            f"solana:{MINT}": {
                "chain": "solana",
                "token": MINT,
                "identity_confidence": "EXACT_CHAIN_CONTRACT",
            }
        }
    }
    existing = {
        "snapshots": [
            {
                "chain": "solana",
                "token": MINT,
                "source": "binance_web3",
                "observed_at": "2026-09-17T17:00:00+00:00",
                "price_usd": 0.0005,
            }
        ]
    }

    def fail(*args, **kwargs):
        raise bwm.ProviderError("temporary failure")

    monkeypatch.setattr(bwm, "fetch_dynamic", fail)
    payload, status = bwm.refresh(
        correlation=correlation,
        existing=existing,
        max_assets=10,
        request_delay_seconds=0,
    )
    assert payload["snapshots"][0]["price_usd"] == 0.0005
    assert status["failed_assets"] == 1
