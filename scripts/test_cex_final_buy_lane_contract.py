from __future__ import annotations

from datetime import datetime, timedelta, timezone

import cex_final_buy_lane as lane


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
CFG = lane.policy({})


def candidate(
    symbol: str,
    *,
    score: float,
    coherent: int,
    change: float,
    turnover: float = 100_000.0,
    relative_multiple: float = 0.0,
    relative_accel: float = 0.0,
    rank: int | None = 8,
    price: float = 0.01,
) -> dict:
    market_id = f"{symbol}_USDT"
    return {
        "key": f"cex:test-{symbol.lower()}:{symbol}",
        "symbol": symbol,
        "coingecko_id": f"test-{symbol.lower()}",
        "asset_identity_verified": True,
        "identity_status": "IDENTITY_PENDING",
        "identity_blocker": "NO_EXACT_ONCHAIN_PLATFORM_IDENTITY",
        "market_age_verified": True,
        "market_age_days": 1000,
        "symbol_collision_suspected": False,
        "price_coherent_exchanges": ["gate", "kucoin"] if coherent >= 2 else ["gate"],
        "signal_score": score,
        "signal_at": "2026-09-20T10:00:00+00:00",
        "signal_price": price * 0.98,
        "signal_milestone": "IMMUTABLE_EARLY_SIGNAL_LEDGER",
        "coherent_confirmations": coherent,
        "leaderboard_best_rank": rank,
        "current_change_24h_pct": change,
        "current_price": price,
        "turnover_24h_usd": turnover,
        "relative_volume_multiple": relative_multiple,
        "relative_volume_acceleration_pct": relative_accel,
        "risk_level": "",
        "markets": [
            {
                "exchange": "gate",
                "market_id": market_id,
                "symbol": f"{symbol}USDT",
                "quote_symbol": "USDT",
                "price": price,
                "volume_24h": turnover,
            }
        ],
    }


def execution(symbol: str, price: float) -> dict:
    return {
        "execution_type": "CEX_SPOT_ORDERBOOK",
        "execution_verified": True,
        "exchange": "gate",
        "market_id": f"{symbol}_USDT",
        "mid_price": price,
        "spread_pct": 0.2,
        "minimum_side_depth_band_usd": 20_000,
        "bid_depth_band_usd": 25_000,
        "ask_depth_band_usd": 20_000,
        "price_error_pct": 0.1,
        "blockers": [],
    }


def assert_two_scan_buy(row: dict) -> None:
    ok, gate = lane.precheck(row, CFG)
    assert ok is True, (row["symbol"], gate)
    first, s1 = lane.evaluate_candidate(
        row,
        execution(row["symbol"], row["current_price"]),
        {},
        CFG,
        now=NOW,
    )
    assert first["state"] == "QUALIFYING", (row["symbol"], first)
    assert first["pre_buy"] is True
    assert first["pre_buy_alert"] is True
    assert first["recommended_action"] == "WAIT"
    assert first["truth_contract"]["exact_dex_pair_not_required_for_cex_execution"] is True

    second_price = row["current_price"] * 1.01
    second, _ = lane.evaluate_candidate(
        row,
        execution(row["symbol"], second_price),
        s1,
        CFG,
        now=NOW + timedelta(minutes=10),
    )
    assert second["state"] == "BUY_ZONE", (row["symbol"], second)
    assert second["recommended_action"] == "BUY"
    assert second["alert"] is True
    assert second["execution_mode"] == "CEX_SPOT"


def main() -> None:
    # Historical archetypes from the 2026-09-20 missed-mover review:
    # the old engine saw these signals but blocked them on DEX/on-chain promotion.
    replay = [
        candidate("VENOM", score=73, coherent=3, change=11.6, turnover=275_000, rank=3),
        candidate("ONE", score=38, coherent=4, change=1.16, turnover=500_000, relative_multiple=8.7, rank=8),
        candidate("CELR", score=35, coherent=4, change=-2.14, turnover=250_000, relative_multiple=8.0, rank=10),
        candidate("FIO", score=37, coherent=1, change=12.0, turnover=30_000, relative_multiple=5.0, rank=1),
        candidate("RARI", score=43, coherent=2, change=4.34, turnover=40_000, rank=6),
        candidate("HEART", score=33, coherent=2, change=14.69, turnover=60_000, relative_multiple=7.0, rank=5),
    ]
    for row in replay:
        assert_two_scan_buy(row)

    # The CEX lane deliberately does not require chain/contract/DEX pair.
    no_dex = candidate("NODEX", score=45, coherent=2, change=8.0)
    assert "chain" not in no_dex and "pair_address" not in no_dex and "token_address" not in no_dex
    assert lane.precheck(no_dex, CFG)[0] is True

    # Asset identity remains fail-closed even though DEX identity is no longer required.
    bad_identity = candidate("BADID", score=70, coherent=3, change=10.0)
    bad_identity["asset_identity_verified"] = False
    ok, gate = lane.precheck(bad_identity, CFG)
    assert ok is False
    assert "CEX_ASSET_IDENTITY_NOT_VERIFIED" in gate["blockers"]

    collision = candidate("COLLIDE", score=70, coherent=3, change=10.0)
    collision["symbol_collision_suspected"] = True
    collision["price_coherent_exchanges"] = ["gate"]
    ok, gate = lane.precheck(collision, CFG)
    assert ok is False
    assert "UNRESOLVED_TICKER_COLLISION" in gate["blockers"]

    # Never convert an already-spent +70% move into a new BUY.
    late = candidate("LATE", score=80, coherent=5, change=71.0, turnover=2_000_000, rank=1)
    ok, gate = lane.precheck(late, CFG)
    assert ok is False
    assert "LATE_MOVE_DO_NOT_CHASE" in gate["blockers"]

    # A live exact CEX order book is mandatory.
    row = candidate("NOBOOK", score=50, coherent=2, change=8.0)
    decision, _ = lane.evaluate_candidate(
        row,
        {"execution_verified": False, "blockers": ["CEX_ORDERBOOK_DEPTH_TOO_LOW"]},
        {},
        CFG,
        now=NOW,
    )
    assert decision["recommended_action"] == "WAIT"
    assert "CEX_ORDERBOOK_DEPTH_TOO_LOW" in decision["blockers"]

    msg = lane.telegram_message(
        lane.evaluate_candidate(
            candidate("MSG", score=55, coherent=2, change=8.0),
            execution("MSG", 0.01),
            {},
            CFG,
            now=NOW,
        )[0]
    )
    assert "PRE-BUY" in msg
    assert "CEX execution identity verified" in msg

    print("CEX_FINAL_BUY_LANE_CONTRACT_OK")


if __name__ == "__main__":
    main()
