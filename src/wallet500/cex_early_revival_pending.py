from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
MIN_EARLY_ALERT_SCORE = 35
MIN_COHERENT_CONFIRMATIONS = 2


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


def run(data_dir: Path = DATA) -> dict:
    """Persist high-value CEX Spot early alerts until exact identity is resolved.

    This is a research/observability lane only. It never bypasses exact chain/contract,
    exact-pair, liquidity, age, survival, or production validation gates.
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
        first_alert = milestones.get("first_alert") if isinstance(milestones.get("first_alert"), dict) else {}
        first_alert_score = int(first_alert.get("score") or old.get("first_alert_score") or 0)
        first_alert_coherent = int(first_alert.get("coherent_confirmations") or old.get("first_alert_coherent_confirmations") or 0)

        qualifies = first_alert_score >= MIN_EARLY_ALERT_SCORE and first_alert_coherent >= MIN_COHERENT_CONFIRMATIONS
        if not qualifies:
            continue
        if symbol in resolved:
            continue

        candidates.append({
            "symbol": cur.get("symbol") or old.get("symbol") or f"{symbol}USDT",
            "base_symbol": symbol,
            "status": "EARLY_REVIVAL_IDENTITY_PENDING_RESEARCH",
            "research_only": True,
            "actionable": False,
            "automatic_buy": False,
            "persistent_until_exact_identity_resolution": True,
            "first_alert_score": first_alert_score,
            "first_alert_coherent_confirmations": first_alert_coherent,
            "first_alert_observed_at": first_alert.get("observed_at") or old.get("first_alert_observed_at"),
            "first_alert_reference_price": first_alert.get("reference_price") if first_alert else old.get("first_alert_reference_price"),
            "first_alert_reference_exchange": first_alert.get("reference_exchange") if first_alert else old.get("first_alert_reference_exchange"),
            "current_score": cur.get("spot_revival_score", old.get("current_score")),
            "current_coherent_confirmations": cur.get("coherent_confirmations", old.get("current_coherent_confirmations")),
            "current_change_24h_max_pct": cur.get("change_24h_max_pct", old.get("current_change_24h_max_pct")),
            "milestones": milestones,
            "promotion_rule": "EXACT_IDENTITY_RESOLUTION_REQUIRED_BEFORE_ANY_ONCHAIN_PROMOTION",
        })

    candidates.sort(key=lambda x: (int(x.get("first_alert_score") or 0), int(x.get("first_alert_coherent_confirmations") or 0)), reverse=True)
    payload = {
        "version": 1,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_PERSISTENT_EARLY_REVIVAL_PENDING_V1",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "minimum_first_alert_score": MIN_EARLY_ALERT_SCORE,
        "minimum_first_alert_coherent_confirmations": MIN_COHERENT_CONFIRMATIONS,
        "truth_contract": {
            "no_hindsight": True,
            "first_alert_timestamp_immutable": True,
            "symbol_only_never_actionable": True,
            "exact_chain_contract_required": True,
            "exact_dex_pair_required": True,
            "production_liquidity_and_survival_gates_unchanged": True,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    _write(data_dir / "cex-early-revival-pending.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
