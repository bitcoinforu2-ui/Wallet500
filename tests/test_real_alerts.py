import json
from pathlib import Path

from wallet500.real_alerts import build


def write(p: Path, name: str, payload):
    (p / name).write_text(json.dumps(payload), encoding="utf-8")


def base_cex(status="DEX_VERIFIED", liq=120000):
    return {
        "symbol": "OLDUSDT",
        "cex_revival_score": 58,
        "coherent_confirmations": 4,
        "market_age_verified": True,
        "market_age_min_days": 900,
        "identity_status": status,
        "identity_verified": status == "DEX_VERIFIED",
        "chain": "solana" if status == "DEX_VERIFIED" else None,
        "token_address": "Mint111111111111111111111111111111111111111" if status == "DEX_VERIFIED" else None,
        "pair_address": "Pair111111111111111111111111111111111111111" if status == "DEX_VERIFIED" else None,
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


def seed(tmp_path, cex_rows=None, precursor_rows=None, active=None):
    write(tmp_path, "cex-revival-radar.json", {"alerts": cex_rows or []})
    write(tmp_path, "revival-precursor-latest.json", {"targets": precursor_rows or []})
    write(tmp_path, "waking-confirmation-latest.json", {"targets": []})
    write(tmp_path, "revival-1000-latest.json", {"coins": []})
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
    cex["market_age_min_days"] = 90
    p = precursor()
    p["market_age_min_days"] = 90
    seed(tmp_path, [cex], [p])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert "VERIFIED_MARKET_AGE_180D_REQUIRED" in result["verified_watch"][0]["blockers"]


def test_late_move_never_becomes_real_alert(tmp_path):
    seed(tmp_path, [base_cex()], [precursor(status="LATE_MOVE_DO_NOT_CHASE")])
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert any("LATE_MOVE_DO_NOT_CHASE" in x["blockers"] for x in result["verified_watch"])
