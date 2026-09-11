import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500.real_alerts import build, run


def write(p: Path, name: str, payload):
    (p / name).write_text(json.dumps(payload), encoding="utf-8")


def base_cex(status="DEX_VERIFIED", liq=120000):
    verified = str(status).startswith("DEX_VERIFIED")
    return {
        "symbol": "OLDUSDT",
        "cex_revival_score": 58,
        "coherent_confirmations": 4,
        "market_age_verified": True,
        "market_age_min_days": 900,
        "identity_status": status,
        "identity_verified": verified,
        "chain": "solana" if verified else None,
        "token_address": "Mint111111111111111111111111111111111111111" if verified else None,
        "pair_address": "Pair111111111111111111111111111111111111111" if verified else None,
        "dex_liquidity_usd": liq,
        "dex_price_usd": 0.12,
        "milestones": {"first_alert": {"observed_at": "2026-09-02T10:00:00+00:00"}},
    }


def precursor(status="PRE_BREAKOUT_CANDIDATE"):
    return {
        "network": "solana",
        "token_address": "Mint111111111111111111111111111111111111111",
        "pair_address": "Pair111111111111111111111111111111111111111",
        "symbol": "OLD",
        "status": status,
        "market_age_verified": True,
        "market_age_min_days": 900,
        "identity": {"exact_mint_verified": True, "exact_pair_verified": True},
        "normalized_score_available_evidence": 72,
        "t0": {"observed_at": "2026-09-02T09:59:00+00:00"},
    }


def seed(tmp_path, cex_rows=None, precursor_rows=None, active=None, spot_rows=None, multichain_rows=None):
    write(tmp_path, "cex-revival-radar.json", {"alerts": cex_rows or []})
    stamp = datetime.now(timezone.utc).isoformat()
    write(tmp_path, "cex-spot-identity-radar.json", {"generated_at": stamp, "candidates": spot_rows or []})
    write(tmp_path, "multichain-veteran-revival.json", {"generated_at": stamp, "veteran_watch": multichain_rows or [], "dna_watch": []})
    write(tmp_path, "revival-precursor-latest.json", {"targets": precursor_rows or []})
    write(tmp_path, "waking-confirmation-latest.json", {"targets": []})
    write(tmp_path, "revival-1000-latest.json", {"coins": []})
    write(tmp_path, "candidate-evidence-envelope.json", {"candidates": []})
    write(tmp_path, "active-qualified-candidates.json", active or [])


def test_exact_old_coin_with_two_lanes_becomes_real_alert(tmp_path):
    seed(tmp_path, [base_cex()], [precursor()])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 1
    row = result["alerts"][0]
    assert row["status"] == "REAL_ALERT"
    assert row["market_age_days"] >= 180
    assert row["exact_identity_verified"] is True
    assert row["exact_pair_verified"] is True
    assert set(row["source_lanes"]) >= {"CEX_REVIVAL", "REVIVAL_PRECURSOR"}


def test_cex_only_never_becomes_real_alert(tmp_path):
    seed(tmp_path, [base_cex()], [])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert result["counts"]["pre_wave_alerts"] == 0
    assert result["counts"]["verified_watch_not_real"] == 1
    assert "INDEPENDENT_CONFIRMATION_LT_2" in result["verified_watch"][0]["blockers"]


def test_unresolved_identity_is_visible_but_not_actionable(tmp_path):
    seed(tmp_path, [base_cex(status="IDENTITY_PENDING")], [])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert result["counts"]["identity_pending_not_actionable"] == 1
    assert result["identity_pending"][0]["actionable_research_alert"] is False


def test_under_180_days_fails_closed(tmp_path):
    cex = base_cex()
    cex["market_age_min_days"] = 179
    p = precursor()
    p["market_age_min_days"] = 179
    seed(tmp_path, [cex], [p])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert result["counts"]["verified_watch_not_real"] == 0


def test_late_move_never_becomes_real_alert(tmp_path):
    seed(tmp_path, [base_cex()], [precursor(status="LATE_MOVE_DO_NOT_CHASE")])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert any("LATE_MOVE_DO_NOT_CHASE" in x["blockers"] for x in result["verified_watch"])


def test_total_liquidity_over_50k_cannot_rescue_thin_execution_pool(tmp_path):
    cex = base_cex(liq=8_700)
    cex["execution_pool_liquidity_usd"] = 8_700
    cex["dex_total_liquidity_usd"] = 120_000
    seed(tmp_path, [cex], [precursor()])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    row = result["verified_watch"][0]
    assert row["execution_pool_liquidity_usd"] == 8_700
    assert row["dex_total_liquidity_usd"] == 120_000
    assert "EXECUTION_POOL_LIQUIDITY_LT_50K" in row["blockers"]


