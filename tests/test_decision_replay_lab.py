from wallet500.decision_replay_lab import build


def _source(price=1.0, event_at="2026-09-13T00:00:00+00:00"):
    return {
        "records": {
            "SHADOW|solana|TOKEN|PAIR": {
                "lane": "NEAR_ALERT_SHADOW",
                "chain": "solana",
                "token_address": "TOKEN",
                "pair_address": "PAIR",
                "event_at": event_at,
                "entry_price_usd": price,
                "decision_snapshot": {
                    "identity": {"chain": "solana", "token": "TOKEN", "pair_address": "PAIR"},
                    "entry": {
                        "observed_at": event_at,
                        "radar_tier": "NEAR_ALERT",
                        "entry_price_usd": price,
                        "readiness_passed": 6,
                        "readiness_total": 7,
                    },
                },
                "checkpoints": {},
            }
        }
    }


def test_key_includes_first_decision_timestamp():
    ledger, report = build(_source(), {})
    assert "solana|TOKEN|PAIR|2026-09-13T00:00:00+00:00" in ledger["records"]
    assert report["source_integrity"]["replay_key_includes_first_decision_timestamp"] is True
    assert report["guardrails"]["symbol_only_identity_forbidden"] is True


def test_existing_t0_is_never_overwritten_on_source_drift():
    ledger1, _ = build(_source(price=1.0), {})
    ledger2, report2 = build(_source(price=2.0), ledger1)
    rec = ledger2["records"]["solana|TOKEN|PAIR|2026-09-13T00:00:00+00:00"]
    assert rec["t0"]["price_usd"] == 1.0
    assert any(x["type"] == "IMMUTABLE_T0_MISMATCH_PRESERVED_OLD_VALUE" for x in report2["source_integrity"]["integrity_events"])


def test_same_pair_different_first_decision_times_are_distinct_records():
    first, _ = build(_source(event_at="2026-09-13T00:00:00+00:00"), {})
    second, _ = build(_source(event_at="2026-09-13T01:00:00+00:00"), first)
    assert len(second["records"]) == 2


def test_missing_exact_identity_is_rejected():
    bad = {"records": {"x": {"chain": "solana", "token_address": "TOKEN", "event_at": "2026-09-13T00:00:00+00:00"}}}
    ledger, report = build(bad, {})
    assert not ledger["records"]
    assert report["source_integrity"]["integrity_events"][0]["type"] == "REJECTED_INCOMPLETE_EXACT_IDENTITY"
