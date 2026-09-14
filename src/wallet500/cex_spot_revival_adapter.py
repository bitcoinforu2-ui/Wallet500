from __future__ import annotations

from pathlib import Path

from . import cex_spot_revival as base


def _f(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _mexc_change_pct(row: dict) -> float:
    """Normalize MEXC 24h change into percentage points.

    MEXC's priceChangePercent feed has behaved as a fractional ratio for the
    markets we consume (for example 0.6581 == 65.81%). Prefer the explicit
    24h open/last calculation when available so the unit cannot drift.
    """
    last = _f(row.get("lastPrice"))
    open24h = _f(row.get("openPrice"))
    if last > 0 and open24h > 0:
        return (last / open24h - 1.0) * 100.0
    return _f(row.get("priceChangePercent")) * 100.0


def mexc_spot_fixed() -> list[dict]:
    rows = base._get("https://api.mexc.com/api/v3/ticker/24hr")
    if isinstance(rows, dict):
        rows = [rows]
    return [
        base._row(
            "mexc",
            x.get("symbol", ""),
            x.get("lastPrice"),
            _mexc_change_pct(x),
            x.get("quoteVolume"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("USDT")
    ]


def run_cex_spot_revival(out: Path, now: str) -> dict:
    """Run the canonical scanner with a forward-only MEXC unit correction."""
    original_sources = base.SPOT_SOURCES
    base.SPOT_SOURCES = [
        (name, mexc_spot_fixed if name == "mexc" else fn)
        for name, fn in original_sources
    ]
    try:
        payload = base.run_cex_spot_revival(out, now)
        payload.setdefault("source_normalization", {})["mexc_24h_change_pct"] = (
            "OPEN_TO_LAST_PERCENT; FALLBACK_PRICE_CHANGE_RATIO_X100"
        )
        # run_cex_spot_revival already wrote the canonical payload before this
        # annotation. The normalization itself is what matters to scoring; do
        # not rewrite output here and race the canonical state publisher.
        return payload
    finally:
        base.SPOT_SOURCES = original_sources
