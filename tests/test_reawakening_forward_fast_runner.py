import wallet500.reawakening_forward_fast_runner as fast


PAIR = "0x9793a9cbb04f781433254e4530398107e6a8dcee"


def test_single_attempt_pair_lookup_calls_http_once_and_matches_evm_case(monkeypatch):
    calls = []

    def fake_get(path, timeout=20):
        calls.append((path, timeout))
        return {"pairs": [{"pairAddress": PAIR.upper(), "dexId": "x"}]}

    monkeypatch.setattr(fast, "_get", fake_get)
    row = fast.single_attempt_pair_lookup("bsc", PAIR)
    assert row is not None
    assert row["pairAddress"] == PAIR.upper()
    assert len(calls) == 1
    assert calls[0][1] == fast.DIRECT_TIMEOUT_SECONDS


def test_single_attempt_pair_lookup_fails_closed_without_retry(monkeypatch):
    calls = []

    def failing_get(path, timeout=20):
        calls.append((path, timeout))
        raise TimeoutError("transient")

    monkeypatch.setattr(fast, "_get", failing_get)
    assert fast.single_attempt_pair_lookup("solana", "ExactCasePair") is None
    assert len(calls) == 1


def test_solana_pair_match_is_case_sensitive(monkeypatch):
    monkeypatch.setattr(
        fast,
        "_get",
        lambda path, timeout=20: {"pairs": [{"pairAddress": "abc"}]},
    )
    assert fast.single_attempt_pair_lookup("solana", "ABC") is None
