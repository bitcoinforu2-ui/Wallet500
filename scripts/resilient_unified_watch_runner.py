from __future__ import annotations

import json
import time
import urllib.parse
from collections import Counter
from pathlib import Path

import deep_investigation_refresh
import resilient_http
import unified_watch_engine as engine

ROOT = Path(__file__).resolve().parents[1]
HTTP_STATE = ROOT / "data/http-resilience-state.json"
REPORT = ROOT / "data/unified-watch-intelligence-report.json"

_ORIGINAL_LOAD_INTELLIGENCE = engine.load_intelligence
_ORIGINAL_FUSION_SUMMARY = engine.fusion_summary
_ORIGINAL_MATERIAL_CHANGE_REASONS = engine.material_change_reasons
_ORIGINAL_SEND = engine.send
_ACTIONABILITY_STATS = Counter()
_ACTIONABILITY_EXAMPLES = []
_DEEP_REPORTS = []
_DEEP_FAILURES = []
_DEEP_DONE = set()
_TARGETS_BY_IDENTITY = {}
_PREVIOUS_STATE = {"tokens": {}}


class _IdentityAwareIntelIndex(dict):
    def get(self, key, default=None):
        row = super().get(key)
        if row is None and key:
            return {"_identity_key": key, "_placeholder": True}
        return row if row is not None else default


def identity_aware_load_intelligence():
    index, doc = _ORIGINAL_LOAD_INTELLIGENCE()
    return _IdentityAwareIntelIndex(index), doc


