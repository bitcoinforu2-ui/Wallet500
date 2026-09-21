from __future__ import annotations

from scripts import protocol_value_accrual_discovery as scout


def test_unmapped_high_value_accrual_stays_non_actionable():
    raw = {
        "slug": "new-protocol",
        "name": "New Protocol",
        "total24h": 500_000,
        "total7d": 1_400_000,
        "total30d": 3_000_000,
    }
    scored = scout.score_row(raw)
    assert scored is not None
    assert scored["discovery_score"] >= 25

    enriched = scout.enrich_mapping(scored, {})
    assert enriched["registry_mapped"] is False
    assert enriched["identity_verified"] is False
    assert enriched["actionable"] is False
    assert enriched["direct_buy_eligible"] is False
    assert enriched["telegram_eligible"] is False
    assert enriched["status"] == "MECHANISM_AND_EXACT_IDENTITY_REQUIRED"


def test_mapping_uses_exact_declared_slug_not_symbol_or_name():
    registry = {
        "entries": [{
            "active": True,
            "id": "foo-token",
            "protocol_name": "Foo Protocol",
            "symbol": "FOO",
            "network": "ethereum",
            "contract": "0x1111111111111111111111111111111111111111",
            "pair": "0x2222222222222222222222222222222222222222",
            "defillama_slug": "foo-protocol",
            "buyback_sensor": {
                "enabled": True,
                "execution_sources": [{
                    "adapter": "json_daily_series",
                    "name": "Foo Buybacks",
                    "url": "https://example.test/foo",
                    "execution_proof": True,
                    "semantics": "VERIFIED_BUYBACK",
                }],
            },
        }]
    }
    mapping = scout.registry_slug_index(registry)

    exact = scout.enrich_mapping(
        {
            "slug": "foo-protocol",
            "name": "Anything",
            "discovery_score": 50,
            "holder_value_24h_usd": 100_000,
        },
        mapping,
    )
    ticker_like = scout.enrich_mapping(
        {
            "slug": "foo",
            "name": "Foo Protocol",
            "discovery_score": 50,
            "holder_value_24h_usd": 100_000,
        },
        mapping,
    )

    assert exact["registry_mapped"] is True
    assert exact["identity_verified"] is True
    assert exact["status"] == "MAPPED_TO_BUYBACK_RADAR"
    assert ticker_like["registry_mapped"] is False
    assert ticker_like["status"] == "MECHANISM_AND_EXACT_IDENTITY_REQUIRED"


def test_overview_rows_supports_list_and_mapping_shapes():
    as_list = {"protocols": [{"slug": "a", "total24h": 1}]}
    as_map = {"protocols": {"b": {"total24h": 2}}}

    rows1 = scout.overview_rows(as_list)
    rows2 = scout.overview_rows(as_map)

    assert rows1[0]["slug"] == "a"
    assert rows2[0]["slug"] == "b"


def test_small_non_accelerating_value_accrual_is_filtered_out():
    raw = {
        "slug": "quiet",
        "total24h": 1_000,
        "total7d": 7_000,
        "total30d": 30_000,
    }
    assert scout.score_row(raw) is None
