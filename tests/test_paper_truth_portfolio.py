from wallet500.paper_truth_portfolio import initial_ledger, reconcile


def candidate(price=1.0, liquidity=60000.0):
    return {
        'chain': 'bsc',
        'token': '0xABC',
        'pair_address': '0xPAIR',
        'price_usd': price,
        'liquidity_usd': liquidity,
        'holder_cluster_production_status': 'PASS',
        'holder_cluster_verification_complete': True,
    }


def entry_quote(qty=2.0, exact=True, pair='0xPAIR'):
    return {
        'status': 'VERIFIED',
        'token_amount_base_units': int(qty * 10**18),
        'token_decimals': 18,
        'quantity': qty,
        'cost_usd': 1.0,
        'effective_entry_price_usd': 1.0 / qty,
        'stable_symbol': 'USDT',
        'proof_level': 'FIRM_ENTRY_TEST',
        'exact_pair_constrained': exact,
        'quoted_pair_address': pair,
    }


def exit_quote(value=1.5, exact=True, pair='0xPAIR'):
    return {
        'status': 'VERIFIED',
        'quoted_exit_value_usd': value,
        'stable_symbol': 'USDT',
        'proof_level': 'FIRM_EXIT_TEST',
        'exact_pair_constrained': exact,
        'quoted_pair_address': pair,
    }


def test_no_entry_without_firm_quote():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    ledger, summary = reconcile(ledger, [candidate()], {}, {}, '2026-08-29T00:01:00+00:00')
    assert summary['open_positions'] == 0
    assert summary['cash_usd'] == 100.0


def test_generic_router_quote_is_not_booked():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    row = candidate()
    key = 'bsc|0xabc|0xpair'
    ledger, summary = reconcile(ledger, [row], {key: entry_quote(exact=False, pair=None)}, {}, '2026-08-29T00:01:00+00:00')
    assert summary['open_positions'] == 0
    assert summary['cash_usd'] == 100.0
    assert any(e.get('type') == 'ENTRY_NOT_BOOKED' for e in ledger['events'])


def test_wrong_pair_quote_is_not_booked():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    row = candidate()
    key = 'bsc|0xabc|0xpair'
    ledger, summary = reconcile(ledger, [row], {key: entry_quote(pair='0xOTHER')}, {}, '2026-08-29T00:01:00+00:00')
    assert summary['open_positions'] == 0
    assert summary['cash_usd'] == 100.0


def test_entry_books_only_exact_pair_verified_quantity():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    row = candidate(price=0.6)
    key = 'bsc|0xabc|0xpair'
    ledger, summary = reconcile(ledger, [row], {key: entry_quote(2.0)}, {}, '2026-08-29T00:01:00+00:00')
    assert summary['open_positions'] == 1
    assert summary['cash_usd'] == 99.0
    p = ledger['positions'][0]
    assert p['quantity'] == 2.0
    assert p['effective_entry_quote_price_usd'] == 0.5
    assert p['entry_market_price_usd'] == 0.6
    assert p['entry_liquidity_usd'] == 60000.0
    assert p['entry_exact_pair_constrained'] is True


def test_below_50k_liquidity_never_books():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    row = candidate(liquidity=49999.0)
    key = 'bsc|0xabc|0xpair'
    ledger, summary = reconcile(ledger, [row], {key: entry_quote()}, {}, '2026-08-29T00:01:00+00:00')
    assert summary['open_positions'] == 0
    assert summary['cash_usd'] == 100.0


def test_exit_signal_does_not_fabricate_sale_without_exact_pair_quote():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    row = candidate()
    key = 'bsc|0xabc|0xpair'
    ledger, _ = reconcile(ledger, [row], {key: entry_quote(1.0)}, {}, '2026-08-29T00:01:00+00:00')
    ledger, summary = reconcile(ledger, [], {}, {key: exit_quote(1.5, exact=False, pair=None)}, '2026-08-29T00:02:00+00:00')
    assert summary['open_positions'] == 1
    assert summary['exit_pending'] == 1
    assert summary['realized_quote_pnl_usd'] == 0.0
    assert summary['cash_usd'] == 99.0


def test_verified_exact_pair_exit_books_profit():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    row = candidate()
    key = 'bsc|0xabc|0xpair'
    ledger, _ = reconcile(ledger, [row], {key: entry_quote(1.0)}, {}, '2026-08-29T00:01:00+00:00')
    ledger, summary = reconcile(ledger, [], {}, {key: exit_quote(1.5)}, '2026-08-29T00:02:00+00:00')
    assert summary['open_positions'] == 0
    assert summary['closed_exact_pair_quote_verified_positions'] == 1
    assert summary['realized_quote_pnl_usd'] == 0.5
    assert summary['cash_usd'] == 100.5
    assert summary['closed_quote_wins'] == 1


def test_loss_is_counted_not_deleted():
    ledger = initial_ledger('2026-08-29T00:00:00+00:00')
    row = candidate()
    key = 'bsc|0xabc|0xpair'
    ledger, _ = reconcile(ledger, [row], {key: entry_quote(1.0)}, {}, '2026-08-29T00:01:00+00:00')
    ledger, summary = reconcile(ledger, [], {}, {key: exit_quote(0.2)}, '2026-08-29T00:02:00+00:00')
    assert summary['realized_quote_pnl_usd'] == -0.8
    assert summary['cash_usd'] == 99.2
    assert summary['closed_quote_losses'] == 1
    assert len(ledger['positions']) == 1
