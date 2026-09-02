from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from wallet500 import mature_age_gate as g


def old_date(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


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
    assert out["alerts"][0]["market_age_min_days"] >= 180


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
    assert all(x["market_age_min_days"] >= 180 for x in out["coins"])
    assert out["counts"]["age_verified_180d_plus"] == 2
    assert out["counts"]["age_gate_rejected"] == 1


def test_validate_file_fails_closed_on_unverified_row(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({
        "age_gate": {"status": "ENFORCED_FAIL_CLOSED", "minimum_market_age_days": 180},
        "alerts": [{"symbol": "X", "market_age_verified": False, "market_age_min_days": 0}],
    }))
    try:
        g.validate_file(p, "alerts")
    except SystemExit as exc:
        assert "MATURE_AGE_GATE_VIOLATION" in str(exc)
    else:
        raise AssertionError("validate_file must fail closed")