def identity_aware_fusion_summary(row, notable_min_raw=0.30):
    placeholder = isinstance(row, dict) and row.get("_placeholder")
    fusion = _ORIGINAL_FUSION_SUMMARY(
        None if placeholder else row,
        notable_min_raw=notable_min_raw,
    )
    if isinstance(row, dict):
        identity_key = row.get("_identity_key") or row.get("identity_key")
        if not identity_key and not placeholder:
            identity_key = engine.exact_identity_key(row)
        if identity_key:
            fusion["_identity_key"] = identity_key
    return fusion


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
            user_agent="Wallet500-UnifiedWatch/3.2-DeepIntel",
        )
    return resilient_http.request_json(
        url,
        timeout=20,
        attempts=3,
        cache_ttl=15,
        user_agent="Wallet500-UnifiedWatch/3.2-DeepIntel",
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
    hard_risks = list(fusion.get("hard_risks") or [])
    buy_side_only = bool(policy.get("telegram_buy_side_only", True))

    # User-facing Telegram is buy-side only. Risk, research, watch, sell-side and
    # deterioration events stay inside the engine for learning/state and must
    # never be promoted as actionable or near-buy alerts.
    if buy_side_only and (direct_live_risk or hard_risks):
        return False, "BUY_SIDE_ONLY_RISK_SUPPRESSED", []

    if direct_live_risk and bool(policy.get("allow_direct_live_risk_alerts", False)):
        return True, "DIRECT_LIVE_RISK", ["LIVE_MARKET_RISK"]

    if hard_risks and bool(policy.get("allow_current_hard_risk_alerts", False)):
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
    strong_requires_market = bool(
        policy.get("real_alert_require_live_market_confirmation_for_strong_path", True)
    )
    if (
        score >= strong_score
        and families >= strong_families
        and (market_confirmed or not strong_requires_market)
    ):
        proof = [f"FUSION_{score:.1f}", f"FAMILIES_{families}"]
        if market_confirmed:
            proof.append("LIVE_MARKET_CONFIRMATION")
        return True, "FUSION_CONFLUENCE", proof

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

    if buy_side_only and not market_confirmed:
        return False, "BUY_SIDE_ONLY_NO_LIVE_MARKET_CONFIRMATION", []
    if not special_intel:
        return False, "NO_HIGH_VALUE_INTELLIGENCE_CONFIRMATION", []
    if score < relaxed_score:
        return False, f"FUSION_SCORE_{score:.1f}_LT_{relaxed_score:.1f}", []
    if families < relaxed_families:
        return False, f"FAMILIES_{families}_LT_{relaxed_families}", []
    if requires_market and not market_confirmed:
        return False, "NO_LIVE_MARKET_CONFIRMATION", []
    return False, "NOT_ACTIONABLE", []


def _state_key(t):
    identity_key = engine.exact_identity_key(t)
    if t.get("dynamic_buy_candidate"):
        return f"BUY:{identity_key}"
    if t.get("dynamic_alpha_candidate"):
        return f"ALPHA:{identity_key}"
    if t.get("dynamic_bootstrap_candidate"):
        return f"BOOTSTRAP:{identity_key}"
    if t.get("dynamic_spot_candidate"):
        return f"SPOT:{identity_key}"
    return str(t.get("symbol") or "").upper()


def _refresh_deep_intelligence(last_alert, live, fusion, triggers, base_reasons, policy):
    identity_key = str(fusion.get("_identity_key") or "")
    if not identity_key or identity_key in _DEEP_DONE:
        return False

    t = _TARGETS_BY_IDENTITY.get(identity_key)
    if not t:
        print("DEEP_INVESTIGATION_TARGET_NOT_RESOLVED", identity_key)
        return False

    force_buy_watch = bool(
        t.get("dynamic_buy_candidate")
        or str(t.get("candidate_type") or "").upper() == "BUY_ZONE"
    ) and bool(t.get("deep_investigation", True))

    status = str(fusion.get("status") or "").upper()
    current_evidence = int(fusion.get("current_evidence_count") or 0)
    families = int(fusion.get("families") or 0)
    family_scores = fusion.get("family_scores") if isinstance(fusion.get("family_scores"), dict) else {}
    micro = float(family_scores.get("market_microstructure") or 0)
    required_evidence = max(1, int(policy.get("real_alert_min_current_evidence", 2)))
    proactive_hot_recovery = bool(
        t.get("dynamic_spot_candidate")
        and t.get("deep_investigation")
        and (
            status != "CURRENT"
            or current_evidence < required_evidence
            or families < int(policy.get("real_alert_relaxed_min_positive_families_with_wallet_or_new_intel", 2))
            or micro <= 0
        )
    )

    qualification = (
        ["FINAL_BUY_ZONE_FULL_INTELLIGENCE"]
        if force_buy_watch
        else deep_investigation_refresh.positive_investigation_reasons(
            live, triggers, base_reasons, policy
        )
    )
    if proactive_hot_recovery:
        missing = []
        if status != "CURRENT":
            missing.append(f"STATUS_{status or 'MISSING'}")
        if current_evidence < required_evidence:
            missing.append(f"EVIDENCE_{current_evidence}_LT_{required_evidence}")
        if families < int(policy.get("real_alert_relaxed_min_positive_families_with_wallet_or_new_intel", 2)):
            missing.append(f"FAMILIES_{families}")
        if micro <= 0:
            missing.append("MICROSTRUCTURE_NONPOSITIVE_OR_MISSING")
        qualification = list(dict.fromkeys([
            *qualification,
            "PROACTIVE_MISSING_EVIDENCE_RECOVERY:" + ",".join(missing),
        ]))
    if not qualification:
        return False

    max_targets = max(1, int(policy.get("deep_investigation_max_targets_per_cycle", 8)))
    if len(_DEEP_DONE) >= max_targets and not force_buy_watch:
        print("DEEP_INVESTIGATION_CAP_REACHED", identity_key, qualification)
        return False

    previous_scan = (_PREVIOUS_STATE.get("tokens") or {}).get(_state_key(t)) or {}
    _DEEP_DONE.add(identity_key)
    try:
        result = deep_investigation_refresh.run_one(
            engine,
            policy,
            t,
            live,
            previous_scan,
            triggers,
            base_reasons,
        )
        if not result:
            return False
        report, row = result
        _DEEP_REPORTS.append(report)
        if row:
            notable_min_raw = float(policy.get("notable_evidence_min_raw", 0.30))
            refreshed = identity_aware_fusion_summary(
                row, notable_min_raw=notable_min_raw
            )
            fusion.clear()
            fusion.update(refreshed)
            return True
    except Exception as exc:
        failure = {
            "identity_key": identity_key,
            "qualification": qualification,
            "error": f"{type(exc).__name__}:{str(exc)[:200]}",
        }
        _DEEP_FAILURES.append(failure)
        print("DEEP_INVESTIGATION_FAILED", json.dumps(failure, ensure_ascii=False))
    return False


def strict_material_change_reasons(last_alert, live, fusion, triggers, policy):
    base_reasons = _ORIGINAL_MATERIAL_CHANGE_REASONS(
        last_alert, live, fusion, triggers, policy
    )

    refreshed = _refresh_deep_intelligence(
        last_alert, live, fusion, triggers, base_reasons, policy
    )
    reasons = (
        _ORIGINAL_MATERIAL_CHANGE_REASONS(last_alert, live, fusion, triggers, policy)
        if refreshed
        else base_reasons
    )

    # Unified Watch keeps scanning, learning and refreshing deep intelligence,
    # but it never sends user-facing Telegram messages. Final BUY delivery is
    # owned exclusively by the canonical Decision Engine BUY / BUY_ZONE lane.
    if bool(policy.get("telegram_final_buy_only", True)):
        if reasons:
            _ACTIONABILITY_STATS["suppressed_final_buy_only"] += 1
            print(
                "TELEGRAM_SUPPRESSED_FINAL_BUY_ONLY",
                json.dumps({"material_reasons": reasons, "triggers": triggers}, ensure_ascii=False),
            )
        return []

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
                    "deep_investigation": identity_key_in_deep(fusion),
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
                    "deep_investigation": identity_key_in_deep(fusion),
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
                    "deep_investigation": identity_key_in_deep(fusion),
                },
                ensure_ascii=False,
            ),
        )
    return []


def identity_key_in_deep(fusion):
    return str(fusion.get("_identity_key") or "") in _DEEP_DONE


