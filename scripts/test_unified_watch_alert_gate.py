from scripts.unified_watch_engine import alpha_telegram_gate, quarter_wave_revalidation


POLICY = {
    "alpha_close_watch_require_confirmation": True,
    "alpha_min_confirmations_for_telegram": 1,
    "alpha_min_fusion_score_for_telegram": 12.0,
    "alpha_min_positive_families_for_telegram": 2,
    "alpha_wallet_holder_score_for_telegram": 3.0,
    "alpha_min_volume_h1_for_telegram": 5000.0,
    "alpha_min_buys_h1_for_telegram": 15,
    "alpha_min_buy_sell_ratio_for_telegram": 2.0,
}


def live(volume=1000.0, buys=11, sells=6):
    return {"volume_h1": volume, "buys_h1": buys, "sells_h1": sells}


def fusion(score=0.8, families=1, notable=None, family_scores=None, hard_risks=None):
    return {
        "score": score,
        "families": families,
        "notable_evidence": notable or [],
        "family_scores": family_scores or {},
        "hard_risks": hard_risks or [],
    }


def check(expected, *, l=None, f=None, triggers=None, reasons=None, risk=False):
    ok, confirmations = alpha_telegram_gate(
        l or live(),
        f or fusion(),
        triggers or ["PRICE_PLUS_VOLUME_ACCELERATION"],
        reasons or ["FIRST_MATERIAL_TRIGGER"],
        risk,
        POLICY,
    )
    assert ok is expected, (ok, confirmations)
    return confirmations


# Screenshot-like case: market twitch only, 0.8/100, one family, ~$1K volume.
assert check(False) == []

# A second independent intelligence family is enough to reopen Telegram.
assert check(True, f=fusion(families=2))

# Material social/search/news evidence is enough even before a high fusion score.
assert check(True, f=fusion(notable=["attention_social:mention_velocity:1"]))
assert check(True, f=fusion(notable=["search_discovery:search_acceleration:1"]))
assert check(True, f=fusion(notable=["catalyst_news:official_announcement:1"]))

# Stronger market confirmation can independently reopen the alert gate.
assert check(True, l=live(volume=6000.0))
assert check(True, l=live(volume=1200.0, buys=20, sells=5), triggers=["ALPHA_CALL_PLUS_BUY_IMBALANCE"])

# Wallet/holder evidence and a meaningful fusion score both qualify.
assert check(True, f=fusion(family_scores={"wallet_flow": 3.5}))
assert check(True, f=fusion(score=14.0))

# Risk alerts must never be hidden by the noise gate.
assert check(True, risk=True) == ["RISK_BYPASS"]

# +25% CEX revalidation uses an immutable verified-price anchor and stays armed.
q1 = quarter_wave_revalidation({}, 0.00010000, "2026-09-20T10:00:00+00:00")
assert q1["first_verified_price"] == 0.00010000
assert q1["quarter_wave_revalidation_armed"] is False

q2 = quarter_wave_revalidation(q1, 0.00012499, "2026-09-20T10:10:00+00:00")
assert q2["quarter_wave_revalidation_armed"] is False
assert q2["first_verified_price"] == q1["first_verified_price"]

q3 = quarter_wave_revalidation(q2, 0.00012500, "2026-09-20T10:20:00+00:00")
assert q3["quarter_wave_revalidation_armed"] is True
assert round(q3["gain_from_first_verified_pct"], 4) == 25.0
assert q3["quarter_wave_revalidation_trigger_price"] == 0.00012500

q4 = quarter_wave_revalidation(q3, 0.00011500, "2026-09-20T10:30:00+00:00")
assert q4["quarter_wave_revalidation_armed"] is True
assert q4["first_verified_price"] == 0.00010000
assert q4["quarter_wave_revalidation_trigger_price"] == 0.00012500

print("UNIFIED_WATCH_ALPHA_ALERT_GATE_PASS")
