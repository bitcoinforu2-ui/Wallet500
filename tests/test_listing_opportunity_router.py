from datetime import datetime, timezone
from wallet500 import listing_opportunity_router as r


def _paths(tmp_path, monkeypatch):
    monkeypatch.setattr(r,'DATA',tmp_path)
    monkeypatch.setattr(r,'WIRE',tmp_path/'wire.json')
    monkeypatch.setattr(r,'LEDGER',tmp_path/'ledger.json')
    monkeypatch.setattr(r,'OUT',tmp_path/'out.json')


def test_future_exact_forward_identity_can_alert(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    (tmp_path/'wire.json').write_text('{"events":[{"event_id":"1","event_type":"SPOT_LISTING_EXPECTED","symbol":"ABC","chain":"solana","contract":"MintABC","source_owner":"gate","source_url":"https://example.com","listing_start":"2026-09-11T12:00:00Z","forward_new":true}]}')
    (tmp_path/'ledger.json').write_text('{"events":{}}')
    x=r.run(datetime(2026,9,10,12,tzinfo=timezone.utc))['opportunities'][0]
    assert x['lane']=='PRE_LISTING_EXISTING_OR_NEW'
    assert x['revival_age_gate_applies'] is False
    assert x['telegram_candidate'] is True
    assert x['automatic_buy'] is False


def test_symbol_only_is_identity_pending_and_never_alerts(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    (tmp_path/'wire.json').write_text('{"events":[{"event_id":"1","event_type":"SPOT_LISTING_EXPECTED","symbol":"ABC","source_owner":"gate","source_url":"https://example.com","listing_start":"2026-09-11T12:00:00Z","forward_new":true}]}')
    (tmp_path/'ledger.json').write_text('{"events":{}}')
    x=r.run(datetime(2026,9,10,12,tzinfo=timezone.utc))['opportunities'][0]
    assert x['lane']=='IDENTITY_PENDING'
    assert x['telegram_candidate'] is False


def test_historical_ledger_event_never_alerts_even_if_listing_metadata_exists(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    (tmp_path/'wire.json').write_text('{"events":[]}')
    (tmp_path/'ledger.json').write_text('{"events":{"old":{"event":{"event_id":"old","event_type":"FUTURES_LISTING","symbol":"OLD","chain":"solana","contract":"MintOld","source_owner":"mexc","source_url":"https://example.com/old","listing_start":"2025-05-12T05:50:00Z"}}}}')
    x=r.run(datetime(2026,9,10,12,tzinfo=timezone.utc))['opportunities'][0]
    assert x['lane']=='HISTORICAL_RESEARCH_ONLY'
    assert x['telegram_candidate'] is False
    assert x['telegram_blocker']=='NOT_CURRENT_WIRE'


def test_current_non_forward_backfill_never_alerts(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    (tmp_path/'wire.json').write_text('{"events":[{"event_id":"1","event_type":"SPOT_LISTING_EXPECTED","symbol":"ABC","chain":"solana","contract":"MintABC","source_owner":"gate","source_url":"https://example.com","listing_start":"2026-09-11T12:00:00Z","forward_new":false}]}')
    (tmp_path/'ledger.json').write_text('{"events":{}}')
    x=r.run(datetime(2026,9,10,12,tzinfo=timezone.utc))['opportunities'][0]
    assert x['telegram_candidate'] is False
    assert x['telegram_blocker']=='NOT_FORWARD_NEW'
