from datetime import datetime, timezone
from wallet500 import listing_opportunity_router as r

def test_future_exact_identity_routes_outside_revival(tmp_path, monkeypatch):
    monkeypatch.setattr(r,'DATA',tmp_path); monkeypatch.setattr(r,'WIRE',tmp_path/'wire.json'); monkeypatch.setattr(r,'LEDGER',tmp_path/'ledger.json'); monkeypatch.setattr(r,'OUT',tmp_path/'out.json')
    (tmp_path/'wire.json').write_text('{"events":[{"event_id":"1","event_type":"SPOT_LISTING_EXPECTED","symbol":"ABC","chain":"solana","contract":"MintABC","source_owner":"gate","source_url":"https://example.com","listing_start":"2026-09-11T12:00:00Z"}]}')
    (tmp_path/'ledger.json').write_text('{"events":{}}')
    d=r.run(datetime(2026,9,10,12,tzinfo=timezone.utc)); x=d['opportunities'][0]
    assert x['lane']=='PRE_LISTING_EXISTING_OR_NEW'; assert x['revival_age_gate_applies'] is False; assert x['telegram_candidate'] is True; assert x['automatic_buy'] is False

def test_symbol_only_is_identity_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(r,'DATA',tmp_path); monkeypatch.setattr(r,'WIRE',tmp_path/'wire.json'); monkeypatch.setattr(r,'LEDGER',tmp_path/'ledger.json'); monkeypatch.setattr(r,'OUT',tmp_path/'out.json')
    (tmp_path/'wire.json').write_text('{"events":[{"event_id":"1","event_type":"SPOT_LISTING_EXPECTED","symbol":"ABC","source_owner":"gate","source_url":"https://example.com","listing_start":"2026-09-11T12:00:00Z"}]}')
    (tmp_path/'ledger.json').write_text('{"events":{}}')
    x=r.run(datetime(2026,9,10,12,tzinfo=timezone.utc))['opportunities'][0]
    assert x['lane']=='IDENTITY_PENDING'; assert x['telegram_candidate'] is False
