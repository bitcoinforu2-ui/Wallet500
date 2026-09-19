from scripts import free_intelligence_collector as free


def _token():
    return {
        "symbol": "ISLAND",
        "network": "ethereum",
        "contract": "0x157a6df6b74f4e5e45af4e4615fde7b49225a662",
        "pair": "0xd96d4a6720d8bb68e045ae7af09b7668075d26e8268b0f272a5dc6e7de91cc63",
    }


def test_honeypot_first_observation_is_warning_not_hard_risk(monkeypatch):
    urls = []

    def fake_get(url, headers=None, timeout=12):
        urls.append(url)
        return {
            "honeypotResult": {"isHoneypot": True},
            "simulationResult": {"buyTax": 0, "sellTax": 0},
        }

    monkeypatch.setattr(free, "get_json", fake_get)
    events, snap = free.honeypot(_token(), {}, with_snapshot=True)

    assert "chainID=1" in urls[0]
    assert snap["is_honeypot"] is True
    assert snap["confirmed_hard_risk"] is False
    assert events[0]["kind"] == "honeypot_or_transfer_block_unconfirmed"
    assert events[0]["hard_risk"] is False


def test_honeypot_second_consecutive_observation_confirms_hard_risk(monkeypatch):
    monkeypatch.setattr(
        free,
        "get_json",
        lambda url, headers=None, timeout=12: {
            "honeypotResult": {"isHoneypot": True},
            "simulationResult": {"buyTax": 0, "sellTax": 0},
        },
    )
    first_events, first = free.honeypot(_token(), {}, with_snapshot=True)
    second_events, second = free.honeypot(_token(), first, with_snapshot=True)

    assert first_events[0]["hard_risk"] is False
    assert second["confirmed_hard_risk"] is True
    hard = [e for e in second_events if e["kind"] == "honeypot_or_transfer_block"]
    assert hard and hard[0]["hard_risk"] is True
