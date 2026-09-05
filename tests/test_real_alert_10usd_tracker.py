from wallet500.real_alert_10usd_tracker import initial_ledger, reconcile


def _real():
    return {
        "alerts": [
            {
                "status": "REAL_ALERT",
                "symbol": "ARC",
                "chain": "solana",
                "token_address": "TOKEN1",
                "pair_address": "PAIR1",
                "price_usd": 2.0,
                "execution_pool_liquidity_usd": 100000,
                "dex_url": "https://dexscreener.com/solana/PAIR1",
                "first_alert_at": "2026-09-05T14:59:30+00:00",
                "score": 77.5,
                "market_age_days": 420,
                "source_lanes": ["REVIVAL_PRECURSOR", "ACTIVE_PRODUCTION_GATE"],
                "evidence_envelope_status": "EVIDENCE_READY",
                "evidence_positive_lanes": ["VERIFIED_SOCIAL"],
                "evidence_verified_lanes": ["SMART_MONEY", "VERIFIED_SOCIAL"],
            }
        ]
    }


def _report(delivered=True, sent_at="2026-09-05T15:00:00+00:00"):
    return {
        "delivered": [
            {
                "key": "solana:TOKEN1:PAIR1",
                "symbol": "ARC",
                "pair_address": "PAIR1",
                "sent_at": sent_at,
                "sent_at_israel": "05/09/2026 18:00:00",
                "dex_url": "https://dexscreener.com/solana/PAIR1",
            }
        ] if delivered else []
    }


def _quote(_chain, _pair):
    return {"pairAddress": "PAIR1", "priceUsd": "2.0", "liquidity": {"usd": 100000}}


def _quote_up(_chain, _pair):
    return {"pairAddress": "PAIR1", "priceUsd": "3.0", "liquidity": {"usd": 110000}}


def _quote_missing(_chain, _pair):
    return None


def test_no_backfill_without_current_telegram_delivery():
    ledger, summary = reconcile(
        initial_ledger("2026-09-05T15:00:01+00:00"),
        _report(False),
        _real(),
        now="2026-09-05T15:00:02+00:00",
        quote_fn=_quote,
    )
    assert ledger["positions"] == []
    assert summary["positions_total"] == 0


def test_pre_activation_delivery_is_never_backfilled():
    ledger, summary = reconcile(
        initial_ledger("2026-09-05T15:00:01+00:00"),
        _report(True, sent_at="2026-09-05T14:40:00+00:00"),
        _real(),
        now="2026-09-05T15:00:02+00:00",
        quote_fn=_quote,
    )
    assert ledger["positions"] == []
    assert summary["positions_total"] == 0


def test_new_delivered_real_alert_creates_exactly_ten_dollar_paper_position():
    ledger, summary = reconcile(
        initial_ledger("2026-09-05T15:00:01+00:00"),
        _report(True),
        _real(),
        now="2026-09-05T15:00:02+00:00",
        quote_fn=_quote,
    )
    assert summary["positions_total"] == 1
    p = ledger["positions"][0]
    assert p["cost_usd"] == 10.0
    assert p["quantity"] == 5.0
    assert p["entry_price_usd"] == 2.0
    assert p["telegram_sent_at_israel"] == "05/09/2026 18:00:00"
    assert p["paper_only"] is True
    assert p["alert_event_id"]
    assert p["entry_score"] == 77.5
    assert p["entry_market_age_days"] == 420
    assert p["entry_verified_evidence"] == ["SMART_MONEY", "VERIFIED_SOCIAL"]
    assert p["checkpoints"] == {}


def test_existing_position_is_not_bought_again_marks_performance_and_captures_horizons_once():
    ledger, _ = reconcile(
        initial_ledger("2026-09-05T15:00:01+00:00"),
        _report(True),
        _real(),
        now="2026-09-05T15:00:02+00:00",
        quote_fn=_quote,
    )
    ledger2, summary2 = reconcile(
        ledger,
        _report(True),
        _real(),
        now="2026-09-05T16:00:02+00:00",
        quote_fn=_quote_up,
    )
    assert len(ledger2["positions"]) == 1
    p = ledger2["positions"][0]
    assert p["current_value_usd"] == 15.0
    assert p["current_return_pct"] == 50.0
    assert p["current_multiple"] == 1.5
    assert p["peak_return_pct"] == 50.0
    assert p["drawdown_from_peak_pct"] == 0.0
    assert set(p["checkpoints"]) == {"15m", "1h"}
    assert p["checkpoints"]["1h"]["return_pct"] == 50.0
    assert p["checkpoints"]["1h"]["capture_rule"] == "FIRST_OBSERVED_EXACT_PAIR_MARK_AT_OR_AFTER_HORIZON"
    assert summary2["roi_pct"] == 50.0
    assert summary2["positions_peak_ge_50pct"] == 1
    assert summary2["positions_peak_ge_100pct"] == 0

    ledger3, _ = reconcile(
        ledger2,
        _report(True),
        _real(),
        now="2026-09-05T16:10:02+00:00",
        quote_fn=_quote_up,
    )
    assert len(ledger3["positions"][0]["checkpoints"]) == 2


def test_missing_exact_pair_mark_is_counted_without_fabricating_price():
    ledger, _ = reconcile(
        initial_ledger("2026-09-05T15:00:01+00:00"),
        _report(True),
        _real(),
        now="2026-09-05T15:00:02+00:00",
        quote_fn=_quote,
    )
    before = ledger["positions"][0]["current_price_usd"]
    ledger2, _ = reconcile(
        ledger,
        _report(False),
        _real(),
        now="2026-09-05T15:20:02+00:00",
        quote_fn=_quote_missing,
    )
    p = ledger2["positions"][0]
    assert p["current_price_usd"] == before
    assert p["missed_mark_count"] == 1
