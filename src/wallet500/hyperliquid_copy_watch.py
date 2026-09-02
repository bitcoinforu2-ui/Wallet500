from __future__ import annotations

import json
import math
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_URL = "https://api.hyperliquid.xyz/info"
CONFIG = Path("experiments/hyperliquid-copy-watch-v1.json")
LEDGER = Path("data/hyperliquid-copy-watch-ledger.json")
SUMMARY = Path("data/hyperliquid-copy-watch-summary.json")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso(ms: int | None = None) -> str:
    ts = (ms if ms is not None else _now_ms()) / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _post(payload: dict[str, Any], retries: int = 4) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Wallet500-HL-CopyWatch/1"},
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= retries - 1:
                raise
            time.sleep(min(8.0, 0.75 * (2**attempt)))
        except (urllib.error.URLError, TimeoutError):
            if attempt >= retries - 1:
                raise
            time.sleep(min(8.0, 0.5 * (2**attempt)))
    raise RuntimeError("HYPERLIQUID_INFO_RETRY_EXHAUSTED")


def _portfolio_map(rows: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str) and isinstance(row[1], dict):
            out[row[0]] = row[1]
    return out


def _history_delta(history: Any) -> float | None:
    pts = [(int(x[0]), _f(x[1])) for x in (history or []) if isinstance(x, list) and len(x) >= 2]
    if len(pts) < 2:
        return None
    return pts[-1][1] - pts[0][1]


def _history_span_days(history: Any) -> float:
    pts = [int(x[0]) for x in (history or []) if isinstance(x, list) and len(x) >= 2]
    if len(pts) < 2:
        return 0.0
    return max(0.0, (max(pts) - min(pts)) / 86_400_000)


def _max_drawdown_pct(history: Any) -> float | None:
    vals = [_f(x[1]) for x in (history or []) if isinstance(x, list) and len(x) >= 2 and _f(x[1]) > 0]
    if len(vals) < 2:
        return None
    peak = vals[0]
    worst = 0.0
    for v in vals:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak * 100.0)
    return worst


def _fill_id(fill: dict[str, Any]) -> str:
    tid = fill.get("tid")
    if tid is not None:
        return f"tid:{tid}"
    return "|".join(
        str(fill.get(k, ""))
        for k in ("hash", "oid", "time", "coin", "side", "px", "sz", "dir")
    )


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * p
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (rank - lo)


def _close_fill_stats(fills: list[dict[str, Any]], now_ms: int) -> dict[str, Any]:
    closes = []
    closes_30d = []
    recent_30d = []
    cutoff = now_ms - 30 * 86_400_000
    for f in fills:
        tm = int(f.get("time") or 0)
        if tm >= cutoff:
            recent_30d.append(f)
        direction = str(f.get("dir") or "")
        pnl = _f(f.get("closedPnl"))
        is_close = "Close" in direction or abs(pnl) > 0
        if is_close:
            closes.append(f)
            if tm >= cutoff:
                closes_30d.append(f)
    wins = sum(1 for f in closes if _f(f.get("closedPnl")) > 0)
    losses = sum(1 for f in closes if _f(f.get("closedPnl")) < 0)
    decided = wins + losses
    return {
        "returned_fill_count": len(fills),
        "closed_fill_events": len(closes),
        "wins": wins,
        "losses": losses,
        "close_win_rate_proxy_pct": (wins / decided * 100.0) if decided else None,
        "closed_pnl_30d_from_returned_fills": sum(_f(f.get("closedPnl")) for f in closes_30d),
        "fills_30d_from_returned_window": len(recent_30d),
        "fills_per_day_30d": len(recent_30d) / 30.0,
    }


def _score(row: dict[str, Any], cfg: dict[str, Any]) -> float:
    s = 0.0
    age = _f(row.get("history_span_days"))
    wr = _f(row.get("close_win_rate_proxy_pct"), -1)
    dd = row.get("max_drawdown_pct")
    month = row.get("month_pnl")
    alltime = row.get("all_time_pnl")
    fills_day = _f(row.get("fills_per_day_30d"))
    obs = int(row.get("forward_copy_observations") or 0)
    med = row.get("forward_median_abs_slippage_bps")
    p95 = row.get("forward_p95_abs_slippage_bps")

    s += min(20.0, max(0.0, age / max(1.0, _f(cfg.get("min_history_days"), 180)) * 20.0))
    if wr >= 0:
        s += min(25.0, max(0.0, wr / 80.0 * 25.0))
    if dd is not None:
        s += max(0.0, 20.0 * (1.0 - min(1.0, _f(dd) / 40.0)))
    if month is not None and _f(month) > 0:
        s += 10.0
    if alltime is not None and _f(alltime) > 0:
        s += 10.0
    max_fpd = _f(cfg.get("max_fills_per_day_30d"), 50)
    if fills_day <= max_fpd:
        s += 5.0
    min_obs = int(cfg.get("min_forward_observations_for_copyability") or 20)
    if obs >= min_obs and med is not None and p95 is not None:
        if _f(med) <= _f(cfg.get("max_forward_median_abs_slippage_bps"), 20):
            s += 5.0
        if _f(p95) <= _f(cfg.get("max_forward_p95_abs_slippage_bps"), 50):
            s += 5.0
    return round(min(100.0, s), 2)


