from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
MIN_MARKET_AGE_DAYS = 90
MIN_RESEARCH_SCORE = 30
MAX_LEADERBOARD_RANK = 10
MODE = "RESEARCH_ONLY_CEX_TELEGRAM_DISABLED_V3"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _key(row: dict) -> str:
    chain = str(row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or row.get("token") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    if chain in {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "polygon"}:
        token = token.lower()
        pair = pair.lower()
    return f"{chain}:{token}:{pair}"


def _eligible(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("identity_status") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
        return False
    if row.get("market_age_verified") is not True:
        return False
    try:
        if int(row.get("market_age_min_days") or 0) < MIN_MARKET_AGE_DAYS:
            return False
        score = int(row.get("spot_revival_score") or 0)
        rank = int(row.get("leaderboard_best_rank") or 9999)
    except (TypeError, ValueError):
        return False
    if row.get("research_only") is not True or row.get("actionable") is not False:
        return False
    if not str(row.get("chain") or "").strip():
        return False
    if not str(row.get("token_address") or row.get("token") or "").strip():
        return False
    if not str(row.get("pair_address") or "").strip():
        return False
    return score >= MIN_RESEARCH_SCORE or rank <= MAX_LEADERBOARD_RANK


def _send(*_args, **_kwargs):
    """Fail closed: research-only CEX candidates are never user-facing Telegram alerts."""
    raise RuntimeError("RESEARCH_ONLY_TELEGRAM_DISABLED_BY_POLICY")


def run(data_dir: Path = DATA, now: datetime | None = None) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    source_path = data_dir / "cex-spot-identity-radar.json"
    report_path = data_dir / "cex-spot-telegram-report.json"
    source = _load(source_path, {})
    candidates = [x for x in (source.get("candidates") or []) if _eligible(x)] if isinstance(source, dict) else []
    now_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_s = now_dt.isoformat()
    suppressed = [
        {
            "key": _key(row),
            "symbol": row.get("symbol"),
            "reason": "RESEARCH_ONLY_NO_USER_NOTIFICATION",
        }
        for row in candidates
    ]
    report = {
        "version": 3,
        "mode": MODE,
        "generated_at": now_s,
        "status": "RESEARCH_ONLY_NOTIFICATION_DISABLED",
        "research_only": True,
        "automatic_buy": False,
        "telegram_delivery_enabled": False,
        "source_generated_at": source.get("generated_at") if isinstance(source, dict) else None,
        "eligible_count": len(candidates),
        "delivered_count": 0,
        "suppressed_count": len(suppressed),
        "suppressed": suppressed,
        "policy": (
            "CEX early-watch evidence remains internal research. User-facing Telegram delivery begins only "
            "after a candidate is promoted into the canonical post-research production alert lane."
        ),
        "truth_contract": {
            "exact_identity_required": True,
            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "research_only_telegram_delivery_disabled": True,
            "research_only_never_user_alert": True,
            "post_research_user_alert_source": "real-alerts.json via wallet500.telegram_alerts",
            "production_gates_unchanged": True,
        },
    }
    _write(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