def test_deep_exact_execution_pool_over_50k_passes_even_if_stale_thin_row_exists(tmp_path):
    cex = base_cex(liq=1_100_000)
    cex["pair_address"] = "DeepPair11111111111111111111111111111111111"
    cex["execution_pool_liquidity_usd"] = 1_100_000
    cex["dex_total_liquidity_usd"] = 1_108_700
    cex["liquidity_gate_metric"] = "EXECUTION_POOL_LIQUIDITY_USD"

    stale = {
        "qualification": "QUALIFIED",
        "chain": "solana",
        "token": "Mint111111111111111111111111111111111111111",
        "pair_address": "ThinPair11111111111111111111111111111111111",
        "liquidity_usd": 8_700,
        "market_age_verified": True,
        "market_age_min_days": 900,
    }
    seed(tmp_path, [cex], [precursor()], [stale])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 1
    row = result["alerts"][0]
    assert row["pair_address"] == cex["pair_address"]
    assert row["execution_pool_liquidity_usd"] == 1_100_000
    assert row["dex_total_liquidity_usd"] == 1_108_700
    assert row["liquidity_gate_metric"] == "EXECUTION_POOL_LIQUIDITY_USD"


def test_run_sanitizes_concentrated_pool_before_real_alert_file_is_publishable(tmp_path):
    cex = base_cex(status="DEX_VERIFIED_DORMANT", liq=143_345.3)
    cex.update({
        "dex": "Meteora",
        "execution_pool_liquidity_usd": 143_345.3,
        "dex_volume_h24": 100_000,
        "dex_volume_h1": 5_000,
    })
    seed(tmp_path, [cex], [precursor()])

    counts = run(tmp_path)
    payload = json.loads((tmp_path / "real-alerts.json").read_text(encoding="utf-8"))

    assert counts["real_alerts"] == 0
    assert payload["truth_contract"]["producer_liquidity_sanitized_before_publish"] is True
    assert payload["truth_contract"]["pool_tvl_never_equals_execution_depth"] is True
    assert payload["verified_watch"]
    row = payload["verified_watch"][0]
    assert row["execution_pool_liquidity_usd"] is None
    assert row["liquidity_usd"] is None
    assert row["pool_tvl_usd"] == 143_345.3
    assert "EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL" in row["blockers"]


def test_pair_metadata_is_atomic_and_never_mixes_dex_from_other_pool(tmp_path):
    mint = "Mint111111111111111111111111111111111111111"
    ray_pair = "RayPair111111111111111111111111111111111111"
    met_pair = "MetPair111111111111111111111111111111111111"

    cex = base_cex(liq=90_000)
    cex.update({
        "pair_address": met_pair,
        "dex": "meteora",
        "dex_url": f"https://dexscreener.com/solana/{met_pair}",
        "execution_pool_liquidity_usd": 90_000,
    })
    p = precursor(status="INSUFFICIENT_PRECURSOR_EVIDENCE")
    p.update({
        "pair_address": ray_pair,
        "dex": "raydium",
        "dex_url": f"https://dexscreener.com/solana/{ray_pair}",
        "execution_pool_liquidity_usd": 1_000_000,
        "dex_liquidity_usd": 1_000_000,
    })
    seed(tmp_path, [cex], [p])

    result = build(tmp_path)
    assert result["verified_watch"]
    row = result["verified_watch"][0]
    assert row["pair_address"] == ray_pair
    assert row["dex"] == "raydium"
    assert ray_pair in row["dex_url"]
    assert met_pair not in row["dex_url"]
    assert row["pair_metadata_atomic"] is True
    assert row["readiness_gates"]["EXECUTION_LIQUIDITY"] is True
    assert set(row["missing_gates"]) == {"STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION"}


STORJ = "0xb64ef51c888972c908cfacf59b47c1afbc0ab8ac"
STORJ_PAIR = "0xAEF16913b6C50EBCf627a394921F306985FC8604"


def storj_cex():
    return {
        "symbol": "STORJUSDT",
        "cex_revival_score": 37,
        "coherent_confirmations": 4,
        "market_age_verified": True,
        "market_age_min_days": 1993,
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "chain": "ethereum",
        "token_address": STORJ,
        "pair_address": STORJ_PAIR,
        "dex": "uniswap",
        "dex_url": f"https://dexscreener.com/ethereum/{STORJ_PAIR.lower()}",
        "execution_pool_liquidity_usd": 79_651.61,
        "dex_total_liquidity_usd": 79_651.61,
        "dex_price_usd": 0.03276,
        "dex_volume_h1": 4_522.59,
        "dex_volume_h24": 42_000.0,
        "buys_h1": 24,
        "sells_h1": 17,
        "concentrated_liquidity_pool": False,
        "milestones": {"first_alert": {"observed_at": "2026-09-11T08:02:55.382064+00:00"}},
    }


