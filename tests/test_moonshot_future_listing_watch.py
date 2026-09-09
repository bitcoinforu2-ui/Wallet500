import json
from datetime import datetime, timezone

from wallet500 import moonshot_future_listing_watch as fw


MINT = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
NOW = datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _future_event():
    return {
        "event_id": fw._event_key(MINT),
        "event_type": "MOONSHOT_FUTURE_LISTING",
        "chain": "solana",
        "token": MINT,
        "symbol": "TEST",
        "source_owner": "moonshot",
        "source_kind": "OFFICIAL_MOONSHOT_FUTURE_LISTING",
        "source_url": "https://x.com/moonshot/status/123",
        "surface": "official_x_api",
        "post_id": "123",
        "published_at": "2026-09-09T15:00:00+00:00",
        "first_seen_at": "2026-09-09T15:00:00+00:00",
        "last_seen_at": "2026-09-09T15:00:00+00:00",
        "catalyst_priority_score": 100,
    }


def _canonical_alert():
    return {
        "status": "REAL_ALERT",
        "actionable_research_alert": True,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "chain": "solana",
        "token_address": MINT,
        "pair_address": "PAIR123",
        "blockers": [],
        "score": 91,
        "first_alert_at": "2026-09-09T15:30:00+00:00",
        "dex_url": "https://dexscreener.com/solana/PAIR123",
    }


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "DATA", tmp_path)
    monkeypatch.setattr(fw, "LEDGER_PATH", tmp_path / "moonshot-future-listing-ledger.json")
    monkeypatch.setattr(fw, "LATEST_PATH", tmp_path / "moonshot-future-listing-latest.json")
    monkeypatch.setattr(fw, "STATE_PATH", tmp_path / "moonshot-future-listing-state.json")
    monkeypatch.setattr(fw, "REAL_ALERTS_PATH", tmp_path / "real-alerts.json")
    monkeypatch.setattr(fw, "VERIFICATION_LEDGER_PATH", tmp_path / "moonshot-verification-ledger.json")
    monkeypatch.setattr(fw, "EXTERNAL_ALPHA_PATH", tmp_path / "external-alpha-events.json")


def test_future_language_requires_explicit_future_moonshot_context():
    assert fw.is_future_listing_text("🚀 $TEST will be listed on Moonshot soon. Contract Address: " + MINT)
    assert fw.is_future_listing_text("$TEST is coming to Moonshot! " + MINT)
    assert not fw.is_future_listing_text("$TEST is now verified on Moonshot. " + MINT)
    assert not fw.is_future_listing_text("$TEST is listing soon on another platform. " + MINT)


def test_syndication_requires_official_author_and_exact_mint():
    payload = {
        "props": {
            "pageProps": {
                "profile": {"screen_name": "moonshot", "id_str": "42"},
                "timeline": {
                    "entries": [
                        {
                            "id_str": "100",
                            "user_id_str": "42",
                            "created_at": "2026-09-09T15:00:00Z",
                            "full_text": f"🚀 $TEST is coming to Moonshot! Contract Address: {MINT}",
                        },
                        {
                            "id_str": "101",
                            "user_id_str": "42",
                            "created_at": "2026-09-09T15:01:00Z",
                            "full_text": "🚀 $NOCA is coming to Moonshot!",
                        },
                        {
                            "id_str": "102",
                            "user_id_str": "999",
                            "created_at": "2026-09-09T15:02:00Z",
                            "full_text": f"$FAKE is coming to Moonshot! Contract Address: {MINT}",
                        },
                        {
                            "id_str": "103",
                            "user_id_str": "42",
                            "created_at": "2026-09-09T15:03:00Z",
                            "full_text": f"$TEST is now verified on Moonshot. Contract Address: {MINT}",
                        },
                    ]
                },
            }
        }
    }
    page = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"
    exact, unresolved = fw.parse_x_syndication(page, NOW)
    assert len(exact) == 1
    assert exact[0]["token"] == MINT
    assert exact[0]["source_owner"] == "moonshot"
    assert exact[0]["catalyst_priority_score"] == 100
    assert len(unresolved) == 1
    assert unresolved[0]["symbol"] == "NOCA"


