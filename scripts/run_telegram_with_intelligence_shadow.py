from __future__ import annotations

import json
import math
import os
from pathlib import Path

from wallet500 import telegram_alerts as alerts
from wallet500.decision_engine_v1 import run as run_decision_engine
from wallet500.telegram_buy_policy import filter_buy_only_payload

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
CURRENT_STATUS = "CURRENT"
STALE_STATUS = "STALE_ONLY"
SLOGAN = "Verified Intelligence. The Pure Truth."
BUY_POLICY = "BUY_ONLY_V2"


def chain_name(value: object) -> str:
    raw = str(value or "").strip().lower()
    return ALIASES.get(raw, raw)


def norm_addr(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def identity_key(row: dict) -> str:
    chain = chain_name(row.get("chain") or row.get("network"))
    token = norm_addr(chain, row.get("token_address") or row.get("token") or row.get("mint") or row.get("contract"))
    pair = norm_addr(chain, row.get("pair_address") or row.get("pair"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def load_index(out: Path) -> dict[str, dict]:
    path = out / "close-watch-intelligence.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        doc = {}
    rows = [x for x in (doc.get("tokens") or []) if isinstance(x, dict)]
    index: dict[str, dict] = {}
    for row in rows:
        if row.get("exact_identity_verified") is not True:
            continue
        key = identity_key(row)
        if key:
            index[key] = row
    return index


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _safe_int(value: object) -> int:
    number = _number(value)
    if number is None:
        return 0
    return max(0, int(number))


def _age_text(value: object) -> str:
    number = _number(value)
    return "n/a" if number is None else f"{number:.1f}m"


def _family_summary(intel: dict) -> str:
    scores = intel.get("family_scores") if isinstance(intel.get("family_scores"), dict) else {}
    positive = []
    for family, value in scores.items():
        score = _number(value)
        if score is not None and score > 0:
            positive.append((str(family), score))
    positive.sort(key=lambda item: item[1], reverse=True)
    return ", ".join(f"{name} {score:.1f}" for name, score in positive[:5]) or "none"


def _hard_risks(intel: dict) -> list[str]:
    raw = intel.get("hard_risks")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _not_available(stage: str, reason: str) -> list[str]:
    return [
        "🧠 Intelligence Fusion: NOT AVAILABLE (SHADOW)",
        f"Intel status: {reason}",
        f"Fusion status: SHADOW — missing/untrusted evidence does not promote or suppress this {stage}.",
    ]


def shadow_lines(row: dict, index: dict[str, dict], stage: str = "BUY") -> list[str]:
    key = identity_key(row)
    intel = index.get(key) if key else None
    stage = str(stage or "BUY").upper()
    if not intel:
        return [
            "🧠 Intelligence Fusion: NOT AVAILABLE (SHADOW)",
            f"Fusion status: SHADOW — no exact-pair intelligence snapshot for this {stage}; production eligibility is unchanged.",
        ]
    if intel.get("exact_identity_verified") is not True:
        return _not_available(stage, "EXACT_IDENTITY_UNVERIFIED")

    status = str(intel.get("status") or "UNKNOWN").upper()
    age = _number(intel.get("evidence_age_minutes"))
    window = _number(intel.get("window_minutes"))
    age_text = _age_text(age)
    window_text = "n/a" if window is None else f"{window:g}m"
    hard = _hard_risks(intel)

    stale_by_age = age is not None and window is not None and window > 0 and age > window
    if status == STALE_STATUS or stale_by_age:
        return [
            "🧠 Intelligence Fusion: STALE (SHADOW)",
            f"Intel status: {status} · freshest evidence age: {age_text} · window: {window_text}",
            f"Hard risks in current window: {', '.join(hard) if hard else 'none'}",
            f"Fusion status: SHADOW — stale evidence does not promote or suppress this {stage}.",
        ]
    if status != CURRENT_STATUS:
        return _not_available(stage, status)
    if age is None or age < 0 or window is None or window <= 0:
        return _not_available(stage, "CURRENT_WITHOUT_VERIFIABLE_FRESHNESS")

    current_evidence = _safe_int(intel.get("current_evidence_count"))
    if current_evidence <= 0:
        return _not_available(stage, "CURRENT_WITHOUT_CURRENT_EVIDENCE")

    score = _number(intel.get("score"))
    if score is None:
        return _not_available(stage, "CURRENT_WITH_INVALID_SCORE")

    score_text = f"{score:.1f}/100"
    label = str(intel.get("label") or "WATCH")
    families = _safe_int(intel.get("independent_positive_families"))
    freshest = str(intel.get("freshest_event_at") or "n/a")
    updated = str(intel.get("updated_at") or "n/a")
    return [
        f"🧠 Intelligence Fusion: {score_text} — {label} (SHADOW)",
        f"independent positive families: {families} · current evidence: {current_evidence}",
        f"Positive family scores: {_family_summary(intel)}",
        f"Intel updated: {updated}",
        f"Freshest evidence: {freshest} · age: {age_text} · window: {window_text}",
        f"Hard risks: {', '.join(hard) if hard else 'none'}",
        f"Fusion status: SHADOW — NOT USED TO PROMOTE/SUPPRESS THIS {stage}.",
    ]


def inject(text: str, row: dict, index: dict[str, dict], stage: str = "BUY") -> str:
    replacement = "\n".join(shadow_lines(row, index, stage=stage))
    if SLOGAN in text:
        return text.replace(SLOGAN, replacement, 1)
    return text + "\n" + replacement


def safe_inject(text: str, row: dict, index: dict[str, dict], stage: str = "BUY") -> str:
    try:
        return inject(text, row, index, stage=stage)
    except Exception:
        stage = str(stage or "BUY").upper()
        replacement = "\n".join(_not_available(stage, "SHADOW_FORMAT_ERROR"))
        if SLOGAN in text:
            return text.replace(SLOGAN, replacement, 1)
        return text + "\n" + replacement


def _buy_message(baseline: str, row: dict) -> str:
    decision = row.get("telegram_buy_decision") if isinstance(row.get("telegram_buy_decision"), dict) else {}
    if decision.get("recommended_action") != "BUY" or decision.get("state") != "BUY_ZONE":
        raise RuntimeError("TELEGRAM_BUY_DECISION_METADATA_MISSING")

    scores = decision.get("scores") if isinstance(decision.get("scores"), dict) else {}
    output: list[str] = []
    for line in baseline.splitlines():
        if line.startswith("🔥 HIGH-CONVICTION BUY REVIEW — WALLET500"):
            output.append("🟢🔥 קנייה / BUY — HIGH CONVICTION — WALLET500")
        elif line.startswith("🚨 BUY REVIEW — WALLET500"):
            output.append("🟢 קנייה / BUY — WALLET500")
        elif line == "🆕 NEW REAL ALERT":
            output.append("🆕 NEW BUY SIGNAL")
        elif line.startswith("Promotion:"):
            output.append("Decision Engine: BUY ✅")
            output.append("Decision state: BUY_ZONE ✅")
            output.append(f"Model signal: {decision.get('model_signal') or 'BUY'}")
            composite = _number(scores.get("composite"))
            confidence = _number(scores.get("confidence"))
            if composite is not None or confidence is not None:
                output.append(
                    "Decision scores: "
                    + f"composite={composite:.1f}" if composite is not None else "Decision scores: composite=n/a"
                )
                if confidence is not None:
                    output[-1] += f" · confidence={confidence:.1f}"
        elif line == "Actionable research alert: YES ✅":
            continue
        else:
            output.append(line)
    return "\n".join(output)


def _prepare_buy_state(out: Path, rows: list[dict]) -> int:
    """Re-arm rows that were previously sent by the old generic REAL_ALERT policy."""
    state_path = out / "telegram-alert-state.json"
    state = alerts._load(state_path, {})
    if not isinstance(state, dict):
        state = {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}
    changed = 0
    for row in rows:
        key = alerts._pair_key(row)
        info = sent.get(key) if isinstance(sent.get(key), dict) else None
        if not info or info.get("buy_signal") is True:
            continue
        if info.get("actionable") is True:
            info["actionable"] = False
            info["cleared_for_buy_only_policy"] = True
            sent[key] = info
            changed += 1
    if changed:
        state["sent"] = sent
        alerts._write(state_path, state)
    return changed


def _mark_buy_deliveries(out: Path, report: dict) -> None:
    delivered = [x for x in report.get("delivered") or [] if isinstance(x, dict) and x.get("alert_type") == "REAL_ALERT"]
    if not delivered:
        return
    state_path = out / "telegram-alert-state.json"
    state = alerts._load(state_path, {})
    if not isinstance(state, dict):
        state = {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}
    for event in delivered:
        key = str(event.get("key") or "")
        info = sent.get(key) if isinstance(sent.get(key), dict) else None
        if not info:
            continue
        info["buy_signal"] = True
        info["delivery_policy"] = BUY_POLICY
        sent[key] = info
    state["sent"] = sent
    alerts._write(state_path, state)


def main() -> int:
    out = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
    index = load_index(out)

    source_name = os.getenv("WALLET500_REAL_ALERT_INPUT", "real-alerts.json")
    source_payload = alerts._load(out / source_name, {})
    decision_payload = run_decision_engine(str(out))
    filtered_payload, buy_audit = filter_buy_only_payload(source_payload, decision_payload)
    filtered_name = "telegram-buy-only-real-alerts.json"
    alerts._write(out / filtered_name, filtered_payload)

    filtered_rows = [x for x in filtered_payload.get("alerts") or [] if isinstance(x, dict)]
    configured = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip())
    migrated_state_rows = _prepare_buy_state(out, filtered_rows) if configured else 0

    original_input = os.environ.get("WALLET500_REAL_ALERT_INPUT")
    os.environ["WALLET500_REAL_ALERT_INPUT"] = filtered_name
    original_message = alerts._message
    original_pre_wave_message = alerts._pre_wave_message

    def guarded_message(row, tier, sent_at=None, alert_event_id=None):
        baseline = original_message(row, tier, sent_at=sent_at, alert_event_id=alert_event_id)
        if "MANUAL DECISION ONLY" not in baseline or "NO AUTOMATIC TRADE" not in baseline or "Actionable research alert: YES" not in baseline:
            raise RuntimeError("TELEGRAM_REAL_ALERT_TRUTH_CONTRACT_DRIFT")
        buy_message = _buy_message(baseline, row)
        return safe_inject(buy_message, row, index, stage="BUY")

    def blocked_pre_wave_message(*args, **kwargs):
        raise RuntimeError("PRE_WAVE_TELEGRAM_DISABLED_BY_BUY_ONLY_POLICY")

    alerts._message = guarded_message
    alerts._pre_wave_message = blocked_pre_wave_message
    try:
        report = alerts.run()
    finally:
        alerts._message = original_message
        alerts._pre_wave_message = original_pre_wave_message
        if original_input is None:
            os.environ.pop("WALLET500_REAL_ALERT_INPUT", None)
        else:
            os.environ["WALLET500_REAL_ALERT_INPUT"] = original_input

    if isinstance(report, dict) and report.get("configured") is True:
        _mark_buy_deliveries(out, report)
        report["buy_only_policy"] = {
            **buy_audit,
            "migrated_old_generic_state_rows": migrated_state_rows,
            "near_buy_lane": "DISABLED",
            "pre_wave_telegram": "DISABLED",
            "generic_real_alert_telegram": "DISABLED_UNLESS_DECISION_ENGINE_BUY",
        }
        policy = dict(report.get("policy") or {})
        policy.update({
            "user_facing_mode": BUY_POLICY,
            "near_buy_stage": "DISABLED",
            "final_buy_gate": "DECISION_ENGINE_V1_BUY_ZONE_EXACT_PAIR",
            "pre_wave_user_delivery": "DISABLED",
            "generic_real_alert_user_delivery": "DISABLED",
        })
        report["policy"] = policy
        alerts._write(out / "telegram-alert-report.json", report)

    print(json.dumps({
        "status": "OK",
        "policy": BUY_POLICY,
        "intelligence_shadow_rows": len(index),
        "source_real_alerts": buy_audit.get("source_real_alert_count"),
        "suppressed_generic_real_alerts": buy_audit.get("suppressed_generic_real_alert_count"),
        "suppressed_pre_wave": buy_audit.get("suppressed_pre_wave_count"),
        "matched_final_buy_alerts": buy_audit.get("matched_buy_alert_count"),
        "decision_snapshot_status": buy_audit.get("decision_snapshot_status"),
        "telegram_report_status": report.get("status") if isinstance(report, dict) else None,
        "production_real_alert_gate_changed": False,
        "automatic_trade": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
