from pathlib import Path


def replace_required(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise SystemExit(f"PATTERN_MISSING:{path}:{old[:80]}")
    p.write_text(text.replace(old, new), encoding="utf-8")


# Recovery V2 must use the same canonical veteran policy as Revival Radar.
replace_required(
    "src/wallet500/reawakening_shadow.py",
    "MIN_MARKET_AGE_DAYS = 60",
    "MIN_MARKET_AGE_DAYS = 90",
)
replace_required(
    "src/wallet500/reawakening_shadow.py",
    '"veteran_age_verified_60d_plus"',
    '"veteran_age_verified_90d_plus"',
)

# Keep the regression boundary aligned with the production/research policy.
replace_required(
    "tests/test_reawakening_shadow.py",
    "def test_reawakening_age_gate_is_fail_closed_at_60_days():",
    "def test_reawakening_age_gate_is_fail_closed_at_90_days():",
)
replace_required(
    "tests/test_reawakening_shadow.py",
    'young["first_reject_snapshot"]["market_age_min_days"] = 59',
    'young["first_reject_snapshot"]["market_age_min_days"] = 89',
)
replace_required(
    "tests/test_reawakening_shadow.py",
    'boundary["first_reject_snapshot"]["market_age_min_days"] = 60',
    'boundary["first_reject_snapshot"]["market_age_min_days"] = 90',
)

# Near-Recovery is not allowed to surface stale/mismatched exact-pair rows or deep-collapse rows.
dash = Path("src/wallet500/reawakening_dashboard.py")
text = dash.read_text(encoding="utf-8")
old_import = "    MIN_CONFIRMATION_SPAN_MINUTES,\n    MIN_LIQUIDITY_RETENTION,\n    MIN_LIQUIDITY_USD,\n    MIN_MARKET_AGE_DAYS,\n"
new_import = "    MAX_GAIN_SINCE_REJECT_PCT,\n    MIN_CONFIRMATION_SPAN_MINUTES,\n    MIN_GAIN_SINCE_REJECT_PCT,\n    MIN_LIQUIDITY_RETENTION,\n    MIN_LIQUIDITY_USD,\n    MIN_MARKET_AGE_DAYS,\n"
if old_import in text:
    text = text.replace(old_import, new_import)
elif new_import not in text:
    raise SystemExit("REAWAKENING_DASH_IMPORT_PATTERN_MISSING")

old_filter = '''        liquidity_recovered_for_watch = _f(metrics.get("liquidity_usd")) >= MIN_LIQUIDITY_USD
        activity_returning = activity_passed >= 1
        if (
            not market_age_verified
            or market_age_days < MIN_MARKET_AGE_DAYS
            or not liquidity_recovered_for_watch
            or not activity_returning
        ):
            continue
'''
new_filter = '''        liquidity_recovered_for_watch = _f(metrics.get("liquidity_usd")) >= MIN_LIQUIDITY_USD
        activity_returning = activity_passed >= 1
        exact_pair_current = _same_pair(chain, latest.get("pair_address"), pair)
        gain_since_reject_pct = _f(metrics.get("gain_since_reject_pct"), -10_000.0)
        anti_chase_window = MIN_GAIN_SINCE_REJECT_PCT <= gain_since_reject_pct <= MAX_GAIN_SINCE_REJECT_PCT
        if (
            not market_age_verified
            or market_age_days < MIN_MARKET_AGE_DAYS
            or not liquidity_recovered_for_watch
            or not activity_returning
            or not exact_pair_current
            or not anti_chase_window
        ):
            continue
'''
if old_filter in text:
    text = text.replace(old_filter, new_filter)
elif "exact_pair_current = _same_pair" not in text or "anti_chase_window =" not in text:
    raise SystemExit("REAWAKENING_DASH_FILTER_PATTERN_MISSING")

old_rule = '''        "rule": {
            "liquidity_floor_usd": 15000,
            "exact_pair_locked": True,
'''
new_rule = '''        "rule": {
            "minimum_market_age_days": 90,
            "liquidity_floor_usd": 15000,
            "near_recovery_requires_current_exact_pair": True,
            "near_recovery_requires_anti_chase_window": True,
            "near_recovery_requires_returning_activity": True,
            "exact_pair_locked": True,
'''
if old_rule in text:
    text = text.replace(old_rule, new_rule)
elif '"minimum_market_age_days": 90' not in text:
    raise SystemExit("REAWAKENING_DASH_RULE_PATTERN_MISSING")
dash.write_text(text, encoding="utf-8")

# The scheduled Recovery workflow must validate the canonical 90d / $15k contract,
# otherwise every future rebuild can fail and leave yesterday's stale dashboard feed visible.
wf = Path(".github/workflows/reawakening-shadow.yml")
text = wf.read_text(encoding="utf-8")
text = text.replace(
    "if float(recovery.get('liquidity_gte_usd') or 0) != 50000.0: raise SystemExit('LIQUIDITY_HARD_FLOOR_CHANGED')",
    "if float(recovery.get('liquidity_gte_usd') or 0) != 15000.0: raise SystemExit('RECOVERY_LIQUIDITY_POLICY_DRIFT')",
)
anchor = "          if recovery.get('exact_pair_locked') is not True: raise SystemExit('EXACT_PAIR_LOCK_MISSING')\n"
age_check = "          if float((db.get('rule') or {}).get('minimum_market_age_days') or 0) != 90.0: raise SystemExit('RECOVERY_AGE_POLICY_DRIFT')\n"
if age_check not in text:
    if anchor not in text:
        raise SystemExit("REAWAKENING_WORKFLOW_VALIDATION_ANCHOR_MISSING")
    text = text.replace(anchor, age_check + anchor)
wf.write_text(text, encoding="utf-8")

print("RECOVERY_WATCH_90D_15K_REPAIR_READY")
