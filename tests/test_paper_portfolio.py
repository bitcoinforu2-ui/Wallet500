from wallet500.paper_portfolio import initial_ledger, reconcile_portfolio


def candidate(price=1.0, liquidity=60000.0):
    return {
        "chain": "bsc",
        "token": "0xABC",
        "pair_address": "0xPAIR",
        "price_usd": price,
        "liquidity_usd": liquidity,
        "holder_cluster_production_status": "PASS",
        "holder_cluster_verification_complete": True,
        "anomaly_score": 90,
    }


def test_buy_mark_and_sell_realizes_loss():
    ledger = initial_ledger("2026-08-29T00:00:00+00:00")
    row = candidate(price=2.0)
    ledger, summary = reconcile_portfolio(ledger, [row], {}, "2026-08-29T00:01:00+00:00")
    assert summary["cash_usd"] == 99.0
    assert summary["open_positions"] == 1
    assert summary["total_equity_usd"] == 100.0

    quote = candidate(price=1.0)
    key = "bsc|0xabc|0xpair"
    ledger, summary = reconcile_portfolio(ledger, [], {key: quote}, "2026-08-29T00:02:00+00:00")
    assert summary["open_positions"] == 0
    assert summary["closed_positions"] == 1
    assert summary["realized_pnl_usd"] == -0.5
    assert summary["cash_usd"] == 99.5
    assert summary["total_equity_usd"] == 99.5
    assert summary["closed_losses"] == 1


def test_never_opens_below_liquidity_floor():
    ledger = initial_ledger("2026-08-29T00:00:00+00:00")
    ledger, summary = reconcile_portfolio(ledger, [candidate(liquidity=49999.99)], {}, "2026-08-29T00:01:00+00:00")
    assert summary["open_positions"] == 0
    assert summary["cash_usd"] == 100.0


def test_unverified_exit_is_not_fabricated():
    ledger = initial_ledger("2026-08-29T00:00:00+00:00")
    row = candidate(price=2.0)
    ledger, _ = reconcile_portfolio(ledger, [row], {}, "2026-08-29T00:01:00+00:00")
    ledger, summary = reconcile_portfolio(ledger, [], {}, "2026-08-29T00:02:00+00:00")
    assert summary["open_positions"] == 1
    assert summary["exit_pending"] == 1
    assert summary["cash_usd"] == 99.0
    assert ledger["positions"][0]["exit_reason"] == "EXIT_UNVERIFIED_NO_EXACT_PAIR_QUOTE"


def test_closed_exact_pair_does_not_reenter():
    ledger = initial_ledger("2026-08-29T00:00:00+00:00")
    row = candidate(price=1.0)
    ledger, _ = reconcile_portfolio(ledger, [row], {}, "2026-08-29T00:01:00+00:00")
    key = "bsc|0xabc|0xpair"
    ledger, _ = reconcile_portfolio(ledger, [], {key: candidate(price=1.2)}, "2026-08-29T00:02:00+00:00")
    ledger, summary = reconcile_portfolio(ledger, [candidate(price=1.3)], {}, "2026-08-29T00:03:00+00:00")
    assert summary["trades_total"] == 1
    assert summary["open_positions"] == 0