def storj_spot(change24=2.28):
    return {
        "symbol": "STORJUSDT",
        "spot_revival_score": 38,
        "status": "CEX_SPOT_EXACT_IDENTITY_RESEARCH",
        "research_only": True,
        "actionable": False,
        "leveraged_product": False,
        "coherent_confirmations": 4,
        "coherent_feature_hits": ["PRICE_ACCEL", "VOLUME_ACCEL"],
        "change_24h_max_pct": change24,
        "price_acceleration_max_pct": 2.2876,
        "volume_acceleration_max_pct": 8.7315,
        "exchanges": ["gate", "kucoin", "mexc", "okx"],
        "market_age_verified": True,
        "market_age_min_days": 1993,
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "chain": "ethereum",
        "token_address": STORJ,
        "pair_address": STORJ_PAIR,
        "dex": "uniswap",
        "dex_url": f"https://dexscreener.com/ethereum/{STORJ_PAIR.lower()}",
        "execution_pool_liquidity_usd": 79_651.61,
        "dex_price_usd": 0.03276,
        "dex_volume_h1": 4_522.59,
        "dex_volume_h24": 42_000.0,
        "buys_h1": 24,
        "sells_h1": 17,
        "concentrated_liquidity_pool": False,
        "milestones": {"first_watch": {"observed_at": "2026-09-06T09:41:49.288906+00:00"}},
    }


def storj_multichain(status="VETERAN_RESEARCH_WATCH", blockers=None, h24=2.3):
    return {
        "chain": "ethereum",
        "token": STORJ,
        "symbol": "STORJ",
        "pair_address": STORJ_PAIR,
        "dex": "uniswap",
        "url": f"https://dexscreener.com/ethereum/{STORJ_PAIR.lower()}",
        "price_usd": 0.03276,
        "token_identity_verified": True,
        "market_age_verified": True,
        "market_age_min_days": 1993,
        "liquidity_usd": 79_651.61,
        "volume_h1": 4_522.59,
        "volume_h24": 42_000.0,
        "price_change_h1": 1.8,
        "price_change_h24": h24,
        "buys_h1": 24,
        "sells_h1": 17,
        "status": status,
        "winner_dna_score_research": 61 if status == "DNA_WATCH_RESEARCH" else 55,
        "blockers": ["VOLUME_H1_LT_15K"] if blockers is None else blockers,
        "chase_risk": False,
        "real_time_gate": {
            "live_liquidity_usd": 79_651.61,
            "volume_h1_usd": 4_522.59,
            "txns_h1": 41,
            "buy_sell_ratio_h1": 24 / 17,
            "turnover_h1": 4_522.59 / 79_651.61,
            "price_change_h1_pct": 1.8,
            "price_change_h24_pct": h24,
        },
    }


def test_storj_style_5_of_7_becomes_pre_wave_without_weakening_real_alert(tmp_path):
    seed(
        tmp_path,
        cex_rows=[storj_cex()],
        spot_rows=[storj_spot()],
        multichain_rows=[storj_multichain()],
    )
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert result["counts"]["pre_wave_alerts"] == 1
    row = result["pre_wave_alerts"][0]
    assert row["status"] == "PRE_WAVE_ALERT"
    assert row["user_alert_eligible"] is True
    assert row["manual_decision_only"] is True
    assert row["automatic_buy"] is False
    assert row["actionable_research_alert"] is False
    assert row["pre_wave_gates"]["cex_spot_breadth"] is True
    assert row["pre_wave_gates"]["multichain_market_activity"] is True
    assert set(row["full_real_alert_pending_gates"]) == {"STRONG_DECISION_LANE"}
    assert "CEX_SPOT_BREADTH" in row["source_lanes"]
    assert "CEX_REVIVAL" in row["source_lanes"]


def test_pre_wave_fails_closed_once_move_is_already_late(tmp_path):
    seed(
        tmp_path,
        cex_rows=[storj_cex()],
        spot_rows=[storj_spot(change24=61.14)],
        multichain_rows=[storj_multichain(h24=61.14)],
    )
    result = build(tmp_path)
    assert result["counts"]["pre_wave_alerts"] == 0
    assert result["counts"]["real_alerts"] == 0


def test_multichain_dna_plus_spot_and_cex_can_complete_strong_decision_lane(tmp_path):
    m = storj_multichain(status="DNA_WATCH_RESEARCH", blockers=[])
    m["winner_dna_score_research"] = 78
    seed(tmp_path, cex_rows=[storj_cex()], spot_rows=[storj_spot()], multichain_rows=[m])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 1
    row = result["alerts"][0]
    assert set(row["source_lanes"]) >= {"CEX_REVIVAL", "CEX_SPOT_BREADTH", "MULTICHAIN_VETERAN_REVIVAL"}
    assert row["readiness_passed"] == 7
