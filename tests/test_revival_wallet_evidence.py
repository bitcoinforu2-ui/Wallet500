from datetime import datetime, timedelta, timezone

from wallet500 import revival_wallet_evidence as wallet


def _tx(mint: str, owner: str, pre: int, post: int, signer: bool = True):
    def bal(amount: int):
        return {
            "mint": mint,
            "owner": owner,
            "uiTokenAmount": {"amount": str(amount), "decimals": 0},
        }

    return {
        "blockTime": 1_800_000_000,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": owner, "signer": signer, "writable": True},
                    {"pubkey": "Program111", "signer": False, "writable": False},
                ]
            }
        },
        "meta": {
            "err": None,
            "preTokenBalances": [bal(pre)],
            "postTokenBalances": [bal(post)],
        },
    }


def test_extract_trade_requires_signed_token_owner_delta():
    mint = "Mint111"
    owner = "Wallet111"
    buy = wallet._extract_trade(_tx(mint, owner, 10, 25), "sig1", mint)
    assert buy is not None
    assert buy["w"] == owner
    assert buy["side"] == "BUY"
    assert buy["token_delta"] == 15
    assert buy["resolution"] == "SIGNED_TOKEN_OWNER_DELTA"

    sell = wallet._extract_trade(_tx(mint, owner, 25, 5), "sig2", mint)
    assert sell is not None
    assert sell["side"] == "SELL"
    assert sell["token_delta"] == -20

    unsigned = wallet._extract_trade(
        _tx(mint, owner, 10, 25, signer=False), "sig3", mint
    )
    assert unsigned is None


def test_extract_trade_does_not_accept_other_mint_delta():
    tx = _tx("OtherMint", "Wallet111", 10, 25)
    assert wallet._extract_trade(tx, "sig", "TargetMint") is None


def test_window_counts_unique_verified_wallets():
    now = 2_000_000_000
    events = [
        {"t": now - 30, "w": "A", "side": "BUY", "token_delta": 5},
        {"t": now - 20, "w": "A", "side": "BUY", "token_delta": 2},
        {"t": now - 10, "w": "B", "side": "SELL", "token_delta": -3},
    ]
    first = {
        "A": {"t": now - 30, "side": "BUY"},
        "B": {"t": now - 10, "side": "SELL"},
    }
    result = wallet._window(events, first, now - 300)
    assert result["resolved_swaps"] == 3
    assert result["unique_traders"] == 2
    assert result["unique_buyers"] == 1
    assert result["unique_sellers"] == 1
    assert result["net_accumulating_wallets"] == 1
    assert result["net_distributing_wallets"] == 1


def test_summary_never_calls_forward_monitor_t0_evidence():
    now = 2_000_000_000
    monitor_started = now
    forensic_t0 = datetime.fromtimestamp(
        now - 600, tz=timezone.utc
    ).isoformat()
    target = {
        "token_address": "Mint111",
        "symbol": "OLD",
        "pair_address": "Pair111",
        "forensics_t0": forensic_t0,
    }
    state = {
        "monitor_started_at": monitor_started,
        "wallet_first": {},
        "events": [],
        "last_run": {"status": "WARMING_UP_FORWARD_ONLY"},
    }
    summary = wallet._summary_for(target, state, now)
    assert (
        summary["coverage"]["eligible_as_forensics_t0_wallet_evidence"]
        is False
    )
    assert summary["smart_money_tiers"]["elite"] == 0
    assert summary["smart_money_tiers"]["status"].startswith("NOT_SCORED")
