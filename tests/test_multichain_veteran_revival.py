import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500 import multichain_veteran_revival as mvr


def _old_ms(days=220):
    now = datetime(2026, 9, 4, tzinfo=timezone.utc).timestamp()
    return int((now - days * 86400) * 1000)


def _snapshot(chain, token, *, liq=100000, vol=60000, buys=240, sells=120, h1=8, h24=15, age_days=220):
    return {
        "chain": chain,
        "token": token,
        "pair_address": "0xpair" if chain != "solana" else "Pair111",
        "dex": "testdex",
        "price_usd": 0.01,
        "token_identity_verified": True,
        "target_token_side": "BASE",
        "liquidity_usd": liq,
        "volume_h1": vol,
        "volume_h24": vol * 5,
        "buys_h1": buys,
        "sells_h1": sells,
        "price_change_h1": h1,
        "price_change_h24": h24,
        "pair_created_at": _old_ms(age_days),
    }


def test_evm_identity_key_is_chain_scoped_and_case_insensitive():
    token = "0xAbC0000000000000000000000000000000000001"
    assert mvr._key("arbitrum", token) == mvr._key("arbitrum", token.lower())
    assert mvr._key("arbitrum", token) != mvr._key("base", token)


def test_arbitrum_veteran_can_be_dna_watch_without_changing_production():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    token = "0x1230000000000000000000000000000000000456"
    row = {"chain": "arbitrum", "token": token, "symbol": "TEST", "discovery_sources": ["geckoterminal:trending_pools"]}
    result = mvr._score(
        row,
        _snapshot("arbitrum", token),
        now,
        {"volume_h1": 30000, "liquidity_usd": 100000},
        {"verified": True, "reason": "EXACT_REGISTRY_IDENTITY_PLUS_CEX_SPOT_WATCH"},
    )
    assert result["blockers"] == []
    assert result["status"] == "DNA_WATCH_RESEARCH"
    assert result["winner_dna_score_research"] >= mvr.WATCH_SCORE
    assert result["actionable"] is False
    assert result["production_portfolio_impact"] == "NONE"


def test_unknown_or_under_180d_age_fails_closed():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    token = "0x4560000000000000000000000000000000000789"
    row = {"chain": "base", "token": token, "symbol": "TEST"}
    result = mvr._score(row, _snapshot("base", token, age_days=30), now, None, {"verified": False})
    assert "PAIR_AGE_LT_180D_OR_UNKNOWN" in result["blockers"]
    assert result["status"] == "INELIGIBLE_FAIL_CLOSED"


def test_missing_pair_creation_time_is_unknown_not_epoch_veteran():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    token = "0x4570000000000000000000000000000000000789"
    row = {"chain": "base", "token": token, "symbol": "TEST"}
    snap = _snapshot("base", token)
    snap["pair_created_at"] = None
    result = mvr._score(row, snap, now, None, {"verified": False})
    assert result["market_age_verified"] is False
    assert "PAIR_AGE_LT_180D_OR_UNKNOWN" in result["blockers"]


def test_exact_registry_age_can_prove_veteran_when_current_pair_is_newer():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    token = "0x4580000000000000000000000000000000000789"
    row = {
        "chain": "arbitrum",
        "token": token,
        "symbol": "TEST",
        "registry_identity_verified": True,
        "market_age_evidence_at": "2026-02-01T00:00:00Z",
        "market_age_evidence_source": "EXACT_REGISTRY_FIXTURE",
    }
    result = mvr._score(row, _snapshot("arbitrum", token, age_days=30), now, None, {"verified": False})
    assert result["market_age_verified"] is True
    assert result["market_age_pair_days"] < 180
    assert result["market_age_registry_days"] > 180
    assert result["market_age_evidence_source"] == "EXACT_REGISTRY_FIXTURE"
    assert "PAIR_AGE_LT_180D_OR_UNKNOWN" not in result["blockers"]


def test_unverified_row_cannot_spoof_registry_age():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    token = "0x4590000000000000000000000000000000000789"
    row = {
        "chain": "arbitrum",
        "token": token,
        "symbol": "TEST",
        "market_age_evidence_at": "2020-01-01T00:00:00Z",
    }
    result = mvr._score(row, _snapshot("arbitrum", token, age_days=30), now, None, {"verified": False})
    assert result["market_age_registry_days"] is None
    assert "PAIR_AGE_LT_180D_OR_UNKNOWN" in result["blockers"]


def test_live_liquidity_floor_never_relaxed():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    token = "0x7890000000000000000000000000000000000123"
    row = {"chain": "ethereum", "token": token, "symbol": "TEST"}
    result = mvr._score(row, _snapshot("ethereum", token, liq=49999), now, None, {"verified": False})
    assert "LIVE_LIQUIDITY_LT_50K" in result["blockers"]
    assert result["status"] == "INELIGIBLE_FAIL_CLOSED"


