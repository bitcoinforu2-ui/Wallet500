from wallet500.paid_order_truth import active_orders, is_solana_address

VALID_SOL = "8H5yfL1GoDETLDaLYZzrgQuZs37eiKJjdfP21b6ypump"


def test_strict_solana_address_validation():
    assert is_solana_address(VALID_SOL)
    assert not is_solana_address("0x47366e0F257Ac009e82bD46fB74e2Fb50826cE98")
    assert not is_solana_address("d97F261b1e88845184f678e2d1e7a98D9FD38dE")
    assert not is_solana_address("x3aCdDe62eA42fCC43ebf4b85362CC7fF4fDfe439")


def test_only_active_paid_orders_are_truth_evidence():
    rows = [
        {"type": "tokenAd", "status": "approved", "paymentTimestamp": 1},
        {"type": "trendingBarAd", "status": "processing", "paymentTimestamp": 2},
        {"type": "communityTakeover", "status": "on-hold", "paymentTimestamp": 3},
        {"type": "tokenProfile", "status": "cancelled", "paymentTimestamp": 4},
        {"type": "tokenAd", "status": "rejected", "paymentTimestamp": 5},
    ]
    out = active_orders(rows)
    assert [x["type"] for x in out] == ["tokenAd", "trendingBarAd", "communityTakeover"]


def test_missing_status_is_not_counted_as_active_paid_order():
    assert active_orders([{"type": "tokenProfile", "paymentTimestamp": 1}]) == []
