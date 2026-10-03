from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from wallet500 import mature_age_gate as g


def old_date(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def pair_created_ms(days: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)


def test_cex_gate_keeps_only_unique_verified_old_symbol(tmp_path, monkeypatch):
    p = tmp_path / "cex.json"
    p.write_text(json.dumps({
        "version": 6,
        "alerts": [
            {"symbol": "OLDUSDT", "cex_revival_score": 70},
            {"symbol": "YOUNGUSDT", "cex_revival_score": 80},
            {"symbol": "AMBUSDT", "cex_revival_score": 90},
        ],
    }))
    monkeypatch.setattr(g, "fetch_by_symbols", lambda _symbols: {
        "OLD": [{"id": "old", "symbol": "old", "ath_date": old_date(400), "atl_date": old_date(300)}],
        "YOUNG": [{"id": "young", "symbol": "young", "ath_date": old_date(30), "atl_date": old_date(50)}],
        "AMB": [
            {"id": "amb-a", "symbol": "amb", "ath_date": old_date(500), "atl_date": old_date(450)},
            {"id": "amb-b", "symbol": "amb", "ath_date": old_date(600), "atl_date": old_date(550)},
        ],
    })
    report = g.enforce_cex(p)
    out = json.loads(p.read_text())
    assert report["accepted"] == 1
    assert out["alerts_count"] == 1
    assert out["alerts"][0]["symbol"] == "OLDUSDT"
    assert out["alerts"][0]["market_age_verified"] is True
    assert out["alerts"][0]["market_age_min_days"] >= 90


def test_revival_gate_accepts_exact_old_id_and_old_pair(tmp_path, monkeypatch):
    p = tmp_path / "revival.json"
    p.write_text(json.dumps({
        "coins": [
            {"id": "old-base", "symbol": "OLD", "source": "coingecko", "dex_link_type": "DEXSCREENER_VERIFIED_PAIR"},
            {"id": "young-base", "symbol": "YNG", "source": "coingecko", "dex_link_type": "DEXSCREENER_VERIFIED_PAIR"},
            {
                "id": "discovery:abc", "symbol": "EXP", "source": "revival_discovery_state+dexscreener_absorption_expansion",
                "pair_age_days": 240, "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
                "absorption_candidate_proxy": True,
                "watch_status": "ABSORPTION_CANDIDATE_DISCOVERY_EXPANSION",
                "order_flow_absorption": {"signal": False},
            },
        ],
        "counts": {},
    }))
    monkeypatch.setattr(g, "fetch_by_ids", lambda _ids: {
        "old-base": {"id": "old-base", "ath_date": old_date(700), "atl_date": old_date(500)},
        "young-base": {"id": "young-base", "ath_date": old_date(20), "atl_date": old_date(40)},
    })
    report = g.enforce_revival(p)
    out = json.loads(p.read_text())
    assert report["accepted"] == 2
    assert {x["symbol"] for x in out["coins"]} == {"OLD", "EXP"}
    assert all(x["market_age_verified"] is True for x in out["coins"])
    assert all(x["market_age_min_days"] >= 90 for x in out["coins"])
    assert out["counts"]["age_verified_60d_plus"] == 2
    assert out["counts"]["age_gate_rejected"] == 1


def test_active_gate_uses_exact_token_history_not_symbol(tmp_path, monkeypatch):
    active = tmp_path / "active.json"
    audit = tmp_path / "audit.json"
    active.write_text(json.dumps([
        {
            "chain": "bsc", "token": "0xOLD", "pair_address": "0xNEWPAIR",
            "locked_pair_address": "0xNEWPAIR", "pair_identity_locked": True,
            "pair_created_at": pair_created_ms(20),
        },
        {
            "chain": "bsc", "token": "0xYOUNG", "pair_address": "0xYPAIR",
            "locked_pair_address": "0xYPAIR", "pair_identity_locked": True,
            "pair_created_at": pair_created_ms(20),
        },
        {
            "chain": "bsc", "token": "0xNOLOCK", "pair_address": "0xPAIR",
            "locked_pair_address": "0xOTHER", "pair_identity_locked": True,
            "pair_created_at": pair_created_ms(500),
        },
    ]))

    def fake_pairs(chain, token):
        if token == "0xOLD":
            return [
                {
                    "pairAddress": "0xOLDPAIR", "pairCreatedAt": pair_created_ms(420),
                    "baseToken": {"address": "0xOLD"}, "quoteToken": {"address": "0xQUOTE"},
                },
                {
                    "pairAddress": "0xNEWPAIR", "pairCreatedAt": pair_created_ms(20),
                    "baseToken": {"address": "0xOLD"}, "quoteToken": {"address": "0xQUOTE"},
                },
            ]
        if token == "0xYOUNG":
            return [{
                "pairAddress": "0xYPAIR", "pairCreatedAt": pair_created_ms(20),
                "baseToken": {"address": "0xYOUNG"}, "quoteToken": {"address": "0xQUOTE"},
            }]
        return []

    monkeypatch.setattr(g, "token_pairs", fake_pairs)
    report = g.enforce_active_candidates(active, audit)
    out = json.loads(active.read_text())
    assert report["accepted"] == 1
    assert report["rejected"] == 2
    assert len(out) == 1
    assert out[0]["token"] == "0xOLD"
    assert out[0]["market_age_verified"] is True
    assert out[0]["market_age_min_days"] >= 90
    assert out[0]["market_age_evidence_source"] == "DEXSCREENER_OLDEST_CURRENT_EXACT_TOKEN_PAIR_CREATED_AT"
    g.validate_active_file(active)


def test_active_gate_accepts_old_locked_pair_without_extra_lookup(tmp_path, monkeypatch):
    active = tmp_path / "active.json"
    audit = tmp_path / "audit.json"
    active.write_text(json.dumps([{
        "chain": "solana", "token": "So11111111111111111111111111111111111111111",
        "pair_address": "PAIR111111111111111111111111111111111111111",
        "locked_pair_address": "PAIR111111111111111111111111111111111111111",
        "pair_identity_locked": True, "pair_created_at": pair_created_ms(365),
    }]))
    monkeypatch.setattr(g, "token_pairs", lambda _chain, _token: (_ for _ in ()).throw(AssertionError("lookup should not run")))
    report = g.enforce_active_candidates(active, audit)
    assert report["accepted"] == 1
    out = json.loads(active.read_text())
    assert out[0]["market_age_evidence_source"] == "DEXSCREENER_EXACT_LOCKED_PAIR_CREATED_AT"


def test_validate_file_fails_closed_on_unverified_row(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({
        "age_gate": {"status": "ENFORCED_FAIL_CLOSED", "minimum_market_age_days": 90},
        "alerts": [{"symbol": "X", "market_age_verified": False, "market_age_min_days": 0}],
    }))
    try:
        g.validate_file(p, "alerts")
    except SystemExit as exc:
        assert "MATURE_AGE_GATE_VIOLATION" in str(exc)
    else:
        raise AssertionError("validate_file must fail closed")


def test_revival_uses_mint_bound_historical_age_proof_when_provider_is_down(tmp_path, monkeypatch):
    """Previously verified age may survive an outage, never current market data."""
    monkeypatch.setattr(g, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(g, "DATA", tmp_path)
    (tmp_path / "cache.json").write_text(json.dumps({
        "version": 2, "coins": {
            "old": {
                "coingecko_id": "old", "network": "solana", "token_address": "MintA",
                "market_age_verified": True,
                "market_age_evidence_at": old_date(400),
                "market_age_evidence_source": "COINGECKO_ATH_OR_ATL_HISTORICAL_EVIDENCE_EXACT_ID",
            }
        },
    }))
    path = tmp_path / "revival.json"
    path.write_text(json.dumps({
        "coins": [
            {"id": "old", "network": "solana", "token_address": "MintA", "source": "coingecko"},
            {"id": "new", "network": "solana", "token_address": "MintB", "source": "coingecko"},
        ],
        "counts": {},
    }))
    def unavailable(_ids):
        raise RuntimeError("upstream HTTP 403")
    monkeypatch.setattr(g, "fetch_by_ids", unavailable)
    report = g.enforce_revival(path)
    coins = json.loads(path.read_text())["coins"]
    assert report["provider_degraded"] is True
    assert report["verified_cache_hits"] == 1
    assert report["accepted"] == 1
    assert [coin["token_address"] for coin in coins] == ["MintA"]
    assert coins[0]["market_age_evidence_source"].startswith("CACHED_")
    assert "price_usd" not in coins[0]


def test_revival_does_not_transfer_cached_age_to_another_mint_or_chain(tmp_path, monkeypatch):
    """Never turn a correct ID's prior token-age proof into another token's."""
    monkeypatch.setattr(g, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(g, "DATA", tmp_path)
    (tmp_path / "cache.json").write_text(json.dumps({
        "version": 2, "coins": {
            "old": {
                "coingecko_id": "old", "network": "solana", "token_address": "MintA",
                "market_age_verified": True,
                "market_age_evidence_at": old_date(400),
                "market_age_evidence_source": "COINGECKO_ATH_OR_ATL_HISTORICAL_EVIDENCE_EXACT_ID",
            },
        },
    }))
    path = tmp_path / "revival.json"
    path.write_text(json.dumps({
        "coins": [
            {"id": "old", "network": "solana", "token_address": "DifferentMint", "source": "coingecko"},
            {"id": "old", "network": "ethereum", "token_address": "MintA", "source": "coingecko"},
        ], "counts": {},
    }))
    monkeypatch.setattr(g, "fetch_by_ids", lambda _ids: (_ for _ in ()).throw(RuntimeError("HTTP 403")))
    report = g.enforce_revival(path)
    assert report["accepted"] == 0
    assert report["rejected"] == 2
    assert json.loads(path.read_text())["coins"] == []


def test_revival_rejects_unbound_legacy_cache_for_exact_mint(tmp_path, monkeypatch):
    """Old cache rows with no mint are insufficient to confirm a current token."""
    monkeypatch.setattr(g, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(g, "DATA", tmp_path)
    (tmp_path / "cache.json").write_text(json.dumps({
        "version": 1, "coins": {
            "old": {
                "coingecko_id": "old", "market_age_verified": True,
                "market_age_evidence_at": old_date(500),
                "market_age_evidence_source": "COINGECKO_ATH_OR_ATL_HISTORICAL_EVIDENCE_EXACT_ID",
            }
        },
    }))
    path = tmp_path / "revival.json"
    path.write_text(json.dumps({
        "coins": [{"id": "old", "network": "solana", "token_address": "MintA", "source": "coingecko"}],
        "counts": {},
    }))
    monkeypatch.setattr(g, "fetch_by_ids", lambda _ids: (_ for _ in ()).throw(RuntimeError("HTTP 403")))
    assert g.enforce_revival(path)["accepted"] == 0