def test_wrapped_and_stable_assets_are_excluded():
    assert mvr._blocked("base", "0x4200000000000000000000000000000000000006", "WETH")
    assert mvr._blocked("arbitrum", "0xaf88d065e77c8cc2239327c5edb3a432268e5831", "USDC")
    assert not mvr._blocked("arbitrum", "0x9990000000000000000000000000000000000999", "REAL")


def test_spot_confirmation_requires_exact_registry_chain_and_contract(tmp_path: Path):
    token = "0xabc0000000000000000000000000000000000001"
    (tmp_path / "cex-identity-registry.json").write_text(
        '{"symbols":{"IDOS":{"chain":"arbitrum","token_address":"0xabc0000000000000000000000000000000000001"}}}',
        encoding="utf-8",
    )
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        '{"watchlist":[{"symbol":"IDOSUSDT","spot_revival_score":82,"exchanges":["gate"],"coherent_confirmations":1}]}',
        encoding="utf-8",
    )
    confirmed = mvr._spot_exact_confirmation(tmp_path, "arbitrum", token.upper())
    assert confirmed["verified"] is True
    assert confirmed["symbol"] == "IDOS"
    wrong_chain = mvr._spot_exact_confirmation(tmp_path, "base", token)
    assert wrong_chain["verified"] is False


def test_exact_spot_watch_injects_registry_contract_even_if_not_trending(tmp_path: Path):
    token = "0x68731d6f14b827bbcffbebb62b19daa18de1d79c"
    (tmp_path / "cex-identity-registry.json").write_text(
        json.dumps({
            "symbols": {
                "IDOS": {
                    "chain": "arbitrum",
                    "token_address": token,
                    "coingecko_id": "idos",
                    "market_age_evidence_at": "2026-03-05T00:00:00Z",
                    "evidence_source": "EXACT_IDOS_FIXTURE",
                }
            }
        }),
        encoding="utf-8",
    )
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        json.dumps({"watchlist": [{"symbol": "IDOSUSDT", "spot_revival_score": 51}]}),
        encoding="utf-8",
    )
    rows = mvr._discover_spot_registry_candidates(tmp_path)
    assert len(rows) == 1
    assert rows[0]["chain"] == "arbitrum"
    assert rows[0]["token"] == token
    assert rows[0]["registry_identity_verified"] is True
    assert rows[0]["discovery_sources"] == ["cex-spot-exact-registry-trigger"]


def test_unregistered_spot_symbol_never_injects_candidate(tmp_path: Path):
    (tmp_path / "cex-identity-registry.json").write_text(
        '{"symbols":{"IDOS":{"chain":"arbitrum","token_address":"0x68731d6f14b827bbcffbebb62b19daa18de1d79c"}}}',
        encoding="utf-8",
    )
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        '{"watchlist":[{"symbol":"FAKEUSDT","spot_revival_score":99}]}',
        encoding="utf-8",
    )
    assert mvr._discover_spot_registry_candidates(tmp_path) == []


def test_registry_candidate_keeps_exact_chain_scope(tmp_path: Path):
    token = "0x68731d6f14b827bbcffbebb62b19daa18de1d79c"
    (tmp_path / "cex-identity-registry.json").write_text(
        json.dumps({"symbols": {"IDOS": {"chain": "arbitrum", "token_address": token}}}),
        encoding="utf-8",
    )
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        '{"watchlist":[{"symbol":"IDOS_USDT","spot_revival_score":51}]}',
        encoding="utf-8",
    )
    rows = mvr._discover_spot_registry_candidates(tmp_path)
    assert rows[0]["chain"] == "arbitrum"
    assert mvr._key(rows[0]["chain"], rows[0]["token"]) != mvr._key("base", token)


def test_run_keeps_all_output_research_only(tmp_path: Path, monkeypatch):
    token = "0xdef0000000000000000000000000000000000002"
    monkeypatch.setattr(
        mvr,
        "discover_core_candidates",
        lambda data_dir=mvr.DATA: ([{"chain": "base", "token": token, "symbol": "TEST", "discovery_sources": ["fixture"]}], []),
    )
    monkeypatch.setattr(mvr, "market_snapshot", lambda chain, address: _snapshot(chain, address))
    payload = mvr.run(tmp_path, "2026-09-04T00:00:00+00:00")
    assert payload["mode"] == "RESEARCH_ONLY_CORE_MULTICHAIN_VETERAN_REVIVAL_V2"
    assert payload["policy"]["production_portfolio_impact"] == "NONE"
    assert payload["core_chains"] == ["solana", "ethereum", "bsc", "arbitrum", "base"]
    assert payload["veteran_gate_pass"] == 1
    assert (tmp_path / "multichain-veteran-revival.json").exists()
