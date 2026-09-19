from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
TOP_N = 10
MIN_CHANGE_PCT = 15.0
MIN_QUOTE_VOLUME_USD = 20_000.0
LEADERBOARD_BONUS = 8
WATCH_SCORE = 25
ALERT_SCORE = 35
NON_USD_REGIONAL_EXCHANGES = {"upbit"}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _load_state(path: Path) -> dict:
    gz = Path(str(path) + ".gz")
    try:
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8") as f:
                raw = json.load(f)
                return raw if isinstance(raw, dict) else {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}
    return {}


def _write_state(path: Path, state: dict) -> None:
    gz = Path(str(path) + ".gz")
    tmp = Path(str(gz) + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(state, f, separators=(",", ":"))
    tmp.replace(gz)
    if path.exists():
        path.unlink()


def _f(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _base_score(change: float, volume: float, volume_comparable: bool = True) -> int:
    score = 0
    if change >= 8:
        score += 10
    if change >= 20:
        score += 10
    if change >= 50:
        score += 5
    if volume_comparable and volume >= 100_000:
        score += 3
    if volume_comparable and volume >= 1_000_000:
        score += 2
    return score


def _latest_market_rows(state: dict) -> list[dict]:
    markets = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    out = []
    for key, history in markets.items():
        if not isinstance(key, str) or not key.startswith("spot:") or not isinstance(history, list) or not history:
            continue
        # Current state keys are `spot:<exchange>:<canonical_symbol>:<raw_market_id>`.
        # Older/bootstrap state used `spot:<exchange>:<canonical_symbol>`. Support
        # both forms while never allowing raw market IDs to contaminate symbols.
        parts = key.split(":", 3)
        if len(parts) == 4:
            _, exchange, symbol, market_id = parts
        elif len(parts) == 3:
            _, exchange, symbol = parts
            market_id = symbol
        else:
            continue
        latest = history[-1] if isinstance(history[-1], dict) else {}
        if not symbol.endswith("USDT"):
            continue
        inferred_regional = exchange in NON_USD_REGIONAL_EXCHANGES
        comparable = bool(latest.get("volume_comparable_usd_like", not inferred_regional))
        out.append(
            {
                "exchange": exchange,
                "market_type": "spot",
                "symbol": symbol,
                "market_id": latest.get("market_id") or market_id,
                "price": _f(latest.get("price")),
                "change_24h_pct": _f(latest.get("change_24h_pct")),
                "volume_24h": _f(latest.get("volume_24h")),
                "quote_symbol": latest.get("quote_symbol") or ("KRW" if inferred_regional else "USDT"),
                "volume_comparable_usd_like": comparable,
                "regional_market": bool(latest.get("regional_market", inferred_regional)),
                "observed_at": latest.get("observed_at"),
                "price_delta_pct": 0.0,
                "volume24_delta_pct": 0.0,
                "history_points": max(0, len(history) - 1),
            }
        )
    return out


def _rank(rows: list[dict]) -> dict[str, list[dict]]:
    by_exchange: dict[str, list[dict]] = {}
    for row in rows:
        if _f(row.get("change_24h_pct")) < MIN_CHANGE_PCT:
            continue
        if row.get("volume_comparable_usd_like", True) and _f(row.get("volume_24h")) < MIN_QUOTE_VOLUME_USD:
            continue
        by_exchange.setdefault(str(row.get("exchange") or "unknown"), []).append(row)

    by_symbol: dict[str, list[dict]] = {}
    for exchange, items in by_exchange.items():
        items.sort(key=lambda x: (_f(x.get("change_24h_pct")), _f(x.get("volume_24h"))), reverse=True)
        for rank, row in enumerate(items[:TOP_N], start=1):
            enriched = {**row, "leaderboard_rank": rank, "leaderboard_exchange": exchange}
            by_symbol.setdefault(str(row.get("symbol") or ""), []).append(enriched)
    return by_symbol


def _snapshot(now: str, rows: list[dict], score: int, kind: str) -> dict:
    best = min(rows, key=lambda x: int(x.get("leaderboard_rank") or 9999))
    return {
        "kind": kind,
        "observed_at": now,
        "reference_exchange": best.get("exchange"),
        "reference_price": _f(best.get("price")),
        "reference_change_24h_pct": _f(best.get("change_24h_pct")),
        "score": int(score),
        "confirmations": len({x.get("exchange") for x in rows if x.get("exchange")}),
        "coherent_confirmations": len({
            x.get("exchange")
            for x in rows
            if x.get("exchange") and x.get("volume_comparable_usd_like", True)
        }),
        "coherent_exchange": best.get("exchange"),
        "coherent_feature_hits": ["MOMENTUM", "LEADERBOARD_TOP10"],
        "price_acceleration_max_pct": 0.0,
        "volume_acceleration_max_pct": 0.0,
        "change_24h_max_pct": round(max((_f(x.get("change_24h_pct")) for x in rows), default=0.0), 4),
        "leaderboard_best_rank": min((int(x.get("leaderboard_rank") or 9999) for x in rows), default=9999),
    }


def run(data_dir: Path = DATA, now: str | None = None) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc).isoformat()
    radar_path = data_dir / "cex-spot-revival-radar.json"
    state_path = data_dir / "cex-spot-state.json"
    leaderboard_path = data_dir / "cex-spot-leaderboard.json"

    radar = _load(radar_path, {})
    state = _load_state(state_path)
    if not isinstance(radar, dict) or not radar or not state:
        report = {
            "version": 1,
            "generated_at": now,
            "status": "DEGRADED_FAIL_CLOSED_MISSING_SOURCE",
            "research_only": True,
            "automatic_buy": False,
            "injected_count": 0,
            "annotated_count": 0,
            "leaderboard_symbols": 0,
        }
        leaderboard_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    ranked = _rank(_latest_market_rows(state))
    watchlist = [dict(x) for x in (radar.get("watchlist") or []) if isinstance(x, dict)]
    existing = {str(x.get("symbol") or ""): i for i, x in enumerate(watchlist)}
    milestones = state.get("signal_milestones") if isinstance(state.get("signal_milestones"), dict) else {}
    state["signal_milestones"] = milestones

    injected = 0
    annotated = 0
    leaderboard_rows = []
    for symbol, rows in ranked.items():
        if not symbol:
            continue
        rows.sort(key=lambda x: int(x.get("leaderboard_rank") or 9999))
        best_rank = min(int(x.get("leaderboard_rank") or 9999) for x in rows)
        best_change = max(_f(x.get("change_24h_pct")) for x in rows)
        comparable_rows = [x for x in rows if x.get("volume_comparable_usd_like", True)]
        best_volume = max((_f(x.get("volume_24h")) for x in comparable_rows), default=0.0)
        boosted = min(
            100,
            max(
                _base_score(
                    _f(x.get("change_24h_pct")),
                    _f(x.get("volume_24h")),
                    bool(x.get("volume_comparable_usd_like", True)),
                )
                + LEADERBOARD_BONUS
                for x in rows
            ),
        )
        exchanges = sorted({str(x.get("exchange")) for x in rows if x.get("exchange")})
        usd_like_exchanges = sorted({
            str(x.get("exchange"))
            for x in rows
            if x.get("exchange") and x.get("volume_comparable_usd_like", True)
        })
        regional_exchanges = sorted({
            str(x.get("exchange"))
            for x in rows
            if x.get("exchange") and not x.get("volume_comparable_usd_like", True)
        })
        reason = f"top-{TOP_N} CEX spot gainer rank #{best_rank}; current 24h move {best_change:.2f}%"

        ms = milestones.setdefault(symbol, {})
        if "first_seen" not in ms:
            ms["first_seen"] = _snapshot(now, rows, boosted, "FIRST_SEEN")
        if "first_anomaly" not in ms:
            ms["first_anomaly"] = _snapshot(now, rows, boosted, "FIRST_ANOMALY")
        if boosted >= WATCH_SCORE and "first_watch" not in ms:
            ms["first_watch"] = _snapshot(now, rows, boosted, "FIRST_WATCH")
        if boosted >= ALERT_SCORE and "first_alert" not in ms:
            ms["first_alert"] = _snapshot(now, rows, boosted, "FIRST_ALERT")

        if symbol in existing:
            idx = existing[symbol]
            row = watchlist[idx]
            row["spot_revival_score"] = max(int(row.get("spot_revival_score") or 0), boosted)
            row["leaderboard_watch"] = True
            row["leaderboard_best_rank"] = best_rank
            row["leaderboard_exchanges"] = exchanges
            row["leaderboard_usd_like_exchanges"] = usd_like_exchanges
            row["leaderboard_regional_exchanges"] = regional_exchanges
            row["leaderboard_bonus"] = LEADERBOARD_BONUS
            row["leaderboard_change_24h_max_pct"] = round(best_change, 4)
            row["leaderboard_volume_24h_max"] = round(best_volume, 4)
            reasons = list(row.get("reasons") or [])
            if reason not in reasons:
                reasons.append(reason)
            row["reasons"] = reasons
            hits = list(row.get("coherent_feature_hits") or [])
            if "LEADERBOARD_TOP10" not in hits:
                hits.append("LEADERBOARD_TOP10")
            row["coherent_feature_hits"] = hits
            row["milestones"] = ms
            if row["spot_revival_score"] >= ALERT_SCORE:
                row["status"] = "DNA_WATCH_RESEARCH"
            watchlist[idx] = row
            annotated += 1
        else:
            record = {
                "symbol": symbol,
                "market_type": "spot",
                "spot_revival_score": max(WATCH_SCORE, boosted),
                "status": "DNA_WATCH_RESEARCH" if boosted >= ALERT_SCORE else "MOMENTUM_WATCH_RESEARCH",
                "research_only": True,
                "actionable": False,
                "identity_required_before_actionable": True,
                "reasons": [reason, "leaderboard bridge is discovery-only; exact veteran identity required downstream"],
                "confirmations": len(exchanges),
                "coherent_confirmations": len(usd_like_exchanges),
                "coherent_exchange": rows[0].get("exchange"),
                "coherent_feature_hits": ["MOMENTUM", "LEADERBOARD_TOP10"],
                "change_24h_max_pct": round(best_change, 4),
                "price_acceleration_max_pct": 0.0,
                "volume_acceleration_max_pct": 0.0,
                "leaderboard_watch": True,
                "leaderboard_best_rank": best_rank,
                "leaderboard_exchanges": exchanges,
                "leaderboard_usd_like_exchanges": usd_like_exchanges,
                "leaderboard_regional_exchanges": regional_exchanges,
                "leaderboard_bonus": LEADERBOARD_BONUS,
                "leaderboard_change_24h_max_pct": round(best_change, 4),
                "leaderboard_volume_24h_max": round(best_volume, 4),
                "exchanges": exchanges,
                "milestones": ms,
                "markets": rows,
            }
            existing[symbol] = len(watchlist)
            watchlist.append(record)
            injected += 1

        leaderboard_rows.append(
            {
                "symbol": symbol,
                "best_rank": best_rank,
                "exchanges": exchanges,
                "change_24h_max_pct": round(best_change, 4),
                "volume_24h_max": round(best_volume, 4),
                "volume_24h_scope": "USD_LIKE_QUOTES_ONLY",
                "regional_exchanges": regional_exchanges,
                "boosted_score": boosted,
                "was_injected": symbol not in {str(x.get("symbol") or "") for x in (radar.get("watchlist") or []) if isinstance(x, dict)},
            }
        )

    _write_state(state_path, state)
    watchlist.sort(
        key=lambda x: (
            int(x.get("spot_revival_score") or 0),
            -int(x.get("leaderboard_best_rank") or 9999),
            int(x.get("coherent_confirmations") or 0),
            int(x.get("confirmations") or 0),
        ),
        reverse=True,
    )
    alerts = [x for x in watchlist if int(x.get("spot_revival_score") or 0) >= ALERT_SCORE]

    bridge_meta = {
        "status": "OK",
        "research_only": True,
        "automatic_buy": False,
        "top_n_per_exchange": TOP_N,
        "minimum_change_24h_pct": MIN_CHANGE_PCT,
        "minimum_quote_volume_usd": MIN_QUOTE_VOLUME_USD,
        "leaderboard_bonus": LEADERBOARD_BONUS,
        "injected_count": injected,
        "annotated_count": annotated,
        "leaderboard_symbols": len(ranked),
        "rule": "CURRENT_TOP_GAINER_RANK_IS_DISCOVERY_EVIDENCE_ONLY; NATIVE_QUOTE_VOLUME_NEVER_TREATED_AS_USD; EXACT_CHAIN_CONTRACT_180D_AND_PAIR_GATES_REMAIN_FAIL_CLOSED",
    }
    radar["leaderboard_bridge"] = bridge_meta
    radar["watch_count"] = len(watchlist)
    radar["alerts_count"] = len(alerts)
    radar["watchlist"] = watchlist[:100]
    radar["alerts"] = alerts[:100]
    radar_path.write_text(json.dumps(radar, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "version": 1,
        "generated_at": now,
        **bridge_meta,
        "leaderboard": sorted(leaderboard_rows, key=lambda x: (x["best_rank"], -x["change_24h_max_pct"], x["symbol"]))[:100],
    }
    leaderboard_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))