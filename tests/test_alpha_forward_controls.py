from datetime import datetime, timezone
import json

from wallet500.alpha_forward_controls import MODE, run


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_enrolls_only_verified_tradable_non_actionable_watch(tmp_path):
    activation = "2026-09-10T10:00:00+00:00"
    write(tmp_path / "alpha-proof-ledger.json", {
        "version": 1, "mode": "FORWARD_ONLY_ALPHA_PROOF_V1", "activation_at": activation,
        "created_at": activation, "updated_at": activation, "signals": {}, "controls": {}, "policy": {},
    })
    write(tmp_path / "real-alerts.json", {
        "generated_at": "2026-09-10T11:30:00+00:00",
        "verified_watch": [
            {
                "chain": "solana", "token_address": "TOK", "pair_address": "PAIR",
                "watch_added_at": "2026-09-10T10:30:00+00:00", "price_usd": 1.0,
                "execution_pool_liquidity_usd": 60000, "market_age_days": 120,
                "market_age_verified": True, "exact_pair_verified": True,
                "actionable_research_alert": False, "status": "VERIFIED_WATCH_NOT_REAL_ALERT",
                "score": 55, "blockers": ["INDEPENDENT_CONFIRMATION_LT_2"],
            },
            {
                "chain": "solana", "token_address": "TVLONLY", "pair_address": "PAIR2",
                "watch_added_at": "2026-09-10T10:35:00+00:00", "price_usd": 1.0,
                "pool_tvl_usd": 500000, "execution_pool_liquidity_usd": None,
                "market_age_days": 130, "market_age_verified": True, "exact_pair_verified": True,
                "actionable_research_alert": False,
            },
            {
                "chain": "solana", "token_address": "ALERT", "pair_address": "PAIR3",
                "watch_added_at": "2026-09-10T10:40:00+00:00", "price_usd": 1.0,
                "execution_pool_liquidity_usd": 80000, "market_age_days": 150,
                "market_age_verified": True, "exact_pair_verified": True,
                "actionable_research_alert": True,
            },
        ],
    })
    audit = run(tmp_path, now=datetime(2026, 9, 10, 11, 30, tzinfo=timezone.utc))
    assert audit["mode"] == MODE
    assert audit["enrolled_this_run"] == 1
    assert audit["formal_control_count_after"] == 1
    ledger = json.loads((tmp_path / "alpha-proof-ledger.json").read_text())
    rec = next(iter(ledger["controls"].values()))
    assert rec["token"] == "TOK"
    assert rec["entry_context"]["market_age_days"] == 120
    assert rec["entry_context"]["execution_liquidity_usd"] == 60000
    assert "24h" not in rec["checkpoints"]
    assert audit["policy"]["pool_tvl_never_substitutes_for_execution_liquidity"] is True
