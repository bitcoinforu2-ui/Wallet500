from scripts import derivatives_intelligence_collector as d


def test_gate_contract_catalog_uses_supported_unpaginated_endpoint(monkeypatch):
    seen = []

    def fake_jget(url, cache_ttl=45, attempts=4):
        seen.append(url)
        return [{
            "name": "TEST_USDT",
            "in_delisting": False,
            "mark_price": "1.0",
            "funding_rate": "0.0001",
        }]

    monkeypatch.setattr(d, "jget", fake_jget)
    out = d.gate_contract_catalog()
    assert "TEST" in out
    assert seen == ["https://api.gateio.ws/api/v4/futures/usdt/contracts"]
    assert "limit=" not in seen[0]
    assert "offset=" not in seen[0]


def test_futures_radar_mapping_is_explicit():
    assert d.target_is_futures_radar({"futures_early_radar": True}) is True
    assert d.target_is_futures_radar({"source": "Gate Futures Early Radar"}) is True
    assert d.target_is_futures_radar({"source": "Gate Spot"}) is False
