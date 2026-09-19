from scripts import intelligence_fusion as fusion
from scripts import public_alpha_source_collector as alpha


SOL = "So11111111111111111111111111111111111111112"


def _telegram_html():
    return f"""
    <div data-post="CallAnalyserSol/100">
      <div class="tgme_widget_message_text">First call from:<br>⚡ Caller: Degen Seals<br>CA: {SOL}</div>
      <time datetime="2026-09-19T09:30:00+00:00"></time>
    </div>
    <div data-post="CallAnalyserSol/101">
      <div class="tgme_widget_message_text">⚡ Caller: Old Caller<br>CA: {SOL}</div>
      <time datetime="2026-09-19T07:00:00+00:00"></time>
    </div>
    """


def test_callanalyser_parser_preserves_original_timestamp_and_caller():
    source = {
        "id": "telegram_callanalyser_sol",
        "name": "Call Analyser SOL",
        "url": "https://t.me/s/CallAnalyserSol",
        "extract_raw_contracts": True,
        "parse_caller_from_text": True,
        "max_live_age_minutes": 45,
    }
    rows, health = alpha.telegram_discoveries(
        _telegram_html(), source, "2026-09-19T10:00:00+00:00"
    )
    recent = next(x for x in rows if x["source_post_id"] == "CallAnalyserSol:100")
    assert recent["caller"] == "Degen Seals"
    assert recent["called_at"] == "2026-09-19T09:30:00+00:00"
    assert recent["timestamp_semantics"] == "TELEGRAM_ORIGINAL_DATETIME"
    assert recent["live_eligible"] is True
    assert health["dropped_untimestamped"] == 0


def test_old_visible_telegram_call_is_historical_not_live():
    source = {
        "id": "telegram_callanalyser_sol",
        "name": "Call Analyser SOL",
        "url": "https://t.me/s/CallAnalyserSol",
        "extract_raw_contracts": True,
        "parse_caller_from_text": True,
        "max_live_age_minutes": 45,
    }
    rows, health = alpha.telegram_discoveries(
        _telegram_html(), source, "2026-09-19T10:00:00+00:00"
    )
    old = next(x for x in rows if x["source_post_id"] == "CallAnalyserSol:101")
    assert old["caller"] == "Old Caller"
    assert old["live_eligible"] is False
    assert health["stale_candidate_rows"] >= 1


def test_direct_and_aggregated_same_origin_share_fusion_fingerprint():
    identity = "solana:mint:pair"
    direct = {
        "independence_key": "alpha-origin:solana:mint:degen seals",
        "canonical_event_id": "direct:1",
    }
    aggregator = {
        "independence_key": "alpha-origin:solana:mint:degen seals",
        "canonical_event_id": "callanalyser:99",
    }
    assert fusion._fingerprint(direct, identity) == fusion._fingerprint(aggregator, identity)


def test_different_callers_remain_independent():
    identity = "solana:mint:pair"
    a = {"independence_key": "alpha-origin:solana:mint:caller a"}
    b = {"independence_key": "alpha-origin:solana:mint:caller b"}
    assert fusion._fingerprint(a, identity) != fusion._fingerprint(b, identity)


def test_evm_raw_address_does_not_fabricate_solana_candidate():
    source = {"extract_raw_contracts": True}
    evm = "0x49d4c84E35627F6AC9A9bC2684aEA3ABB41948CF"
    rows = alpha.extract_candidates(f"CA: {evm}", source)
    assert ("evm", evm) in rows
    assert not any(network == "solana" for network, _ in rows)
