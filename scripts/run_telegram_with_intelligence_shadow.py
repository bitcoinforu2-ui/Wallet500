from __future__ import annotations

import json
import os
from pathlib import Path

from wallet500 import telegram_alerts as alerts

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
CURRENT_STATUS = "CURRENT"
STALE_STATUS = "STALE_ONLY"


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
    return {identity_key(x): x for x in rows if identity_key(x)}


def _age_text(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.1f}m"
    except (TypeError, ValueError):
        return "n/a"


def _family_summary(intel: dict) -> str:
    scores = intel.get("family_scores") if isinstance(intel.get("family_scores"), dict) else {}
    positive = []
    for family, value in scores.items():
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if score > 0:
            positive.append((str(family), score))
    positive.sort(key=lambda item: item[1], reverse=True)
    return ", ".join(f"{name} {score:.1f}" for name, score in positive[:5]) or "none"


def shadow_lines(row: dict, index: dict[str, dict], stage: str = "REAL_ALERT") -> list[str]:
    key = identity_key(row)
    intel = index.get(key) if key else None
    stage = str(stage or "REAL_ALERT").upper()
    if not intel:
        return [
            "🧠 Intelligence Fusion: NOT AVAILABLE (SHADOW)",
            f"Fusion status: SHADOW — no exact-pair intelligence snapshot for this {stage}; production eligibility is unchanged.",
        ]

    status = str(intel.get("status") or "UNKNOWN").upper()
    age_text = _age_text(intel.get("evidence_age_minutes"))
    window = intel.get("window_minutes")
    hard = [str(x) for x in (intel.get("hard_risks") or [])]

    # Missing/stale evidence is never rendered as a misleading 0/100 score.
    if status == STALE_STATUS:
        return [
            "🧠 Intelligence Fusion: STALE (SHADOW)",
            f"Intel status: {status} · freshest evidence age: {age_text} · window: {window if window is not None else 'n/a'}m",
            f"Hard risks in current window: {', '.join(hard) if hard else 'none'}",
            f"Fusion status: SHADOW — stale evidence does not promote or suppress this {stage}.",
        ]
    if status != CURRENT_STATUS:
        return [
            "🧠 Intelligence Fusion: NOT AVAILABLE (SHADOW)",
            f"Intel status: {status} · no current exact-pair verified evidence",
            f"Fusion status: SHADOW — missing evidence does not promote or suppress this {stage}.",
        ]

    score = intel.get("score")
    score_text = "n/a" if score is None else f"{float(score):.1f}/100"
    label = str(intel.get("label") or "WATCH")
    families = int(intel.get("independent_positive_families") or 0)
    current_evidence = int(intel.get("current_evidence_count") or 0)
    freshest = str(intel.get("freshest_event_at") or "n/a")
    updated = str(intel.get("updated_at") or "n/a")
    return [
        f"🧠 Intelligence Fusion: {score_text} — {label} (SHADOW)",
        f"Independent positive families: {families} · current evidence: {current_evidence}",
        f"Positive family scores: {_family_summary(intel)}",
        f"Intel updated: {updated}",
        f"Freshest evidence: {freshest} · age: {age_text} · window: {window if window is not None else 'n/a'}m",
        f"Hard risks: {', '.join(hard) if hard else 'none'}",
        f"Fusion status: SHADOW — NOT USED TO PROMOTE/SUPPRESS THIS {stage}.",
    ]


def inject(text: str, row: dict, index: dict[str, dict], stage: str = "REAL_ALERT") -> str:
    replacement = "\n".join(shadow_lines(row, index, stage=stage))
    slogan = "Verified Intelligence. The Pure Truth."
    if slogan in text:
        return text.replace(slogan, replacement, 1)
    return text + "\n" + replacement


def main() -> int:
    out = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
    index = load_index(out)
    original_message = alerts._message
    original_pre_wave_message = alerts._pre_wave_message

    def guarded_message(row, tier, sent_at=None, alert_event_id=None):
        baseline = original_message(row, tier, sent_at=sent_at, alert_event_id=alert_event_id)
        if "MANUAL DECISION ONLY" not in baseline or "NO AUTOMATIC TRADE" not in baseline or "Actionable research alert: YES" not in baseline:
            raise RuntimeError("TELEGRAM_REAL_ALERT_TRUTH_CONTRACT_DRIFT")
        return inject(baseline, row, index, stage="REAL_ALERT")

    def guarded_pre_wave_message(row, sent_at=None, alert_event_id=None):
        baseline = original_pre_wave_message(row, sent_at=sent_at, alert_event_id=alert_event_id)
        if "MANUAL REVIEW ONLY" not in baseline or "NO AUTOMATIC TRADE" not in baseline:
            raise RuntimeError("TELEGRAM_PRE_WAVE_TRUTH_CONTRACT_DRIFT")
        return inject(baseline, row, index, stage="PRE_WAVE")

    alerts._message = guarded_message
    alerts._pre_wave_message = guarded_pre_wave_message
    try:
        report = alerts.run()
    finally:
        # The wrapper can be imported/executed in the same interpreter as tests or
        # other tooling. Never leak monkey-patched formatter functions globally.
        alerts._message = original_message
        alerts._pre_wave_message = original_pre_wave_message

    print(json.dumps({
        "status": "OK",
        "intelligence_shadow_rows": len(index),
        "telegram_report_status": report.get("status") if isinstance(report, dict) else None,
        "production_real_alert_gate_changed": False,
        "automatic_trade": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
