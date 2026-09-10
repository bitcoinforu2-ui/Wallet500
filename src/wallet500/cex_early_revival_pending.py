from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
MIN_EARLY_ALERT_SCORE = 35
MIN_EARLY_WATCH_SCORE = 25
MIN_COHERENT_CONFIRMATIONS = 2
MIN_PRICE_ACCEL_PCT = 2.0
MIN_VOLUME_ACCEL_PCT = 8.0
LATE_MOVE_PCT = 100.0


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_symbol(value: object) -> str:
    s = str(value or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()
    return s[:-4] if s.endswith("USDT") else s


def _i(value: object) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _f(value: object) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _milestone(cur: dict, old: dict, name: str) -> dict:
    ms = cur.get("milestones") if isinstance(cur.get("milestones"), dict) else {}
    if not ms:
        ms = old.get("milestones") if isinstance(old.get("milestones"), dict) else {}
    row = ms.get(name) if isinstance(ms.get(name), dict) else {}
    return row


def run(data_dir: Path = DATA) -> dict:
    """Persist early CEX Spot evidence until exact identity is resolved.

    Research/observability only. The lane deliberately keeps a pre-alert watch milestone
    when it has multi-exchange coherence plus price/volume acceleration, because waiting
    for the full score can turn discovery into a post-pump observation. It never bypasses
    exact identity, pair, liquidity, age, survival, or production validation gates.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    spot = _load(data_dir / "cex-spot-revival-radar.json", {})
    identity = _load(data_dir / "cex-spot-identity-radar.json", {})
    previous = _load(data_dir / "cex-early-revival-pending.json", {})

    resolved = set()
    for row in identity.get("candidates") or []:
        if isinstance(row, dict) and row.get("identity_status") == "DEX_VERIFIED" and row.get("identity_verified") is True:
            resolved.add(_base_symbol(row.get("symbol")))

    prior = {}
    for row in previous.get("candidates") or []:
        if isinstance(row, dict):
            symbol = _base_symbol(row.get("symbol"))
            if symbol:
                prior[symbol] = row

    current_by_symbol = {}
    for row in spot.get("watchlist") or []:
        if not isinstance(row, dict):
            continue
        symbol = _base_symbol(row.get("symbol"))
        if symbol:
            current_by_symbol[symbol] = row

    symbols = set(prior) | set(current_by_symbol)
    candidates = []
    for symbol in sorted(symbols):
        cur = current_by_symbol.get(symbol, {})
        old = prior.get(symbol, {})
        milestones = cur.get("milestones") if isinstance(cur.get("milestones"), dict) else {}
        if not milestones:
            milestones = old.get("milestones") if isinstance(old.get("milestones"), dict) else {}

        first_watch = _milestone(cur, old, "first_watch")
        first_alert = _milestone(cur, old, "first_alert")

        alert_score = _i(first_alert.get("score") or old.get("first_alert_score"))
        alert_coherent = _i(first_alert.get("coherent_confirmations") or old.get("first_alert_coherent_confirmations"))
        alert_qualifies = alert_score >= MIN_EARLY_ALERT_SCORE and alert_coherent >= MIN_COHERENT_CONFIRMATIONS

        watch_score = _i(first_watch.get("score") or old.get("first_watch_score"))
        watch_coherent = _i(first_watch.get("coherent_confirmations") or old.get("first_watch_coherent_confirmations"))
        watch_price_acc = _f(first_watch.get("price_acceleration_max_pct") or old.get("first_watch_price_acceleration_max_pct"))
        watch_volume_acc = _f(first_watch.get("volume_acceleration_max_pct") or old.get("first_watch_volume_acceleration_max_pct"))
        watch_qualifies = (
            watch_score >= MIN_EARLY_WATCH_SCORE
            and watch_coherent >= MIN_COHERENT_CONFIRMATIONS
            and (watch_price_acc >= MIN_PRICE_ACCEL_PCT or watch_volume_acc >= MIN_VOLUME_ACCEL_PCT)
        )

        if not (alert_qualifies or watch_qualifies):
            continue
        if symbol in resolved:
            continue

        anchor = first_watch if watch_qualifies else first_alert
        anchor_kind = "FIRST_WATCH" if watch_qualifies else "FIRST_ALERT"
        anchor_change = _f(anchor.get("change_24h_max_pct") or anchor.get("reference_change_24h_pct"))
        timing_quality = "LATE_BREAKOUT_ALREADY_EXTENDED" if anchor_change >= LATE_MOVE_PCT else "EARLY_BREAKOUT_EVIDENCE"

        candidates.append({
            "symbol": cur.get("symbol") or old.get("symbol") or f"{symbol}USDT",
            "base_symbol": symbol,
            "status": "EARLY_REVIVAL_IDENTITY_PENDING_RESEARCH",
            "research_only": True,
            "actionable": False,
            "automatic_buy": False,
            "persistent_until_exact_identity_resolution": True,
            "earliest_retained_milestone": anchor_kind,
            "timing_quality": timing_quality,
            "first_watch_score": watch_score or old.get("first_watch_score"),
            "first_watch_coherent_confirmations": watch_coherent or old.get("first_watch_coherent_confirmations"),
            "first_watch_observed_at": first_watch.get("observed_at") or old.get("first_watch_observed_at"),
            "first_watch_reference_price": first_watch.get("reference_price") if first_watch else old.get("first_watch_reference_price"),
            "first_watch_price_acceleration_max_pct": watch_price_acc or old.get("first_watch_price_acceleration_max_pct"),
            "first_watch_volume_acceleration_max_pct": watch_volume_acc or old.get("first_watch_volume_acceleration_max_pct"),
            "first_alert_score": alert_score or old.get("first_alert_score"),
            "first_alert_coherent_confirmations": alert_coherent or old.get("first_alert_coherent_confirmations"),
            "first_alert_observed_at": first_alert.get("observed_at") or old.get("first_alert_observed_at"),
            "first_alert_reference_price": first_alert.get("reference_price") if first_alert else old.get("first_alert_reference_price"),
            "first_alert_reference_exchange": first_alert.get("reference_exchange") if first_alert else old.get("first_alert_reference_exchange"),
            "current_score": cur.get("spot_revival_score", old.get("current_score")),
            "current_coherent_confirmations": cur.get("coherent_confirmations", old.get("current_coherent_confirmations")),
            "current_change_24h_max_pct": cur.get("change_24h_max_pct", old.get("current_change_24h_max_pct")),
            "milestones": milestones,
            "promotion_rule": "EXACT_IDENTITY_RESOLUTION_REQUIRED_BEFORE_ANY_ONCHAIN_PROMOTION",
        })

    candidates.sort(
        key=lambda x: (
            x.get("timing_quality") == "EARLY_BREAKOUT_EVIDENCE",
            _i(x.get("first_alert_score")),
            _i(x.get("first_watch_score")),
        ),
        reverse=True,
    )
    payload = {
        "version": 2,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_PERSISTENT_EARLY_REVIVAL_PENDING_V2",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "minimum_first_alert_score": MIN_EARLY_ALERT_SCORE,
        "minimum_first_watch_score": MIN_EARLY_WATCH_SCORE,
        "minimum_coherent_confirmations": MIN_COHERENT_CONFIRMATIONS,
        "minimum_price_acceleration_pct": MIN_PRICE_ACCEL_PCT,
        "minimum_volume_acceleration_pct": MIN_VOLUME_ACCEL_PCT,
        "late_move_pct": LATE_MOVE_PCT,
        "truth_contract": {
            "no_hindsight": True,
            "first_seen_watch_alert_timestamps_immutable": True,
            "symbol_only_never_actionable": True,
            "exact_chain_contract_required": True,
            "exact_dex_pair_required": True,
            "production_liquidity_and_survival_gates_unchanged": True,
            "pre_alert_retention_is_research_only": True,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    _write(data_dir / "cex-early-revival-pending.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
