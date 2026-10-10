from scripts.unified_watch_engine import rotate_noncritical_targets, scan_priority


def test_rotation_preserves_critical_priority_and_cycles_tail():
    targets = [
        {"symbol": "A"}, {"symbol": "B"}, {"symbol": "C"},
        {"symbol": "BUY", "dynamic_buy_candidate": True},
        {"symbol": "HOT", "critical_market_lane": True},
    ]
    first = rotate_noncritical_targets(targets, 0)
    second = rotate_noncritical_targets(targets, 1)
    third = rotate_noncritical_targets(targets, 3)
    assert [t["symbol"] for t in first] == ["BUY", "HOT", "A", "B", "C"]
    assert [t["symbol"] for t in second] == ["BUY", "HOT", "B", "C", "A"]
    assert [t["symbol"] for t in third] == [t["symbol"] for t in first]
    assert all(scan_priority(t) < 3 for t in second[:2])


def test_rotation_empty_tail_is_safe():
    targets = [{"symbol": "BUY", "dynamic_buy_candidate": True}]
    assert rotate_noncritical_targets(targets, 999) == targets
