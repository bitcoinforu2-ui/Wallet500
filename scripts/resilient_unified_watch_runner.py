from __future__ import annotations

import json
import time
import urllib.parse
from collections import Counter
from pathlib import Path

import resilient_http
import unified_watch_engine as engine

ROOT = Path(__file__).resolve().parents[1]
HTTP_STATE = ROOT / "data/http-resilience-state.json"
REPORT = ROOT / "data/unified-watch-intelligence-report.json"

_ORIGINAL_MATERIAL_CHANGE_REASONS = engine.material_change_reasons
_ORIGINAL_SEND = engine.send
_ACTIONABILITY_STATS = Counter()
_ACTIONABILITY_EXAMPLES = []


def resilient_http_json(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    if host == "api.geckoterminal.com":
        # Exact-pair consensus remains mandatory, but 429 itself is fail-closed.
        # A 429 installs a shared 15s cooldown for subsequent targets instead of
        # retrying the same target repeatedly and amplifying throttling.
        return resilient_http.request_json(
            url,
            timeout=20,
            attempts=1,
            cache_ttl=15,
            min_interval=4.0,
            user_agent="Wallet500-UnifiedWatch/3.1",
        )
    return resilient_http.request_json(
        url,
        timeout=20,
        attempts=3,
        cache_ttl=15,
        user_agent="Wallet500-UnifiedWatch/3.1",
    )


def _fresh_intelligence(fusion, policy):
    status = str(fusion.get("status") or "").upper()
    if bool(policy.get("block_stale_only_positive_alerts", True)) and status in {
        "STALE_ONLY",
        "NOT_AVAILABLE",
        "UNKNOWN",
        "",
    }:
        return False, f"INTELLIGENCE_STATUS_{status or 'MISSING'}"

    current_evidence = int(fusion.get("current_evidence_count") or 0)
    required = max(1, int(policy.get("real_alert_min_current_evidence", 2)))
    if current_evidence < required:
        return False, f"CURRENT_EVIDENCE_{current_evidence}_LT_{required}"
    return True, "FRESH_INTELLIGENCE"


def _live_market_confirmation(live, triggers):
    positive_trigger = any(
        x in {"PRICE_PLUS_VOLUME_ACCELERATION", "ALPHA_CALL_PLUS_BUY_IMBALANCE"}
        or x.startswith("BREAK_ABOVE_")
        for x in triggers
    )
    buys = int(live.get("buys_h1") or 0)
    sells = int(live.get("sells_h1") or 0)
    ratio = (buys + 1.0) / (sells + 1.0)
    positive_flow = buys >= 10 and ratio >= 1.5
    positive_price = float(live.get("change_h1") or 0) > 0
    return bool(positive_trigger or (positive_flow and positive_price))


def _new_high_value_intelligence(reasons):
    return any(str(r).startswith("NEW_INTELLIGENCE:") for r in reasons)


def actionable_real_alert_gate(last_alert, live, fusion, triggers, reasons, policy):
    if not reasons:
        return False, "NO_MATERIAL_CHANGE", []

    direct_live_risk = any(
        x.startswith("LOSS_") or "LIQUIDITY_DROP" in x for x in triggers
    )
    if direct_live_risk and bool(policy.get("allow_direct_live_risk_alerts", True)):
        return True, "DIRECT_LIVE_RISK", ["LIVE_MARKET_RISK"]

    hard_risks = list(fusion.get("hard_risks") or [])
    if hard_risks and bool(policy.get("allow_current_hard_risk_alerts", True)):
        fresh, why = _fresh_intelligence(fusion, policy)
        if fresh:
            return True, "CURRENT_HARD_RISK", ["HARD_RISK", *hard_risks[:3]]
        return False, f"STALE_HARD_RISK:{why}", []

    fresh, why = _fresh_intelligence(fusion, policy)
    if not fresh:
        return False, why, []

    score = float(fusion.get("score") or 0)
    families = int(fusion.get("families") or 0)
    family_scores = fusion.get("family_scores") or {}
    wallet_score = float(family_scores.get("wallet_flow") or 0)
    holder_score = float(family_scores.get("holder_network") or 0)
    wallet_holder_min = float(policy.get("real_alert_min_wallet_holder_score", 3.0))
    strong_wallet_holder = max(wallet_score, holder_score) >= wallet_holder_min or any(
        str(r).startswith("WALLET_FLOW_SHIFT_+")
        or str(r).startswith("HOLDER_NETWORK_SHIFT_+")
        for r in reasons
    )
    new_intel = _new_high_value_intelligence(reasons)
    market_confirmed = _live_market_confirmation(live, triggers)

    strong_score = float(policy.get("real_alert_min_fusion_score", 55.0))
    strong_families = int(policy.get("real_alert_min_positive_families", 3))
    if score >= strong_score and families >= strong_families:
        return True, "FUSION_CONFLUENCE", [
            f"FUSION_{score:.1f}",
            f"FAMILIES_{families}",
        ]

    relaxed_score = float(
        policy.get("real_alert_relaxed_min_fusion_score_with_wallet_or_new_intel", 30.0)
    )
    relaxed_families = int(
        policy.get("real_alert_relaxed_min_positive_families_with_wallet_or_new_intel", 2)
    )
    special_intel = strong_wallet_holder or new_intel
    requires_market = bool(
        policy.get("real_alert_require_live_market_confirmation_for_relaxed_path", True)
    )
    if (
        special_intel
        and score >= relaxed_score
        and families >= relaxed_families
        and (market_confirmed or not requires_market)
    ):
        proof = [f"FUSION_{score:.1f}", f"FAMILIES_{families}"]
        if strong_wallet_holder:
            proof.append("WALLET_OR_HOLDER_SIGNAL")
        if new_intel:
            proof.append("NEW_MATERIAL_INTELLIGENCE")
        if market_confirmed:
            proof.append("LIVE_MARKET_CONFIRMATION")
        return True, "INTELLIGENCE_PLUS_MARKET", proof

    if not special_intel:
        return False, "NO_HIGH_VALUE_INTELLIGENCE_CONFIRMATION", []
    if score < relaxed_score:
        return False, f"FUSION_SCORE_{score:.1f}_LT_{relaxed_score:.1f}", []
    if families < relaxed_families:
        return False, f"FAMILIES_{families}_LT_{relaxed_families}", []
    if requires_market and not market_confirmed:
        return False, "NO_LIVE_MARKET_CONFIRMATION", []
    return False, "NOT_ACTIONABLE", []


def strict_material_change_reasons(last_alert, live, fusion, triggers, policy):
    reasons = _ORIGINAL_MATERIAL_CHANGE_REASONS(
        last_alert, live, fusion, triggers, policy
    )
    if not bool(policy.get("telegram_real_alert_only", True)):
        return reasons

    allowed, gate_reason, proof = actionable_real_alert_gate(
        last_alert, live, fusion, triggers, reasons, policy
    )
    if allowed:
        _ACTIONABILITY_STATS["real_alert_promotions"] += 1
        _ACTIONABILITY_STATS[f"promotion:{gate_reason}"] += 1
        print(
            "TELEGRAM_REAL_ALERT_PROMOTED",
            json.dumps(
                {
                    "gate_reason": gate_reason,
                    "proof": proof,
                    "material_reasons": reasons,
                    "triggers": triggers,
                    "score": fusion.get("score"),
                    "families": fusion.get("families"),
                    "status": fusion.get("status"),
                },
                ensure_ascii=False,
            ),
        )
        return reasons

    if reasons:
        _ACTIONABILITY_STATS["suppressed_non_actionable"] += 1
        _ACTIONABILITY_STATS[f"suppressed:{gate_reason}"] += 1
        if len(_ACTIONABILITY_EXAMPLES) < 25:
            _ACTIONABILITY_EXAMPLES.append(
                {
                    "gate_reason": gate_reason,
                    "material_reasons": list(reasons),
                    "triggers": list(triggers),
                    "fusion_score": fusion.get("score"),
                    "fusion_label": fusion.get("label"),
                    "fusion_status": fusion.get("status"),
                    "positive_families": fusion.get("families"),
                    "current_evidence_count": fusion.get("current_evidence_count"),
                }
            )
        print(
            "TELEGRAM_SUPPRESSED_NOT_ACTIONABLE",
            json.dumps(
                {
                    "gate_reason": gate_reason,
                    "material_reasons": reasons,
                    "triggers": triggers,
                    "score": fusion.get("score"),
                    "families": fusion.get("families"),
                    "status": fusion.get("status"),
                },
                ensure_ascii=False,
            ),
        )
    return []


def strict_send(msg):
    lines = str(msg).splitlines()
    if not lines:
        return _ORIGINAL_SEND(msg)

    risk = "| RISK" in lines[0] or lines[0].startswith("⚠️")
    parts = [x.strip() for x in lines[0].split("|")]
    symbol = parts[0] if parts else "🔥 WALLET500"
    if risk:
        lines[0] = f"{symbol} | WALLET500 | REAL_ALERT | ACTIONABLE=TRUE | RISK"
    else:
        lines[0] = f"{symbol} | WALLET500 | REAL_ALERT | ACTIONABLE=TRUE"

    if not any(x.startswith("ACTIONABLE:") for x in lines):
        insert_at = 1 if len(lines) > 1 else len(lines)
        lines.insert(insert_at, "ACTIONABLE: TRUE · RESEARCH_ONLY/WATCH SUPPRESSED")
    return _ORIGINAL_SEND("\n".join(lines))


def _write_actionability_report(policy):
    try:
        report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    except Exception:
        report = {}
    report["version"] = max(int(report.get("version") or 0), 4)
    report["mode"] = "REAL_ALERT_ACTIONABLE_ONLY"
    report["telegram_mode"] = "REAL_ALERT_ACTIONABLE_ONLY"
    report["actionable_required"] = True
    report["research_watch_telegram_suppressed"] = True
    report["actionability_policy"] = {
        "min_fusion_score": float(policy.get("real_alert_min_fusion_score", 55.0)),
        "min_positive_families": int(policy.get("real_alert_min_positive_families", 3)),
        "min_current_evidence": int(policy.get("real_alert_min_current_evidence", 2)),
        "relaxed_score_with_wallet_or_new_intel": float(
            policy.get("real_alert_relaxed_min_fusion_score_with_wallet_or_new_intel", 30.0)
        ),
        "relaxed_families_with_wallet_or_new_intel": int(
            policy.get("real_alert_relaxed_min_positive_families_with_wallet_or_new_intel", 2)
        ),
        "relaxed_path_requires_live_market_confirmation": bool(
            policy.get("real_alert_require_live_market_confirmation_for_relaxed_path", True)
        ),
        "stale_positive_alerts_blocked": bool(
            policy.get("block_stale_only_positive_alerts", True)
        ),
    }
    report["actionability_stats"] = dict(_ACTIONABILITY_STATS)
    report["suppressed_non_actionable_examples"] = list(_ACTIONABILITY_EXAMPLES)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


def main():
    # Give the previous collector stage a short quiet period, then use a
    # process-shared per-host limiter/cooldown. Exact identity/spread checks in
    # unified_watch_engine are intentionally unchanged and remain fail-closed.
    time.sleep(4)
    engine.http_json = resilient_http_json
    engine.material_change_reasons = strict_material_change_reasons
    engine.send = strict_send

    cfg = json.loads(engine.CONFIG.read_text())
    policy = dict(cfg.get("alert_policy") or {})

    rc = engine.main()
    _write_actionability_report(policy)
    HTTP_STATE.write_text(
        json.dumps(
            {
                "version": 3,
                "updated_at": engine.now_iso(),
                "component": "unified_watch",
                "strategy": "STRICT_EXACT_PAIR_4S_GECKO_PACING_429_CIRCUIT_BREAKER_PLUS_REAL_ALERT_ACTIONABLE_GATE",
                "metrics": resilient_http.metrics(),
                "telegram_mode": "REAL_ALERT_ACTIONABLE_ONLY",
                "actionability_stats": dict(_ACTIONABILITY_STATS),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
