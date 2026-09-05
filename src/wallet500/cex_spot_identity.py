from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .cex_identity import run as resolve_exact_identity
from .cex_identity_preflight import run as verify_age_and_coin_identity

DATA = Path("data")
MAX_WATCH_CANDIDATES = 60


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


def _status(row: dict) -> str:
    identity = str(row.get("identity_status") or "")
    if identity == "DEX_VERIFIED":
        return "CEX_SPOT_EXACT_IDENTITY_RESEARCH"
    if identity == "IDENTITY_RESOLVED_PAIR_PENDING":
        return "CEX_SPOT_IDENTITY_RESOLVED_PAIR_PENDING_RESEARCH"
    return "CEX_SPOT_IDENTITY_PENDING_RESEARCH"


def _persist_verified_registry(data_dir: Path, rows: list[dict], now: str) -> dict:
    """Self-expand the veteran identity registry only from fully exact, conflict-free evidence."""
    path = data_dir / "cex-identity-registry.json"
    registry = _load(path, {})
    if not isinstance(registry, dict):
        registry = {}
    symbols = registry.get("symbols") if isinstance(registry.get("symbols"), dict) else {}
    added = []
    confirmed = []
    conflicts = []

    for row in rows:
        if row.get("identity_status") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
            continue
        if row.get("market_age_verified") is not True:
            continue
        symbol = _base_symbol(row.get("symbol"))
        coin_id = str(row.get("coingecko_id") or "").strip()
        chain = str(row.get("chain") or "").lower().strip()
        token = str(row.get("token_address") or "").strip()
        pair = str(row.get("pair_address") or "").strip()
        age_at = str(row.get("market_age_evidence_at") or "").strip()
        if not all((symbol, coin_id, chain, token, pair, age_at)):
            continue

        existing = symbols.get(symbol)
        if isinstance(existing, dict):
            same = (
                str(existing.get("coingecko_id") or "") == coin_id
                and str(existing.get("chain") or "").lower() == chain
                and str(existing.get("token_address") or "").lower() == token.lower()
            )
            if same:
                confirmed.append(symbol)
            else:
                conflicts.append({
                    "symbol": symbol,
                    "reason": "EXISTING_EXACT_REGISTRY_CONFLICT_PRESERVED_FAIL_CLOSED",
                    "existing_coingecko_id": existing.get("coingecko_id"),
                    "candidate_coingecko_id": coin_id,
                })
            continue

        symbols[symbol] = {
            "coingecko_id": coin_id,
            "chain": chain,
            "token_address": token,
            "market_age_evidence_at": age_at,
            "evidence_source": "AUTO_STRICT_CEX_SPOT_CGID_AGE_PLUS_EXACT_DEX_PAIR",
            "evidence_note": (
                "Automatically learned only after strict CEX symbol identity, >=180d age evidence, "
                "exact on-chain chain+contract resolution and an exact-address DEX pair. This is an "
                "identity seed only; all liquidity, holder, survival and REAL ALERT gates still apply."
            ),
            "auto_verified_pair_address": pair,
            "auto_verified_at": now,
        }
        added.append(symbol)

    if added:
        registry["version"] = max(int(registry.get("version") or 0), 3)
        registry["updated_at"] = now
        registry["policy"] = "EXACT_IDENTITY_SEEDS_ONLY_NO_SYMBOL_ONLY_ACTIONABILITY"
        registry["symbols"] = symbols
        _write(path, registry)

    return {
        "added": added,
        "confirmed_existing": confirmed,
        "conflicts": conflicts,
        "added_count": len(added),
        "conflict_count": len(conflicts),
        "rule": "ONLY_DEX_VERIFIED_PLUS_180D_EXACT_IDENTITY_CAN_SELF_REGISTER; EXISTING_CONFLICT_NEVER_OVERWRITTEN",
    }