def strict_send(msg):
    # Defense in depth: this runner has no authority to deliver Telegram.
    # Even if a future code path reaches send(), fail closed and keep the event internal.
    header = str(msg).splitlines()[0] if str(msg).splitlines() else "WALLET500"
    print("TELEGRAM_SEND_BLOCKED_FINAL_BUY_ONLY", header)
    _ACTIONABILITY_STATS["send_blocked_final_buy_only"] += 1
    return None


def _write_actionability_report(policy):
    try:
        report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    except Exception:
        report = {}
    report["version"] = max(int(report.get("version") or 0), 5)
    report["mode"] = "ENGINE_ONLY_FINAL_BUY_TELEGRAM_SUPPRESSED"
    report["telegram_mode"] = "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE"
    report["actionable_required"] = False
    report["research_watch_telegram_suppressed"] = True
    report["risk_telegram_suppressed"] = bool(policy.get("telegram_buy_side_only", True))
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
        "telegram_buy_side_only": bool(policy.get("telegram_buy_side_only", True)),
        "direct_live_risk_alerts_allowed": bool(policy.get("allow_direct_live_risk_alerts", False)),
        "hard_risk_alerts_allowed": bool(policy.get("allow_current_hard_risk_alerts", False)),
        "strong_path_requires_live_market_confirmation": bool(
            policy.get("real_alert_require_live_market_confirmation_for_strong_path", True)
        ),
    }
    report["deep_investigation"] = {
        "mode": "ON_DEMAND_BEFORE_ALERT_GATE",
        "max_targets_per_cycle": int(policy.get("deep_investigation_max_targets_per_cycle", 8)),
        "investigated": len(_DEEP_REPORTS),
        "failed": len(_DEEP_FAILURES),
        "targets": list(_DEEP_REPORTS),
        "failures": list(_DEEP_FAILURES),
    }
    report["actionability_stats"] = dict(_ACTIONABILITY_STATS)
    report["suppressed_non_actionable_examples"] = list(_ACTIONABILITY_EXAMPLES)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


def _build_target_index():
    cfg = json.loads(engine.CONFIG.read_text())
    static = [dict(x) for x in (cfg.get("tokens") or []) if isinstance(x, dict)]
    dynamic = [dict(x) for x in engine.dynamic_candidates() if isinstance(x, dict)]
    index = {
        engine.exact_identity_key(x): x
        for x in static
        if engine.exact_identity_key(x)
    }
    for row in dynamic:
        identity = engine.exact_identity_key(row)
        if not identity:
            continue
        if row.get("dynamic_buy_candidate"):
            merged = dict(index.get(identity) or {})
            merged.update({
                "candidate_type": "BUY_ZONE",
                "dynamic_buy_candidate": True,
                "priority": "HIGHEST",
                "close_watch": "HIGHEST",
                "deep_investigation": True,
                "full_intelligence": True,
                "buy_zone_price_usd": row.get("buy_zone_price_usd"),
                "first_buy_at": row.get("first_buy_at"),
                "last_buy_at": row.get("last_buy_at"),
            })
            for key in ("symbol", "network", "contract", "pair", "dex_url", "first_seen_at", "discovery_price"):
                if not merged.get(key) and row.get(key) is not None:
                    merged[key] = row.get(key)
            index[identity] = merged
        elif identity not in index:
            index[identity] = row
    return index


def main():
    global _TARGETS_BY_IDENTITY, _PREVIOUS_STATE
    # Give the previous collector stage a short quiet period, then use a
    # process-shared per-host limiter/cooldown. Exact identity/spread checks in
    # unified_watch_engine remain fail-closed. Positive material market changes
    # are upgraded into a targeted deep-intelligence refresh before alert gating.
    time.sleep(4)
    engine.http_json = resilient_http_json
    engine.load_intelligence = identity_aware_load_intelligence
    engine.fusion_summary = identity_aware_fusion_summary
    engine.material_change_reasons = strict_material_change_reasons
    engine.send = strict_send

    cfg = json.loads(engine.CONFIG.read_text())
    policy = dict(cfg.get("alert_policy") or {})
    _TARGETS_BY_IDENTITY = _build_target_index()
    try:
        _PREVIOUS_STATE = json.loads(engine.STATE.read_text()) if engine.STATE.exists() else {"tokens": {}}
    except Exception:
        _PREVIOUS_STATE = {"tokens": {}}

    rc = engine.main()
    _write_actionability_report(policy)
    HTTP_STATE.write_text(
        json.dumps(
            {
                "version": 4,
                "updated_at": engine.now_iso(),
                "component": "unified_watch",
                "strategy": "STRICT_EXACT_PAIR_PLUS_PROACTIVE_MISSING_EVIDENCE_RECOVERY_BEFORE_FINAL_DECISION",
                "metrics": resilient_http.metrics(),
                "telegram_mode": "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE",
                "deep_investigation_count": len(_DEEP_REPORTS),
                "deep_investigation_failures": len(_DEEP_FAILURES),
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