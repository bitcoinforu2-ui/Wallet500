from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .telegram_alerts import _fmt_money, _send

SOURCE = "candidate-evidence-envelope.json"
STATE = "stage-transition-telegram-state.json"
REPORT = "stage-transition-telegram-report.json"

# Raw research, WATCH and EVIDENCE_READY remain silent. User-facing stage
# notifications begin only at PAPER_BUY_CANDIDATE: one stage before BUY/REAL
# ALERT, then continue for stronger stages. This lane never weakens BUY gates.
STAGE_RANK = {
    "RESEARCH": 0,
    "WATCH": 0,
    "EVIDENCE_READY": 1,
    "PAPER_BUY_CANDIDATE": 2,
    "STRONG_GENESIS": 3,
    "EXCEPTIONAL_GENESIS": 4,
}
MIN_USER_FACING_RANK = STAGE_RANK["PAPER_BUY_CANDIDATE"]
MIN_USER_FACING_STAGE = "PAPER_BUY_CANDIDATE"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _key(row: dict) -> str:
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or "").strip().lower()
    return f"{token}|{pair}"


def _stage(row: dict) -> str:
    status = str(row.get("status") or "").upper().strip()
    if status in STAGE_RANK:
        return status
    if row.get("evidence_ready") is True or str(row.get("evidence_envelope_status") or "").upper() == "EVIDENCE_READY":
        return "EVIDENCE_READY"
    tier = str(row.get("discovery_tier") or "").upper()
    if "EVIDENCE_READY" in tier:
        return "EVIDENCE_READY"
    return "RESEARCH"


def _message(row: dict, previous_stage: str, current_stage: str) -> str:
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
    token = str(row.get("symbol") or row.get("name") or "UNKNOWN")
    mint = str(row.get("token_address") or row.get("token") or row.get("mint") or "unknown")
    pair = str(row.get("pair_address") or "unknown")
    liquidity = market.get("liquidity_usd") if market.get("liquidity_usd") is not None else row.get("liquidity_usd")
    verified = coverage.get("verified_independent_count")
    positive = coverage.get("positive_independent_count")
    pending = row.get("pending_confirmations") if isinstance(row.get("pending_confirmations"), list) else []
    blockers = row.get("blockers") if isinstance(row.get("blockers"), list) else []
    return "\n".join([
        "🔥 WALLET500 — PRE-BUY STAGE",
        "⚠️ שלב אחד לפני BUY או חזק יותר — עדיין לא הוראת BUY",
        f"Token: {token}",
        f"Mint: {mint}",
        f"Exact Pair: {pair}",
        f"שלב: {previous_stage} → {current_stage}",
        f"Liquidity: {_fmt_money(liquidity)}",
        f"Verified lanes: {verified if verified is not None else 'n/a'}",
        f"Positive lanes: {positive if positive is not None else 'n/a'}",
        f"Pending confirmations: {', '.join(map(str, pending)) if pending else 'none'}",
        f"Blockers: {', '.join(map(str, blockers)) if blockers else 'none'}",
        "REAL ALERT / BUY נשארים במסלול נפרד עם gates קשיחים יותר.",
    ])


def run(output_dir: str | None = None, now: datetime | None = None, sender=_send) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    source = _load(out / SOURCE, {})
    state_exists = (out / STATE).exists()
    state = _load(out / STATE, {"version": 2, "candidates": {}})
    previous = state.get("candidates") if isinstance(state.get("candidates"), dict) else {}
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(token and chat_id)
    reference = now or datetime.now(timezone.utc)

    current: dict[str, dict] = {}
    delivered: list[dict] = []
    eligible: list[dict] = []
    errors: list[dict] = []

    for row in source.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        key = _key(row)
        if key == "|" or not key.split("|", 1)[1]:
            continue
        stage = _stage(row)
        rank = STAGE_RANK.get(stage, 0)
        old = previous.get(key) if isinstance(previous.get(key), dict) else {}
        old_stage = str(old.get("stage") or "RESEARCH")
        old_rank = int(old.get("rank") or 0)
        current[key] = {
            "stage": stage,
            "rank": rank,
            "token_address": row.get("token_address") or row.get("token") or row.get("mint"),
            "pair_address": row.get("pair_address"),
            "symbol": row.get("symbol"),
            "last_observed_at": reference.isoformat(),
        }

        # First execution establishes a baseline and never replays historical research.
        if not state_exists:
            continue
        # EVIDENCE_READY and all earlier stages are dashboard/state only. Telegram
        # starts at PAPER_BUY_CANDIDATE (one stage before BUY) and only on upward moves.
        if rank <= old_rank or rank < MIN_USER_FACING_RANK:
            continue
        event = {"key": key, "from_stage": old_stage, "to_stage": stage, "rank": rank}
        eligible.append(event)
        if not configured:
            continue
        try:
            message_id, attempts = sender(token, chat_id, _message(row, old_stage, stage))
            event = dict(event)
            event.update({"sent_at": reference.isoformat(), "telegram_message_id": message_id, "delivery_attempts": attempts})
            delivered.append(event)
        except Exception as exc:
            errors.append({**event, "error": f"{type(exc).__name__}: {exc}"[:300]})
            # Delivery failure must not consume the transition. Preserve prior state so next run retries.
            if old:
                current[key] = old
            else:
                current.pop(key, None)

    state_payload = {"version": 2, "updated_at": reference.isoformat(), "candidates": current}
    report = {
        "version": 2,
        "mode": "PRE_BUY_AND_STRONGER_STAGE_TELEGRAM",
        "updated_at": reference.isoformat(),
        "source": SOURCE,
        "configured": configured,
        "baseline_only": not state_exists,
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "eligible": eligible,
        "delivered": delivered,
        "errors": errors,
        "policy": {
            "raw_research_notifications": False,
            "evidence_ready_notifications": False,
            "minimum_user_facing_stage": MIN_USER_FACING_STAGE,
            "minimum_user_facing_rank": MIN_USER_FACING_RANK,
            "only_upward_transitions": True,
            "exact_pair_scoped_state": True,
            "historical_replay_on_first_run": False,
            "automatic_buy": False,
            "real_alert_pipeline_unchanged": True,
        },
    }
    _write(out / STATE, state_payload)
    _write(out / REPORT, report)
    return report


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
