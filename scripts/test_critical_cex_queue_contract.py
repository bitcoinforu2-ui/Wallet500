from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unified_watch_engine as engine


def main() -> None:
    rows = [{"symbol": f"C{i}", "network": "bsc", "contract": f"0x{i:040x}", "pair": f"0x{i+1000:040x}"} for i in range(30)]

    selected, cursor, stats = engine.bounded_fair_cex_queue(rows, cursor=0, limit=10)
    assert len(selected) == 10
    assert stats["input"] == 30
    assert stats["selected"] == 10
    assert stats["deferred"] == 20
    assert stats["priority_reserve"] == 5
    assert [x["symbol"] for x in selected[:5]] == [f"C{i}" for i in range(5)]

    selected2, cursor2, stats2 = engine.bounded_fair_cex_queue(rows, cursor=cursor, limit=10)
    assert len(selected2) == 10
    assert cursor2 != cursor
    assert [x["symbol"] for x in selected2[:5]] == [f"C{i}" for i in range(5)]
    assert set(x["symbol"] for x in selected[5:]).isdisjoint(
        set(x["symbol"] for x in selected2[5:])
    )

    # Across enough scans every non-reserved identity receives a turn.
    seen = set()
    cur = 0
    for _ in range(6):
        batch, cur, _ = engine.bounded_fair_cex_queue(rows, cursor=cur, limit=10)
        seen.update(x["symbol"] for x in batch)
    assert seen == {f"C{i}" for i in range(30)}

    tiny, cur, stats = engine.bounded_fair_cex_queue(rows[:3], cursor=999, limit=10)
    assert len(tiny) == 3
    assert cur == 0
    assert stats["deferred"] == 0

    print("CRITICAL_CEX_QUEUE_HARD_BOUND_FAIR_ROTATION_OK")


if __name__ == "__main__":
    main()