def run(data_dir: Path = DATA) -> dict:
    """Resolve veteran CEX Spot watches to exact on-chain identity without relaxing action gates.

    Symbol-only momentum is useful for discovery but is never actionable. This lane first
    resolves one CoinGecko identity with price/exchange coherence and >=180d age evidence,
    then resolves an exact chain+contract and exact DEX pair. Unresolved rows remain research
    only and can never promote a REAL ALERT or an automatic buy.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    spot_path = data_dir / "cex-spot-revival-radar.json"
    out_path = data_dir / "cex-spot-identity-radar.json"
    spot = _load(spot_path, {})
    watch = [x for x in (spot.get("watchlist") or []) if isinstance(x, dict)][:MAX_WATCH_CANDIDATES]

    base = {
        "version": 1,
        "generated_at": now,
        "source_generated_at": spot.get("generated_at"),
        "mode": "RESEARCH_ONLY_DYNAMIC_CEX_SPOT_EXACT_IDENTITY_V1",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "symbol_only_actionable": False,
        "minimum_market_age_days": 180,
        "truth_contract": {
            "symbol_only_never_actionable": True,
            "unique_or_strictly_coherent_coin_identity_required": True,
            "exact_onchain_contract_required": True,
            "exact_dex_pair_required_before_registry_learning": True,
            "cex_only_never_real_alert": True,
            "hard_liquidity_and_survival_gates_unchanged": True,
            "existing_registry_conflict_never_overwritten": True,
        },
        "source_watch_count": len(watch),
    }
    if not watch:
        payload = {
            **base,
            "status": "HEALTHY_EMPTY",
            "counts": {"age_identity_verified": 0, "dex_verified": 0, "pair_pending": 0, "identity_pending": 0},
            "auto_registry": {"added": [], "confirmed_existing": [], "conflicts": [], "added_count": 0, "conflict_count": 0},
            "candidates": [],
            "rejections": [],
        }
        _write(out_path, payload)
        return payload

    temp = data_dir / ".cex-spot-identity-work.json"
    _write(temp, {
        "version": 1,
        "generated_at": spot.get("generated_at") or now,
        "alerts": watch,
        "alerts_count": len(watch),
    })
    try:
        age_report = verify_age_and_coin_identity(temp)
        resolve_exact_identity(temp)
        resolved = _load(temp, {})
        rows = []
        for row in resolved.get("alerts") or []:
            if not isinstance(row, dict):
                continue
            rows.append({
                **row,
                "status": _status(row),
                "research_only": True,
                "actionable": False,
                "automatic_buy": False,
                "source_lane": "CEX_SPOT_DYNAMIC_EXACT_IDENTITY",
            })
        registry_report = _persist_verified_registry(data_dir, rows, now)
        counts = {
            "age_identity_verified": len(rows),
            "dex_verified": sum(1 for x in rows if x.get("identity_status") == "DEX_VERIFIED"),
            "pair_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_RESOLVED_PAIR_PENDING"),
            "identity_pending": sum(1 for x in rows if x.get("identity_status") == "IDENTITY_PENDING"),
        }
        payload = {
            **base,
            "status": "OK",
            "counts": counts,
            "auto_registry": registry_report,
            "age_identity_preflight": age_report,
            "platform_catalog": resolved.get("platform_catalog"),
            "identity_contract": resolved.get("identity_contract"),
            "candidates": rows,
            "rejections": list((age_report or {}).get("rejections") or []),
        }
    except Exception as exc:
        payload = {
            **base,
            "status": "DEGRADED_FAIL_CLOSED",
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "counts": {"age_identity_verified": 0, "dex_verified": 0, "pair_pending": 0, "identity_pending": len(watch)},
            "auto_registry": {"added": [], "confirmed_existing": [], "conflicts": [], "added_count": 0, "conflict_count": 0},
            "candidates": [],
            "rejections": [],
        }
    finally:
        try:
            temp.unlink(missing_ok=True)
        except Exception:
            pass

    _write(out_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
