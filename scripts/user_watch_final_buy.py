from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
WATCH_STATE = ROOT / "data/unified-watch-state.json"
WATCH_REPORT = ROOT / "data/unified-watch-intelligence-report.json"
STATE = ROOT / "data/user-watch-final-buy-state.json"
REPORT = ROOT / "data/user-watch-final-buy-report.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
POLICY_MODE = "USER_REQUESTED_UNIFIED_WATCH_FINAL_BUY_V1"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def num(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError, OverflowError):
        return default


def parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def age_seconds(value: Any, now: datetime) -> float | None:
    dt = parse_dt(value)
    if dt is None:
        return None
    return (now - dt).total_seconds()


def chain_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return ALIASES.get(raw, raw)


def norm(chain: str, value: Any) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def identity_key(row: dict) -> str:
    chain = chain_name(row.get("chain") or row.get("network"))
    token = norm(chain, row.get("token_address") or row.get("token") or row.get("contract") or row.get("mint"))
    pair = norm(chain, row.get("pair_address") or row.get("pair") or row.get("exact_pair"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def eligible_targets(config: dict) -> list[dict]:
    rows = []
    for row in config.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        if row.get("user_watch_final_buy_lane") is not True:
            continue
        if str(row.get("telegram_policy") or "").upper() != "FINAL_BUY_ONLY":
            continue
        if row.get("exact_identity_required") is not True or row.get("exact_pair_required") is not True:
            continue
        if identity_key(row):
            rows.append(row)
    return rows


def market_row(state: dict, key: str) -> dict | None:
    rows = state.get("tokens") if isinstance(state, dict) else {}
    if not isinstance(rows, dict):
        return None
    for row in rows.values():
        if isinstance(row, dict) and str(row.get("identity_key") or "") == key:
            return row
    return None


def report_row(report: dict, key: str) -> dict | None:
    for row in (report.get("targets") or []) if isinstance(report, dict) else []:
        if isinstance(row, dict) and str(row.get("identity_key") or "") == key:
            return row
    return None


def _policy(config: dict) -> dict:
    p = dict(config.get("user_watch_final_buy_policy") or {})
    defaults = {
        "enabled": True,
        "max_source_spread_pct": 2.0,
        "max_snapshot_age_seconds": 2100,
        "min_liquidity_usd": 50000.0,
        "min_volume_h1_usd": 15000.0,
        "min_activity_h1": 50,
        "min_buy_sell_ratio": 1.20,
        "min_rebound_from_watch_low_pct": 5.0,
        "min_scan_price_gain_pct": 1.0,
        "max_scan_price_gain_pct": 25.0,
        "strong_min_fusion_score": 55.0,
        "strong_min_positive_families": 3,
        "relaxed_min_fusion_score": 30.0,
        "relaxed_min_positive_families": 2,
        "relaxed_min_wallet_or_holder_score": 3.0,
        "min_current_evidence": 2,
        "required_consecutive_qualified_scans": 2,
        "rearm_after_observable_misses": 2,
        "telegram_final_buy_only": True,
        "automatic_trade": False,
    }
    for k, v in defaults.items():
        p.setdefault(k, v)
    return p


def evaluate(
    target: dict,
    market: dict | None,
    observed: dict | None,
    prior: dict | None,
    policy: dict,
    *,
    now: datetime | None = None,
) -> tuple[dict, dict]:
    now = (now or now_utc()).astimezone(timezone.utc)
    prior = dict(prior or {})
    key = identity_key(target)
    blockers: list[str] = []
    proof: list[str] = []

    if not key:
        blockers.append("EXACT_IDENTITY_MISSING")
    if market is None:
        blockers.append("MARKET_STATE_MISSING")
    if observed is None:
        blockers.append("WATCH_REPORT_ROW_MISSING")

    report_verified = bool(observed and observed.get("market_verified") is True)
    if not report_verified:
        blockers.append("EXACT_PAIR_NOT_VERIFIED_THIS_SCAN")

    report_age = age_seconds((observed or {}).get("observed_at") or (observed or {}).get("updated_at"), now)
    injected_report_age = num((observed or {}).get("_report_age_seconds"))
    if report_age is None:
        report_age = injected_report_age
    max_age = float(policy["max_snapshot_age_seconds"])
    if report_age is None or report_age < -120 or report_age > max_age:
        blockers.append("WATCH_REPORT_STALE_OR_UNTIMED")

    market_age = age_seconds((market or {}).get("observed_at"), now)
    if market_age is None or market_age < -120 or market_age > max_age:
        blockers.append("MARKET_SNAPSHOT_STALE_OR_UNTIMED")

    market_key = str((market or {}).get("identity_key") or "")
    if market is not None and market_key != key:
        blockers.append("MARKET_IDENTITY_MISMATCH")

    price = num((market or {}).get("price"), 0.0) or 0.0
    liquidity = num((market or {}).get("liquidity"), 0.0) or 0.0
    volume_h1 = num((market or {}).get("volume_h1"), 0.0) or 0.0
    buys = int(num((market or {}).get("buys_h1"), 0.0) or 0)
    sells = int(num((market or {}).get("sells_h1"), 0.0) or 0)
    activity = buys + sells
    ratio = (buys + 1.0) / (sells + 1.0)
    spread = num((market or {}).get("spread_pct"), 999.0) or 999.0

    if price <= 0:
        blockers.append("PRICE_MISSING")
    if spread > float(policy["max_source_spread_pct"]):
        blockers.append("PRICE_SOURCE_SPREAD_TOO_WIDE")
    if liquidity < float(policy["min_liquidity_usd"]):
        blockers.append("LIQUIDITY_BELOW_FINAL_BUY_FLOOR")
    if volume_h1 < float(policy["min_volume_h1_usd"]):
        blockers.append("VOLUME_H1_TOO_LOW")
    if activity < int(policy["min_activity_h1"]):
        blockers.append("ACTIVITY_H1_TOO_LOW")
    if ratio < float(policy["min_buy_sell_ratio"]):
        blockers.append("BUY_FLOW_NOT_CONFIRMED")

    intel = (observed or {}).get("intelligence") if isinstance((observed or {}).get("intelligence"), dict) else {}
    status = str(intel.get("status") or "").upper()
    score = num(intel.get("score"), 0.0) or 0.0
    families = int(num(intel.get("families") or intel.get("independent_positive_families"), 0.0) or 0)
    evidence = int(num(intel.get("current_evidence_count"), 0.0) or 0)
    intel_age = num(intel.get("evidence_age_minutes"))
    hard_risks = [str(x) for x in (intel.get("hard_risks") or []) if str(x).strip()]
    family_scores = intel.get("family_scores") if isinstance(intel.get("family_scores"), dict) else {}
    wallet = num(family_scores.get("wallet_flow"), 0.0) or 0.0
    holder = num(family_scores.get("holder_network"), 0.0) or 0.0
    micro = num(family_scores.get("market_microstructure"), 0.0) or 0.0

    if status != "CURRENT":
        blockers.append("INTELLIGENCE_NOT_CURRENT")
    if intel_age is None or intel_age < 0 or intel_age * 60 > max_age:
        blockers.append("INTELLIGENCE_STALE_OR_UNTIMED")
    if evidence < int(policy["min_current_evidence"]):
        blockers.append("CURRENT_EVIDENCE_TOO_LOW")
    if hard_risks:
        blockers.append("HARD_RISK_PRESENT")
    if micro <= 0:
        blockers.append("MARKET_MICROSTRUCTURE_NOT_POSITIVE")

    strong = (
        score >= float(policy["strong_min_fusion_score"])
        and families >= int(policy["strong_min_positive_families"])
    )
    relaxed = (
        score >= float(policy["relaxed_min_fusion_score"])
        and families >= int(policy["relaxed_min_positive_families"])
        and max(wallet, holder) >= float(policy["relaxed_min_wallet_or_holder_score"])
    )
    if strong:
        proof.append(f"STRONG_FUSION_{score:.1f}_{families}F")
    elif relaxed:
        proof.append(f"FUSION_PLUS_WALLET_HOLDER_{score:.1f}_{families}F")
    else:
        blockers.append("FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET")

    previous_price = num(prior.get("last_price"))
    previous_low = num(prior.get("watch_low_price"))
    low = price if price > 0 and previous_low is None else previous_low
    if price > 0 and low is not None:
        low = min(low, price)
    rebound = ((price / low) - 1.0) * 100.0 if price > 0 and low and low > 0 else None
    scan_gain = ((price / previous_price) - 1.0) * 100.0 if price > 0 and previous_price and previous_price > 0 else None

    if previous_price is None:
        blockers.append("NEED_SECOND_VERIFIED_SCAN")
    if rebound is None or rebound < float(policy["min_rebound_from_watch_low_pct"]):
        blockers.append("REBOUND_FROM_WATCH_LOW_NOT_CONFIRMED")
    if scan_gain is None or scan_gain < float(policy["min_scan_price_gain_pct"]):
        blockers.append("SHORT_TERM_PRICE_RECLAIM_NOT_CONFIRMED")
    if scan_gain is not None and scan_gain > float(policy["max_scan_price_gain_pct"]):
        blockers.append("SHORT_TERM_CHASE_RISK")

    observable = bool(
        market is not None
        and observed is not None
        and report_verified
        and market_age is not None
        and -120 <= market_age <= max_age
        and report_age is not None
        and -120 <= report_age <= max_age
        and market_key == key
    )

    unique_blockers = sorted(set(blockers))
    qualified = not unique_blockers
    prior_streak = int(prior.get("qualified_streak") or 0)
    streak = prior_streak + 1 if qualified else 0
    required_streak = max(1, int(policy["required_consecutive_qualified_scans"]))
    final_buy = qualified and streak >= required_streak

    armed = bool(prior.get("armed", True))
    miss_streak = int(prior.get("observable_miss_streak") or 0)
    if qualified:
        miss_streak = 0
    elif observable:
        miss_streak += 1
        if miss_streak >= max(1, int(policy["rearm_after_observable_misses"])):
            armed = True

    alert = bool(final_buy and armed)
    if alert:
        armed = False

    if ratio >= float(policy["min_buy_sell_ratio"]):
        proof.append(f"BUY_SELL_{ratio:.2f}X")
    if rebound is not None and rebound >= float(policy["min_rebound_from_watch_low_pct"]):
        proof.append(f"REBOUND_{rebound:.2f}PCT")
    if scan_gain is not None and float(policy["min_scan_price_gain_pct"]) <= scan_gain <= float(policy["max_scan_price_gain_pct"]):
        proof.append(f"SCAN_GAIN_{scan_gain:.2f}PCT")
    if liquidity >= float(policy["min_liquidity_usd"]):
        proof.append(f"LIQUIDITY_{liquidity:.0f}")
    if report_verified:
        proof.append("EXACT_PAIR_VERIFIED")

    result = {
        "identity_key": key,
        "symbol": str(target.get("symbol") or "").upper(),
        "state": "BUY_ZONE" if final_buy else ("QUALIFYING" if qualified else "WATCH"),
        "recommended_action": "BUY" if final_buy else "WAIT",
        "alert": alert,
        "observable": observable,
        "qualified_this_scan": qualified,
        "qualified_streak": streak,
        "required_streak": required_streak,
        "blockers": unique_blockers,
        "proof": list(dict.fromkeys(proof)),
        "market": {
            "price_usd": price,
            "liquidity_usd": liquidity,
            "volume_h1_usd": volume_h1,
            "buys_h1": buys,
            "sells_h1": sells,
            "buy_sell_ratio": round(ratio, 4),
            "activity_h1": activity,
            "spread_pct": spread,
            "scan_price_gain_pct": round(scan_gain, 4) if scan_gain is not None else None,
            "rebound_from_watch_low_pct": round(rebound, 4) if rebound is not None else None,
        },
        "intelligence": {
            "status": status,
            "score": score,
            "positive_families": families,
            "current_evidence_count": evidence,
            "evidence_age_minutes": intel_age,
            "hard_risks": hard_risks,
            "wallet_flow_score": wallet,
            "holder_network_score": holder,
            "market_microstructure_score": micro,
        },
        "truth_contract": {
            "exact_chain_contract_pair_required": True,
            "two_scan_confirmation_required": required_streak >= 2,
            "telegram_final_buy_only": True,
            "manual_decision_only": True,
            "automatic_trade": False,
            "does_not_modify_veteran_real_alert_policy": True,
        },
    }

    next_state = {
        **prior,
        "identity_key": key,
        "symbol": result["symbol"],
        "last_seen_at": now.isoformat(),
        "last_price": price if price > 0 else prior.get("last_price"),
        "last_liquidity": liquidity,
        "last_volume_h1": volume_h1,
        "watch_low_price": low if low is not None else prior.get("watch_low_price"),
        "watch_high_price": max(num(prior.get("watch_high_price"), 0.0) or 0.0, price),
        "qualified_streak": streak,
        "observable_miss_streak": miss_streak,
        "armed": armed,
        "last_state": result["state"],
        "last_blockers": unique_blockers,
    }
    if not next_state.get("first_seen_at"):
        next_state["first_seen_at"] = now.isoformat()
    if alert:
        next_state["last_alert_at"] = now.isoformat()
        next_state["last_alert_price"] = price
        next_state["buy_episode_count"] = int(prior.get("buy_episode_count") or 0) + 1

    return result, next_state


def telegram_message(target: dict, decision: dict) -> str:
    m = decision["market"]
    intel = decision["intelligence"]
    dex = str(target.get("dex_url") or "")
    return "\n".join([
        f"🟢🔥 קנייה / BUY — {decision['symbol']} — WALLET500",
        "Unified Watch FINAL BUY ✅",
        f"Price: ${m['price_usd']:.10f}",
        f"Liquidity: ${m['liquidity_usd']:,.0f} | Vol 1H: ${m['volume_h1_usd']:,.0f}",
        f"Buys/Sells 1H: {m['buys_h1']}/{m['sells_h1']} ({m['buy_sell_ratio']:.2f}x)",
        f"Rebound from watch low: {m['rebound_from_watch_low_pct']:.2f}%",
        f"Scan-to-scan price gain: {m['scan_price_gain_pct']:.2f}%",
        f"Intelligence Fusion: {intel['score']:.1f}/100 | {intel['positive_families']} positive families",
        "Proof: " + " | ".join(decision.get("proof") or []),
        "Manual decision only. No automatic trade.",
        f"CA: {target.get('contract')}",
        f"Pair: {target.get('pair')}",
        dex,
    ])


def send_telegram(text: str) -> None:
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        raise RuntimeError("TELEGRAM_SECRETS_NOT_CONFIGURED")
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot}/sendMessage",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError("TELEGRAM_SEND_FAILED")


def main() -> int:
    config = load(CONFIG, {})
    policy = _policy(config)
    if policy.get("enabled") is not True:
        write(REPORT, {
            "version": 1,
            "generated_at": now_iso(),
            "mode": POLICY_MODE,
            "status": "DISABLED",
            "targets": [],
        })
        return 0

    watch_state = load(WATCH_STATE, {})
    watch_report = load(WATCH_REPORT, {})
    persistent = load(STATE, {"version": 1, "targets": {}})
    target_state = persistent.get("targets") if isinstance(persistent.get("targets"), dict) else {}
    target_state = dict(target_state)

    now = now_utc()
    top_report_age = age_seconds(watch_report.get("updated_at"), now)
    decisions: list[dict] = []
    delivered: list[str] = []
    errors: list[dict] = []

    for target in eligible_targets(config):
        key = identity_key(target)
        m = market_row(watch_state, key)
        rr = report_row(watch_report, key)
        if rr is not None:
            rr = dict(rr)
            rr["_report_age_seconds"] = top_report_age
        decision, next_state = evaluate(
            target, m, rr, target_state.get(key), policy, now=now
        )

        if decision.get("alert") is True:
            try:
                send_telegram(telegram_message(target, decision))
                delivered.append(key)
                next_state["last_delivery_status"] = "DELIVERED"
            except Exception as exc:
                next_state["armed"] = True
                next_state.pop("last_alert_at", None)
                next_state.pop("last_alert_price", None)
                next_state["buy_episode_count"] = int((target_state.get(key) or {}).get("buy_episode_count") or 0)
                next_state["last_delivery_status"] = f"ERROR:{type(exc).__name__}"
                decision["alert"] = False
                decision["delivery_error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
                errors.append({"identity_key": key, "error": decision["delivery_error"]})

        target_state[key] = next_state
        decisions.append(decision)

    persistent = {
        "version": 1,
        "updated_at": now.isoformat(),
        "mode": POLICY_MODE,
        "targets": target_state,
    }
    write(STATE, persistent)

    report = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": POLICY_MODE,
        "policy": policy,
        "configured_targets": len(eligible_targets(config)),
        "buy_zone_count": sum(1 for x in decisions if x.get("state") == "BUY_ZONE"),
        "delivered_count": len(delivered),
        "delivered": delivered,
        "error_count": len(errors),
        "errors": errors,
        "decisions": decisions,
        "truth_contract": {
            "source": "Unified Watch exact-pair state + current intelligence report",
            "user_requested_targets_only": True,
            "telegram_final_buy_only": True,
            "research_watch_notifications": False,
            "near_buy_notifications": False,
            "automatic_trade": False,
            "veteran_production_real_alert_policy_unchanged": True,
        },
    }
    write(REPORT, report)
    print(json.dumps({
        "status": "OK" if not errors else "DELIVERY_ERROR",
        "mode": POLICY_MODE,
        "configured_targets": report["configured_targets"],
        "buy_zone_count": report["buy_zone_count"],
        "delivered_count": report["delivered_count"],
        "error_count": report["error_count"],
    }, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
