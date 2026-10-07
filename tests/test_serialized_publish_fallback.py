from scripts import serialized_publish


def test_lock_timeout_can_fall_back_to_atomic_cas(monkeypatch):
    calls = {"atomic": 0}

    monkeypatch.setenv("WALLET500_SERIALIZED_PUBLISH_FALLBACK_DIRECT", "1")
    monkeypatch.setattr(serialized_publish, "_expand_directory_payloads", lambda: None)
    monkeypatch.setattr(serialized_publish, "_route_unsafe_large_transports_to_direct_git", lambda: None)

    def timeout():
        raise RuntimeError("SERIALIZED_PUBLISH_LOCK_TIMEOUT wait_seconds=210")

    def atomic_main():
        calls["atomic"] += 1
        return 0

    monkeypatch.setattr(serialized_publish, "acquire_lock", timeout)
    monkeypatch.setattr(serialized_publish.atomic_publish, "main", atomic_main)

    assert serialized_publish.main() == 0
    assert calls["atomic"] == 1


def test_lock_timeout_stays_fail_closed_without_explicit_fallback(monkeypatch):
    monkeypatch.delenv("WALLET500_SERIALIZED_PUBLISH_FALLBACK_DIRECT", raising=False)
    monkeypatch.setattr(serialized_publish, "_expand_directory_payloads", lambda: None)
    monkeypatch.setattr(serialized_publish, "_route_unsafe_large_transports_to_direct_git", lambda: None)

    def timeout():
        raise RuntimeError("SERIALIZED_PUBLISH_LOCK_TIMEOUT wait_seconds=210")

    monkeypatch.setattr(serialized_publish, "acquire_lock", timeout)

    try:
        serialized_publish.main()
        assert False, "expected lock timeout"
    except RuntimeError as exc:
        assert "SERIALIZED_PUBLISH_LOCK_TIMEOUT" in str(exc)