def test_canonical_gate_reuses_real_alert_truth_without_local_thresholds(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    _write(fw.REAL_ALERTS_PATH, {
        "truth_contract": {
            "minimum_market_age_days": 180,
            "minimum_execution_pool_liquidity_usd": 50000.0,
        },
        "alerts": [_canonical_alert()],
    })
    ok, row, truth = fw._canonical_real_alert(MINT)
    assert ok is True
    assert row["pair_address"] == "PAIR123"
    assert truth["minimum_market_age_days"] == 180
    assert truth["minimum_execution_pool_liquidity_usd"] == 50000.0

    bad = _canonical_alert()
    bad["status"] = "VERIFIED_WATCH_NOT_REAL_ALERT"
    _write(fw.REAL_ALERTS_PATH, {"truth_contract": {}, "alerts": [bad]})
    assert fw._canonical_real_alert(MINT)[0] is False


def test_existing_future_event_sends_later_when_canonical_gate_turns_real_alert(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    event = _future_event()
    _write(fw.LEDGER_PATH, {"version": 1, "events": {event["event_id"]: event}})
    _write(fw.STATE_PATH, {"version": 1, "alerted": {}})
    _write(fw.REAL_ALERTS_PATH, {"truth_contract": {"minimum_market_age_days": 180}, "alerts": [_canonical_alert()]})
    _write(fw.VERIFICATION_LEDGER_PATH, {"events": {}})
    _write(fw.EXTERNAL_ALPHA_PATH, {"version": 1, "events": []})

    monkeypatch.setattr(fw, "collect_official_sources", lambda reference=None: ([], [], [{"provider": "test", "status": "OK_TEST"}]))
    monkeypatch.setattr(fw, "_market", lambda token: ({
        "pair_identity_locked": True,
        "pair_address": "PAIR123",
        "liquidity_usd": 75000.0,
        "price_usd": 0.0123,
        "symbol": "TEST",
        "dex_url": "https://dexscreener.com/solana/PAIR123",
    }, "OK"))
    sent = []
    monkeypatch.setattr(fw, "_telegram_send", lambda text: (sent.append(text) or True, "SENT"))

    out = fw.run(NOW)
    assert out["counts"]["telegram_delivered"] == 1
    assert len(sent) == 1
    assert "MOONSHOT FUTURE LISTING" in sent[0]
    assert "Canonical Wallet500 REAL ALERT: PASS" in sent[0]

    # Idempotent on the next scan.
    out2 = fw.run(NOW)
    assert out2["counts"]["telegram_delivered"] == 0
    assert len(sent) == 1


def test_completed_moonshot_verification_suppresses_future_listing_telegram(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    event = _future_event()
    _write(fw.LEDGER_PATH, {"version": 1, "events": {event["event_id"]: event}})
    _write(fw.STATE_PATH, {"version": 1, "alerted": {}})
    _write(fw.REAL_ALERTS_PATH, {"truth_contract": {}, "alerts": [_canonical_alert()]})
    _write(fw.VERIFICATION_LEDGER_PATH, {
        "events": {
            "v": {
                "event_type": "MOONSHOT_VERIFIED",
                "source_owner": "moonshot",
                "token": MINT,
            }
        }
    })
    _write(fw.EXTERNAL_ALPHA_PATH, {"version": 1, "events": []})
    monkeypatch.setattr(fw, "collect_official_sources", lambda reference=None: ([], [], [{"provider": "test", "status": "OK_TEST"}]))
    monkeypatch.setattr(fw, "_market", lambda token: ({"pair_identity_locked": True, "pair_address": "PAIR123"}, "OK"))
    sent = []
    monkeypatch.setattr(fw, "_telegram_send", lambda text: (sent.append(text) or True, "SENT"))

    out = fw.run(NOW)
    assert out["events"][0]["phase"] == "LISTED_OR_VERIFIED_ON_MOONSHOT"
    assert out["events"][0]["telegram_eligible"] is False
    assert sent == []


def test_external_alpha_is_research_only_even_when_wallet500_passes(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    _write(fw.EXTERNAL_ALPHA_PATH, {"version": 1, "events": []})
    event = _future_event()
    event["phase"] = "FUTURE_LISTING_PENDING"
    event["market"] = {"pair_address": "PAIR123", "liquidity_usd": 75000.0}
    event["wallet500_gate"] = {"pass": True}
    count = fw._merge_external_alpha([event])
    assert count == 1
    payload = json.loads(fw.EXTERNAL_ALPHA_PATH.read_text())
    row = payload["events"][0]
    assert row["event_type"] == "MOONSHOT_FUTURE_LISTING"
    assert row["wallet500_real_alert_pass"] is True
    assert row["research_only_until_wallet500_gates_pass"] is True
    assert row["automatic_buy"] is False
