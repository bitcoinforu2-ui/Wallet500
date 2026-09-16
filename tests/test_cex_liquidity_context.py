from __future__ import annotations

import subprocess
import sys
import textwrap


def _run(code: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


def test_deepest_verified_same_token_pool_is_separate_from_execution_pair():
    _run(
        r'''
        from datetime import datetime, timezone, timedelta
        from scripts import run_cex_action_guarded as guard

        now = datetime.now(timezone.utc)
        old_ms = int((now - timedelta(days=400)).timestamp() * 1000)
        new_ms = int((now - timedelta(days=20)).timestamp() * 1000)
        token = "0x92aa03137385F18539301349dcfc9ebc923ffb10"
        execution_pair = "0x69B86059C5Fb3A44355937e7b505A659443b9A22"

        def fake_get(url, timeout=8):
            assert token in url
            return [
                {
                    "chainId": "bsc",
                    "pairAddress": execution_pair,
                    "dexId": "pancakeswap",
                    "baseToken": {"address": token, "symbol": "SKYAI"},
                    "priceUsd": "0.0575",
                    "pairCreatedAt": old_ms,
                    "liquidity": {"usd": 48000},
                    "url": "https://dexscreener.com/bsc/execution",
                },
                {
                    "chainId": "bsc",
                    "pairAddress": "0xDEEPER",
                    "dexId": "pancakeswap",
                    "baseToken": {"address": token.lower(), "symbol": "SKYAI"},
                    "priceUsd": "0.0577",
                    "pairCreatedAt": old_ms,
                    "liquidity": {"usd": 2_400_000},
                    "url": "https://dexscreener.com/bsc/deeper",
                },
                {
                    "chainId": "bsc",
                    "pairAddress": "0xWRONGTOKEN",
                    "dexId": "pancakeswap",
                    "baseToken": {"address": "0x1111111111111111111111111111111111111111", "symbol": "SKYAI"},
                    "priceUsd": "0.0576",
                    "pairCreatedAt": old_ms,
                    "liquidity": {"usd": 9_000_000},
                },
                {
                    "chainId": "bsc",
                    "pairAddress": "0xTOONEW",
                    "dexId": "pancakeswap",
                    "baseToken": {"address": token, "symbol": "SKYAI"},
                    "priceUsd": "0.0576",
                    "pairCreatedAt": new_ms,
                    "liquidity": {"usd": 8_000_000},
                },
                {
                    "chainId": "bsc",
                    "pairAddress": "0xBADPRICE",
                    "dexId": "pancakeswap",
                    "baseToken": {"address": token, "symbol": "SKYAI"},
                    "priceUsd": "0.20",
                    "pairCreatedAt": old_ms,
                    "liquidity": {"usd": 7_000_000},
                },
            ]

        guard.promo._get = fake_get
        row = {
            "chain": "bsc",
            "token_address": token,
            "pair_address": execution_pair,
            "dex": "pancakeswap",
            "dex_url": "https://dexscreener.com/bsc/execution",
            "dex_price_usd": 0.0575,
            "execution_pool_liquidity_usd": 48_000,
        }
        metrics = {"current_price": 0.0576, "execution_liquidity_usd": 48_000}
        out = guard.best_verified_pool_context(row, metrics)
        assert out["best_verified_pool_check_complete"] is True
        assert out["best_verified_pool_liquidity_usd"] == 2_400_000
        assert out["best_verified_pool_pair_address"] == "0xDEEPER"
        assert out["best_verified_pool_is_execution_pair"] is False
        assert out["liquidity_context"] == "DEEPER_SAME_TOKEN_POOL_VERIFIED"
        '''
    )


def test_telegram_copy_labels_pair_depth_and_total_depth_separately():
    _run(
        r'''
        from scripts import run_cex_action_guarded as guard

        guard.best_verified_pool_context = lambda row, metrics: {
            "best_verified_pool_liquidity_usd": 2_400_000.0,
            "best_verified_pool_pair_address": "0xDEEPER",
            "best_verified_pool_dex": "pancakeswap",
            "best_verified_pool_url": "https://dexscreener.com/bsc/deeper",
            "best_verified_pool_price_usd": 0.0577,
            "best_verified_pool_check_complete": True,
            "best_verified_pool_source": "TEST",
            "best_verified_pool_is_execution_pair": False,
            "liquidity_context": "DEEPER_SAME_TOKEN_POOL_VERIFIED",
        }
        row = {
            "chain": "bsc",
            "token_address": "0xTOKEN",
            "pair_address": "0xPAIR",
            "dex": "pancakeswap",
            "dex_url": "https://dexscreener.com/bsc/execution",
            "execution_pool_liquidity_usd": 48_000,
        }
        metrics = {
            "symbol": "SKYAIUSDT",
            "signal_price": 0.06076,
            "current_price": 0.0576,
            "signal_at": "2026-09-05T18:55:50.520435+00:00",
            "current_change_24h_pct": 13.0,
            "cex_turnover_usd": 545_800,
            "coherent_confirmations": 2,
            "exchanges": ["gate", "mexc"],
            "single_exchange_exception": False,
            "signal_score": 58,
            "market_age_days": 507,
            "execution_liquidity_usd": 48_000,
        }
        text = guard.guarded_message(row, metrics, "2026-09-16T10:00:00+00:00", "CF-TEST")
        assert text.startswith("🟢 BUY ZONE — ENTRY TIMING PASSED")
        assert "Execution pair liquidity: $48.0K ✅ min $15K" in text
        assert "Best verified pool liquidity: $2.40M · pancakeswap ✅" in text
        assert "execution-pair depth ≠ total asset depth" in text
        assert "Execution liquidity:" not in text
        assert metrics["best_verified_pool_liquidity_usd"] == 2_400_000.0
        '''
    )


def test_failed_deeper_pool_scan_never_pretends_total_asset_liquidity_is_known():
    _run(
        r'''
        from scripts import run_cex_action_guarded as guard

        def fail_get(url, timeout=8):
            raise RuntimeError("network down")

        guard.promo._get = fail_get
        row = {
            "chain": "bsc",
            "token_address": "0xTOKEN",
            "pair_address": "0xPAIR",
            "dex": "pancakeswap",
            "execution_pool_liquidity_usd": 48_000,
        }
        metrics = {"current_price": 0.0576, "execution_liquidity_usd": 48_000}
        out = guard.best_verified_pool_context(row, metrics)
        assert out["best_verified_pool_check_complete"] is False
        assert out["best_verified_pool_liquidity_usd"] == 48_000
        assert out["liquidity_context"] == "EXECUTION_PAIR_BASELINE_ONLY"
        '''
    )
