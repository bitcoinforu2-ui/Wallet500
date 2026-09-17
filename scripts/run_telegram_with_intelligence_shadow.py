from __future__ import annotations

import json
import os
from pathlib import Path

from wallet500 import telegram_alerts as alerts

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}


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


def shadow_lines(row: dict, index: dict[str, dict]) -> list[str]:
    key = identity_key(row)
    intel = index.get(key) if key else None
    if not intel:
        return [
            "🧠 Intelligence Fusion: NOT AVAILABLE (SHADOW)",
            "Fusion mode: SHADOW — canonical REAL ALERT eligibility is unchanged.",
        ]
    score = intel.get("score")
    score_text = "n/a" if score is None else f"{float(score):.1f}/100"
    label = str(intel.get("label") or "WATCH")
    status = str(intel.get("status") or "UNKNOWN")
    families = int(intel.get("independent_positive_families") or 0)
    age = intel.get("evidence_age_minutes")
    age_text = "n/a" if age is None else f"{float(age):.1f}m"
    hard = [str(x) for x in (intel.get("hard_risks") or [])]
    lines = [
        f"🧠 Intelligence Fusion: {score_text} — {label}",
        f"Intel status: {status} · independent positive families: {families} · evidence age: {age_text}",
        f"Hard risks: {', '.join(hard) if hard else 'none'}",
        "Fusion mode: SHADOW — visible evidence only; it does not promote or suppress this REAL ALERT yet.",
    ]
    return lines


def inject(text: str, row: dict, index: dict[str, dict]) -> str:
    replacement = "\n".join(shadow_lines(row, index))
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
        return inject(original_message(row, tier, sent_at=sent_at, alert_event_id=alert_event_id), row, index)

    def guarded_pre_wave_message(row, sent_at=None, alert_event_id=None):
        return inject(original_pre_wave_message(row, sent_at=sent_at, alert_event_id=alert_event_id), row, index)

    alerts._message = guarded_message
    alerts._pre_wave_message = guarded_pre_wave_message
    report = alerts.run()
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