def _decision(row: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if _f(row.get("history_span_days")) < _f(cfg.get("min_history_days"), 180):
        blockers.append("HISTORY_LT_180D")
    if int(row.get("closed_fill_events") or 0) < int(cfg.get("min_closed_fill_events") or 200):
        blockers.append("INSUFFICIENT_CLOSED_FILL_SAMPLE")
    wr = row.get("close_win_rate_proxy_pct")
    if wr is None or _f(wr) < _f(cfg.get("min_close_win_rate_proxy_pct"), 60):
        blockers.append("WIN_RATE_PROXY_BELOW_THRESHOLD")
    dd = row.get("max_drawdown_pct")
    if dd is None or _f(dd) > _f(cfg.get("max_drawdown_pct"), 20):
        blockers.append("DRAWDOWN_TOO_HIGH_OR_UNKNOWN")
    if cfg.get("require_positive_month_pnl") and (row.get("month_pnl") is None or _f(row.get("month_pnl")) <= 0):
        blockers.append("MONTH_PNL_NOT_POSITIVE")
    if cfg.get("require_positive_all_time_pnl") and (row.get("all_time_pnl") is None or _f(row.get("all_time_pnl")) <= 0):
        blockers.append("ALL_TIME_PNL_NOT_POSITIVE")
    if _f(row.get("fills_per_day_30d")) > _f(cfg.get("max_fills_per_day_30d"), 50):
        blockers.append("TOO_HIGH_FREQUENCY_FOR_COPY")
    if blockers:
        return "WATCH", blockers

    obs = int(row.get("forward_copy_observations") or 0)
    min_obs = int(cfg.get("min_forward_observations_for_copyability") or 20)
    if obs < min_obs:
        return "HISTORICAL_SHORTLIST_FORWARD_VALIDATION", ["NEED_MORE_FORWARD_COPY_OBSERVATIONS"]
    med = row.get("forward_median_abs_slippage_bps")
    p95 = row.get("forward_p95_abs_slippage_bps")
    if med is None or _f(med) > _f(cfg.get("max_forward_median_abs_slippage_bps"), 20):
        return "HISTORICAL_SHORTLIST_FORWARD_VALIDATION", ["FORWARD_MEDIAN_SLIPPAGE_TOO_HIGH_OR_UNKNOWN"]
    if p95 is None or _f(p95) > _f(cfg.get("max_forward_p95_abs_slippage_bps"), 50):
        return "HISTORICAL_SHORTLIST_FORWARD_VALIDATION", ["FORWARD_P95_SLIPPAGE_TOO_HIGH_OR_UNKNOWN"]
    return "COPYABLE_CANDIDATE", []


def _observe_new_fills(
    address: str,
    fills: list[dict[str, Any]],
    mids: dict[str, Any],
    ledger: dict[str, Any],
    now_ms: int,
) -> list[dict[str, Any]]:
    accounts = ledger.setdefault("accounts", {})
    acc = accounts.setdefault(address.lower(), {"seen_fill_ids": [], "forward_observations": []})
    seen = set(acc.get("seen_fill_ids") or [])
    observations = list(acc.get("forward_observations") or [])
    activation_ms = int(ledger.get("activated_at_ms") or now_ms)

    for fill in sorted(fills, key=lambda x: int(x.get("time") or 0)):
        fid = _fill_id(fill)
        if fid in seen:
            continue
        seen.add(fid)
        fill_time = int(fill.get("time") or 0)
        if fill_time < activation_ms:
            continue
        coin = str(fill.get("coin") or "")
        source_px = _f(fill.get("px"), 0)
        mid = _f(mids.get(coin), 0) if isinstance(mids, dict) else 0
        slippage_bps = abs(mid - source_px) / source_px * 10_000 if source_px > 0 and mid > 0 else None
        observations.append(
            {
                "fill_id": fid,
                "source_fill_time": fill_time,
                "source_fill_time_iso": _iso(fill_time) if fill_time else None,
                "first_observed_at": now_ms,
                "first_observed_at_iso": _iso(now_ms),
                "observation_latency_ms": max(0, now_ms - fill_time) if fill_time else None,
                "coin": coin,
                "dir": fill.get("dir"),
                "side": fill.get("side"),
                "source_px": source_px or None,
                "observed_mid": mid or None,
                "abs_slippage_bps_at_first_observation": slippage_bps,
                "size": _f(fill.get("sz")) or None,
                "closed_pnl": _f(fill.get("closedPnl")),
                "tx_hash": fill.get("hash"),
            }
        )

    acc["seen_fill_ids"] = list(seen)[-12_000:]
    acc["forward_observations"] = observations[-5_000:]
    return acc["forward_observations"]


def run_once() -> dict[str, Any]:
    config = _load(CONFIG, {})
    screening = config.get("screening") or {}
    now_ms = _now_ms()
    ledger = _load(
        LEDGER,
        {
            "version": "HYPERLIQUID_COPY_WATCH_LEDGER_V1",
            "activated_at_ms": now_ms,
            "activated_at": _iso(now_ms),
            "accounts": {},
        },
    )
    mids = _post({"type": "allMids"})
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for candidate in config.get("candidates") or []:
        address = str(candidate.get("address") or "").lower()
        if not (address.startswith("0x") and len(address) == 42):
            errors.append({"id": candidate.get("id"), "address": address, "error": "INVALID_ADDRESS"})
            continue
        try:
            fills = _post({"type": "userFills", "user": address, "aggregateByTime": True})
            portfolio = _portfolio_map(_post({"type": "portfolio", "user": address}))
            state = _post({"type": "clearinghouseState", "user": address})
            fills = fills if isinstance(fills, list) else []
            observations = _observe_new_fills(address, fills, mids if isinstance(mids, dict) else {}, ledger, now_ms)

            perp_month = portfolio.get("perpMonth") or portfolio.get("month") or {}
            perp_all = portfolio.get("perpAllTime") or portfolio.get("allTime") or {}
            all_hist = perp_all.get("accountValueHistory") or []
            stats = _close_fill_stats(fills, now_ms)
            slippages = [
                _f(o.get("abs_slippage_bps_at_first_observation"))
                for o in observations
                if o.get("abs_slippage_bps_at_first_observation") is not None
            ]
            latencies = [
                int(o.get("observation_latency_ms") or 0)
                for o in observations
                if o.get("observation_latency_ms") is not None
            ]
            margin = (state or {}).get("marginSummary") or {}
            row: dict[str, Any] = {
                "id": candidate.get("id"),
                "address": address,
                "source": candidate.get("source"),
                "account_value_usd": _f(margin.get("accountValue")) or None,
                "open_positions": len((state or {}).get("assetPositions") or []),
                "history_span_days": round(_history_span_days(all_hist), 2),
                "max_drawdown_pct": None if _max_drawdown_pct(all_hist) is None else round(_max_drawdown_pct(all_hist) or 0, 2),
                "month_pnl": _history_delta(perp_month.get("pnlHistory") or []),
                "all_time_pnl": _history_delta(perp_all.get("pnlHistory") or []),
                **stats,
                "forward_copy_observations": len(observations),
                "forward_median_abs_slippage_bps": round(statistics.median(slippages), 2) if slippages else None,
                "forward_p95_abs_slippage_bps": round(_percentile(slippages, 0.95) or 0, 2) if slippages else None,
                "forward_median_observation_latency_ms": int(statistics.median(latencies)) if latencies else None,
                "latest_forward_observation": observations[-1] if observations else None,
            }
            decision, blockers = _decision(row, screening)
            row["decision"] = decision
            row["blockers"] = blockers
            row["score"] = _score(row, screening)
            rows.append(row)
        except Exception as exc:
            errors.append({"id": candidate.get("id"), "address": address, "error": f"{type(exc).__name__}: {exc}"})

    rows.sort(key=lambda x: (x.get("decision") == "COPYABLE_CANDIDATE", x.get("score") or 0), reverse=True)
    _write(LEDGER, ledger)
    summary = {
        "version": "HYPERLIQUID_COPY_WATCH_V1",
        "mode": "FORWARD_ONLY_TRACK_AND_SCREEN",
        "updated_at": _iso(now_ms),
        "candidates_configured": len(config.get("candidates") or []),
        "candidates_scored": len(rows),
        "copyable_candidates": sum(1 for r in rows if r.get("decision") == "COPYABLE_CANDIDATE"),
        "historical_shortlist": sum(1 for r in rows if r.get("decision") == "HISTORICAL_SHORTLIST_FORWARD_VALIDATION"),
        "watch_only": sum(1 for r in rows if r.get("decision") == "WATCH"),
        "ranking": rows,
        "screening": screening,
        "truth_contract": config.get("truth_contract") or {},
        "recommend_real_money_now": False,
        "real_money_reason": "TRACK_AND_SCREEN_ONLY_UNTIL_FORWARD_COPYABILITY_IS_MEASURED",
        "errors": errors,
    }
    _write(SUMMARY, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run_once(), ensure_ascii=False, indent=2))
