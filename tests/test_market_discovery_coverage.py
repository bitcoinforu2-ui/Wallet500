from wallet500.market_discovery import BSC_MIN_DISCOVERY_CAP, FRESH_PAGE_COUNT, _add, _chain_limit


def test_bsc_has_expanded_initial_discovery_cap():
    assert BSC_MIN_DISCOVERY_CAP >= 300
    assert _chain_limit("bsc", 120) == BSC_MIN_DISCOVERY_CAP
    assert _chain_limit("ethereum", 120) == 120
    assert _chain_limit("solana", 120) == 120


def test_fresh_lane_covers_more_than_three_pages():
    assert FRESH_PAGE_COUNT >= 5


def test_bsc_candidate_is_not_dropped_at_legacy_120_cap():
    rows=[];seen=set();counts={"bsc":120};filtered={"bsc":0}
    token="0x0000000000000000000000000000000000000121"
    _add(rows,seen,counts,filtered,"bsc",token,"test",120)
    assert counts["bsc"] == 121
    assert rows and rows[0]["token"] == token
