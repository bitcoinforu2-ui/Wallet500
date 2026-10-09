"""Research-only CEX detection-to-production visibility audit.

Never generates Telegram alerts or authorizes trading. Fail closed on missing data.
"""
import json
from pathlib import Path


def read(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: expected object")
    return obj


def identity(row):
    # Symbol is only a research correlation key, NEVER an exact-pair identity.
    return str(row.get("symbol") or "").strip().upper()


def audit(cex, production):
    watch = cex.get("watchlist") or []
    detections = cex.get("alerts") or []
    real = production.get("alerts") or []
    verified = production.get("verified_watch") or []
    if not all(isinstance(rows, list) for rows in (watch, detections, real, verified)):
        raise ValueError("Malformed radar or production lists")
    radar_symbols = {identity(x) for x in detections if isinstance(x, dict) and identity(x)}
    production_symbols = {identity(x) for x in real if isinstance(x, dict) and identity(x)}
    # This is not an exact-pair match. It must NEVER imply production eligibility.
    missing = sorted(radar_symbols - production_symbols)
    return {
        "classification": "RESEARCH_ONLY_SYMBOL_CORRELATION_NOT_PRODUCTION_IDENTITY",
        "cex_generated_at": cex.get("generated_at"),
        "production_generated_at": production.get("generated_at"),
        "cex_watch_count": len(watch),
        "cex_detection_count": len(detections),
        "production_real_alert_count": len(real),
        "production_verified_watch_count": len(verified),
        "cex_symbols_not_in_production": missing,
        "limitation": "No historical first-seen proof, exact-pair proof, or missed-buy conclusion",
        "telegram_eligible": False,
        "buy_authorized": False,
    }


def main():
    report = audit(read("data/cex-revival-radar.json"), read("data/real-alerts.json"))
    print("CEX_TO_PRODUCTION_VISIBILITY_AUDIT " + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
