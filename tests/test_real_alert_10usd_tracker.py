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
            }
        ]
    }


def _report(delivered=True):
    return {
        "delivered": [
            {
                "key": "solana:TOKEN1:PAIR1",
                "symbol": "ARC",
                "pair_address": "PAIR1",
                "sent_at": "2026-09-05T15:00:00+00:00",
                "sent_at_israel": "05/09/2026 18:00:00",
                "dex_url": "https://dexscreener.com/solana/PAIR1",
            }
        ] if delivered else []
    }


def _quote(_chain, _pair):
    return {"pairAddress": "PAIR1", "priceUsd": "2.0", "liquidity": {"usd": 100000}}


def _quote_up(_chain, _pair):
    return {"pairAddress": "PAIR1", "priceUsd": "3.0", "liquidity": {"usd": 110000}}


def test_no_backfill_without_current_telegram_delivery():
    ledger, summary = reconcile(initial_ledger("2026-09-05T15:00:01+00:00"), _report(False), _real(), now="2026-09-05T15:00:02+00:00", quote_fn=_quote)
    assert ledger["positions"] == []
    assert summary["positions_total"] == 0


def test_new_delivered_real_alert_creates_exactly_ten_dollar_paper_position():
    ledger, summary = reconcile(initial_ledger("2026-09-05T15:00:01+00:00"), _report(True), _real(), now="2026-09-05T15:00:02+00:00", quote_fn=_quote)
    assert summary["positions_total"] == 1
    p = ledger["positions"][0]
    assert p["cost_usd"] == 10.0
    assert p["quantity"] == 5.0
    assert p["entry_price_usd"] == 2.0
    assert p["telegram_sent_at_israel"] == "05/09/2026 18:00:00"
    assert p["paper_only"] is True


def test_existing_position_is_not_bought_again_and_marks_performance():
    ledger, _ = reconcile(initial_ledger("2026-09-05T15:00:01+00:00"), _report(True), _real(), now="2026-09-05T15:00:02+00:00", quote_fn=_quote)
    ledger2, summary2 = reconcile(ledger, _report(True), _real(), now="2026-09-05T16:00:02+00:00", quote_fn=_quote_up)
    assert len(ledger2["positions"]) == 1
    p = ledger2["positions"][0]
    assert p["current_value_usd"] == 15.0
    assert p["current_return_pct"] == 50.0
    assert p["peak_return_pct"] == 50.0
    assert summary2["roi_pct"] == 50.0
