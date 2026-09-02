from wallet500.telegram_alerts import _pair_key, _tier, _message


def _row():
    return {
        'chain':'bsc','token':'0xABC','pair_address':'0xPAIR','locked_pair_address':'0xPAIR','pair_identity_locked':True,
        'qualification':'QUALIFIED','live_survival_gate':'ACTIVE','pump_dump_blocked':False,
        'holder_cluster_production_status':'PASS','holder_cluster_verification_complete':True,
        'market_age_verified':True,'market_age_min_days':420,
        'market_age_evidence_source':'DEXSCREENER_OLDEST_CURRENT_EXACT_TOKEN_PAIR_CREATED_AT',
        'anomaly_score':92,'live_liquidity_usd':80000,'live_volume_h1':50000,'live_activity_h1':120,
        'pump_dump_risk_level':'LOW','dex':'pancakeswap','price_usd':0.01,'buys_h1':80,'sells_h1':40,
        'survival_checked_at':'2026-09-02T04:00:00+00:00','url':'https://dexscreener.com/bsc/0xpair',
    }


def test_exact_pair_is_required_for_alert():
    row=_row()
    assert _tier(row)=='HIGH_CONVICTION'
    row['locked_pair_address']='0xOTHER'
    assert _tier(row) is None


def test_verified_180_day_market_age_is_required_for_alert():
    row=_row()
    row['market_age_min_days']=179
    assert _tier(row) is None
    row=_row()
    row['market_age_verified']=False
    assert _tier(row) is None
    row=_row()
    row.pop('market_age_min_days')
    assert _tier(row) is None


def test_dedupe_key_contains_pair_and_message_exposes_identity_and_market_age():
    row=_row()
    assert _pair_key(row)=='bsc:0xabc:0xpair'
    msg=_message(row,'HIGH_CONVICTION')
    assert 'Pair: 0xPAIR' in msg
    assert 'DEX: pancakeswap' in msg
    assert 'Pair identity: EXACT LOCK' in msg
    assert 'Market age: ≥420d' in msg
