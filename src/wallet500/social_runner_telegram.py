from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .telegram_alerts import _send

SOCIAL_SOURCE = "social-runner-research.json"
CANDIDATE_SOURCE = "candidate-evidence-envelope.json"
STATE = "social-runner-telegram-state.json"
REPORT = "social-runner-telegram-report.json"

SOCIAL_MODE = "RESEARCH_ONLY_SOCIAL_RUNNER_INTELLIGENCE_V1"
CANDIDATE_MODE = "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1"
PREBUY_STAGE = "PAPER_BUY_CANDIDATE"
SOCIAL_STAGE = "CONFIRMED_RUNNER"
MAX_SOURCE_AGE_SECONDS = 90 * 60


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        out = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def _fresh(value: Any, now: datetime, max_age_seconds: float = MAX_SOURCE_AGE_SECONDS) -> bool:
    ts = _dt(value)
    if ts is None:
        return False
    age = (now - ts).total_seconds()
    return -120 <= age <= max_age_seconds


def _norm_chain(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {"eth": "ethereum", "binance": "bsc", "bnb": "bsc", "sol": "solana"}
    return aliases.get(raw, raw)


def _norm_token(chain: str, value: Any) -> str:
    raw = str(value or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "polygon", "optimism"}:
        return raw.lower()
    return raw


def _candidate_identity(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    chain = _norm_chain(row.get("chain") or row.get("network"))
    token = _norm_token(
        chain,
        row.get("token_address") or row.get("token") or row.get("mint") or row.get("contract"),
    )
    pair = str(row.get("pair_address") or "").strip()
    if not chain or not token or not pair:
        return None
    return chain, token, pair.lower()


def _social_identity(row: Mapping[str, Any]) -> tuple[str, str] | None:
    chain = _norm_chain(row.get("chain"))
    token = _norm_token(chain, row.get("contract") or row.get("token_address") or row.get("mint"))
    if not chain or not token:
        return None
    return chain, token


def _candidate_stage(row: Mapping[str, Any]) -> str:
    return str(row.get("status") or row.get("stage") or "").upper().strip()


def _social_is_confirmed(row: Mapping[str, Any]) -> bool:
    c = row.get("classification") if isinstance(row.get("classification"), Mapping) else {}
    if str(c.get("state") or "").upper() != SOCIAL_STAGE:
        return False
    if c.get("late_attention_penalty") is True:
        return False
    if c.get("distribution_risk") is True or c.get("false_social_risk") is True:
        return False
    if int(c.get("market_confirmations") or 0) < 2:
        return False
    if int(c.get("onchain_confirmations") or 0) < 1:
        return False
    if c.get("automatic_buy") is not False or c.get("production_effect") is not False:
        return False
    return True


def _fmt_x(value: Any) -> str:
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct01(value: Any) -> str:
    try:
        return f"{float(value) * 100.0:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _dex_url(chain: str, pair: str) -> str:
    return f"https://dexscreener.com/{chain}/{pair}"


def _message(candidate: Mapping[str, Any], social: Mapping[str, Any]) -> str:
    features = social.get("features") if isinstance(social.get("features"), Mapping) else {}
    classification = social.get("classification") if isinstance(social.get("classification"), Mapping) else {}
    chain, token, pair = _candidate_identity(candidate) or ("unknown", "unknown", "unknown")
    symbol = str(candidate.get("symbol") or candidate.get("name") or social.get("symbol") or "UNKNOWN")
    reasons = classification.get("reasons") if isinstance(classification.get("reasons"), list) else []
    communities = int(features.get("unique_communities") or 0)
    first = int(features.get("first_time_communities") or 0)
    platforms = int(features.get("cross_platform_count") or 0)
    return "\n".join(
        [
            "🟠 WALLET500 — SOCIAL CONFLUENCE / קרוב מאוד לקנייה",
            "⚠️ עדיין לא BUY — Social הוא אישור נוסף בלבד; Decision Engine חייב לאשר BUY בנפרד.",
            f"Token: {symbol}",
            f"Chain: {chain}",
            f"Mint/Contract: {token}",
            f"Exact Pair: {pair}",
            f"Social state: {SOCIAL_STAGE}",
            f"Attention 3h/21d: {_fmt_x(features.get('attention_jump_3h_vs_21d'))}",
            f"Velocity 3d/21d: {_fmt_x(features.get('velocity_3d_vs_21d'))}",
            f"Organic: {_fmt_pct01(features.get('organic_share'))}",
            f"Communities: {communities} | first-time: {first}",
            f"Cross-platform: {platforms}",
            f"Market confirmations: {int(classification.get('market_confirmations') or 0)}",
            f"On-chain confirmations: {int(classification.get('onchain_confirmations') or 0)}",
            f"Reasons: {', '.join(map(str, reasons)) if reasons else 'n/a'}",
            f"DEX: {_dex_url(chain, pair)}",
            "התראת BUY תישלח רק אם מסלול ה-REAL ALERT / Decision Engine עובר את שער הקנייה.",
        ]
    )


def _social_index(source: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    out: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in source.get("rows") or []:
        if not isinstance(row, Mapping) or not _social_is_confirmed(row):
            continue
        identity = _social_identity(row)
        if identity is None:
            continue
        previous = out.get(identity)
        if previous is None or str(row.get("observed_at") or "") > str(previous.get("observed_at") or ""):
            out[identity] = row
    return out


def run(output_dir: str | None = None, now: datetime | None = None, sender=_send) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    reference = now or datetime.now(timezone.utc)
    social_source = _load(out / SOCIAL_SOURCE, {})
    candidate_source = _load(out / CANDIDATE_SOURCE, {})
    state = _load(out / STATE, {"version": 1, "pairs": {}})
    previous = state.get("pairs") if isinstance(state.get("pairs"), dict) else {}

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(token and chat_id)

    social_source_valid = (
        isinstance(social_source, Mapping)
        and social_source.get("mode") == SOCIAL_MODE
        and social_source.get("research_only") is True
        and social_source.get("production_effect") is False
        and social_source.get("automatic_buy") is False
        and _fresh(social_source.get("generated_at"), reference)
    )
    candidate_source_present = isinstance(candidate_source, Mapping) and bool(candidate_source)
    candidate_source_valid = (
        candidate_source_present
        and candidate_source.get("mode") == CANDIDATE_MODE
        and candidate_source.get("production_change") is False
        and candidate_source.get("automatic_buy") is False
        and _fresh(candidate_source.get("generated_at"), reference)
    )

    social = _social_index(social_source) if social_source_valid else {}
    current: dict[str, dict] = {}
    eligible: list[dict] = []
    delivered: list[dict] = []
    errors: list[dict] = []

    candidates = candidate_source.get("candidates") if candidate_source_valid else []
    for row in candidates or []:
        if not isinstance(row, Mapping):
            continue
        identity = _candidate_identity(row)
        if identity is None:
            continue
        chain, contract, pair = identity
        key = f"{chain}|{contract}|{pair}"
        old = previous.get(key) if isinstance(previous.get(key), dict) else {}
        old_eligible = old.get("eligible") is True
        social_row = social.get((chain, contract))
        joint_eligible = _candidate_stage(row) == PREBUY_STAGE and social_row is not None

        current[key] = {
            "eligible": joint_eligible,
            "stage": _candidate_stage(row),
            "social_state": SOCIAL_STAGE if social_row is not None else None,
            "last_observed_at": reference.isoformat(),
        }

        if not joint_eligible or old_eligible:
            continue

        event = {
            "key": key,
            "chain": chain,
            "contract": contract,
            "pair_address": pair,
            "symbol": row.get("symbol") or row.get("name") or (social_row or {}).get("symbol"),
            "candidate_stage": _candidate_stage(row),
            "social_state": SOCIAL_STAGE,
        }
        eligible.append(event)

        if not configured:
            current[key] = old or {"eligible": False}
            continue
        try:
            message_id, attempts = sender(token, chat_id, _message(row, social_row))
            delivered.append(
                {
                    **event,
                    "sent_at": reference.isoformat(),
                    "telegram_message_id": message_id,
                    "delivery_attempts": attempts,
                }
            )
        except Exception as exc:
            errors.append({**event, "error": f"{type(exc).__name__}: {exc}"[:300]})
            current[key] = old or {"eligible": False}

    # Preserve previously tracked pairs not present in a fresh candidate snapshot only
    # when the candidate source itself is unavailable/invalid. A valid snapshot that
    # drops a pair resets eligibility, allowing a future clean transition to alert.
    if not candidate_source_valid:
        current = dict(previous)

    state_payload = {
        "version": 1,
        "updated_at": reference.isoformat(),
        "pairs": current,
    }
    report = {
        "version": 1,
        "mode": "JOINT_PREBUY_SOCIAL_TELEGRAM_V1",
        "updated_at": reference.isoformat(),
        "configured": configured,
        "social_source_valid": social_source_valid,
        "candidate_source_present": candidate_source_present,
        "candidate_source_valid": candidate_source_valid,
        "confirmed_social_rows": len(social),
        "eligible_count": len(eligible),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "eligible": eligible,
        "delivered": delivered,
        "errors": errors,
        "policy": {
            "raw_social_notifications": False,
            "early_runner_notifications": False,
            "confirmed_runner_requires_prebuy": True,
            "candidate_stage_required": PREBUY_STAGE,
            "social_stage_required": SOCIAL_STAGE,
            "exact_chain_contract_pair_required": True,
            "late_attention_silent": True,
            "distribution_false_social_silent": True,
            "only_transition_into_joint_confirmation": True,
            "duplicate_steady_state_alerts": False,
            "automatic_buy": False,
            "real_alert_pipeline_unchanged": True,
            "final_buy_pipeline_separate": True,
        },
    }
    _write(out / STATE, state_payload)
    _write(out / REPORT, report)
    return report


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
