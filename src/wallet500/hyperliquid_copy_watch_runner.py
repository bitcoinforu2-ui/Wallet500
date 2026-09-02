from __future__ import annotations

import json
from typing import Any

from . import hyperliquid_copy_watch as engine


def _series(history: Any) -> dict[int, float]:
    out: dict[int, float] = {}
    for x in history or []:
        if isinstance(x, list) and len(x) >= 2:
            try:
                out[int(x[0])] = float(x[1])
            except Exception:
                pass
    return out


def trading_drawdown_proxy_pct(account_history: Any, pnl_history: Any) -> float | None:
    """Trading drawdown proxy that is less distorted by deposits/withdrawals.

    Hyperliquid accountValueHistory can jump because of cash flows. We therefore measure the
    peak-to-trough decline in cumulative trading PnL and normalize that decline by the largest
    positive account value observed up to the PnL peak. This is deliberately labelled a proxy,
    not a broker-reported max drawdown.
    """
    av = _series(account_history)
    pnl = _series(pnl_history)
    common = sorted(set(av) & set(pnl))
    if len(common) < 2:
        return None

    max_capital_so_far = 0.0
    peak_pnl: float | None = None
    peak_capital = 0.0
    worst = 0.0
    for ts in common:
        capital = av[ts]
        p = pnl[ts]
        if capital > 0:
            max_capital_so_far = max(max_capital_so_far, capital)
        if peak_pnl is None or p > peak_pnl:
            peak_pnl = p
            peak_capital = max(max_capital_so_far, capital, 1.0)
        if peak_pnl is not None and peak_capital > 0:
            worst = max(worst, max(0.0, peak_pnl - p) / peak_capital * 100.0)
    return worst


def run() -> dict[str, Any]:
    summary = engine.run_once()
    cfg = summary.get("screening") or {}
    ranking = summary.get("ranking") or []

    for row in ranking:
        address = str(row.get("address") or "")
        try:
            portfolio = engine._portfolio_map(engine._post({"type": "portfolio", "user": address}))
            perp_all = portfolio.get("perpAllTime") or portfolio.get("allTime") or {}
            dd = trading_drawdown_proxy_pct(
                perp_all.get("accountValueHistory") or [],
                perp_all.get("pnlHistory") or [],
            )
            row["raw_account_value_drawdown_pct"] = row.get("max_drawdown_pct")
            row["max_drawdown_pct"] = None if dd is None else round(dd, 2)
            row["drawdown_method"] = "PNL_PEAK_TO_TROUGH_NORMALIZED_BY_PEAK_CAPITAL_PROXY"
            decision, blockers = engine._decision(row, cfg)
            row["decision"] = decision
            row["blockers"] = blockers
            row["score"] = engine._score(row, cfg)
        except Exception as exc:
            row["drawdown_method"] = "UNAVAILABLE"
            row.setdefault("blockers", []).append("DRAWDOWN_PROXY_FETCH_FAILED")
            summary.setdefault("errors", []).append(
                {"id": row.get("id"), "address": address, "stage": "DRAWDOWN_PROXY", "error": f"{type(exc).__name__}: {exc}"}
            )

    ranking.sort(
        key=lambda x: (x.get("decision") == "COPYABLE_CANDIDATE", x.get("decision") == "HISTORICAL_SHORTLIST_FORWARD_VALIDATION", x.get("score") or 0),
        reverse=True,
    )
    summary["copyable_candidates"] = sum(1 for r in ranking if r.get("decision") == "COPYABLE_CANDIDATE")
    summary["historical_shortlist"] = sum(1 for r in ranking if r.get("decision") == "HISTORICAL_SHORTLIST_FORWARD_VALIDATION")
    summary["watch_only"] = sum(1 for r in ranking if r.get("decision") == "WATCH")
    summary["drawdown_policy"] = {
        "method": "PNL_PEAK_TO_TROUGH_NORMALIZED_BY_PEAK_CAPITAL_PROXY",
        "reason": "Account value alone is distorted by deposits and withdrawals; Wallet500 uses cumulative trading PnL for the drawdown numerator.",
        "broker_reported_mdd_claimed": False,
    }
    engine._write(engine.SUMMARY, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
