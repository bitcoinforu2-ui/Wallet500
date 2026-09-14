from __future__ import annotations

import json
from pathlib import Path

from . import cex_spot_leaderboard_bridge as base

LEVERAGED_SUFFIXES = (
    "2L", "2S", "3L", "3S", "4L", "4S", "5L", "5S",
    "BULL", "BEAR", "UP", "DOWN",
)


def _f(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _base_symbol(value) -> str:
    text = str(value or "").split(":", 1)[0].upper().strip()
    text = text.replace("-", "").replace("_", "").replace("/", "")
    return text[:-4] if text.endswith("USDT") else text


def _is_leveraged(value) -> bool:
    symbol = _base_symbol(value)
    return any(symbol.endswith(suffix) and len(symbol) > len(suffix) for suffix in LEVERAGED_SUFFIXES)


def _latest_market_rows_fixed(state: dict) -> list[dict]:
    """Parse state keys without leaking market_id into the canonical symbol."""
    markets = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    out = []
    for key, history in markets.items():
        if not isinstance(key, str) or not key.startswith("spot:") or not isinstance(history, list) or not history:
            continue
        parts = key.split(":", 3)
        if len(parts) < 3:
            continue
        exchange = parts[1]
        symbol = parts[2]
        market_id = parts[3] if len(parts) > 3 else symbol
        if not symbol.endswith("USDT") or _is_leveraged(symbol):
            continue
        latest = history[-1] if isinstance(history[-1], dict) else {}
        out.append({
            "exchange": exchange,
            "market_type": "spot",
            "symbol": symbol,
            "market_id": market_id,
            "price": _f(latest.get("price")),
            "change_24h_pct": _f(latest.get("change_24h_pct")),
            "volume_24h": _f(latest.get("volume_24h")),
            "observed_at": latest.get("observed_at"),
            "price_delta_pct": 0.0,
            "volume24_delta_pct": 0.0,
            "history_points": max(0, len(history) - 1),
        })
    return out


def run(data_dir: Path = base.DATA, now: str | None = None) -> dict:
    original = base._latest_market_rows
    base._latest_market_rows = _latest_market_rows_fixed
    try:
        report = base.run(data_dir, now)
    finally:
        base._latest_market_rows = original

    # Defense-in-depth: a leaderboard discovery row is never an automatic trade.
    radar_path = data_dir / "cex-spot-revival-radar.json"
    try:
        radar = json.loads(radar_path.read_text(encoding="utf-8"))
        for lane in ("watchlist", "alerts"):
            cleaned = []
            for row in radar.get(lane) or []:
                if not isinstance(row, dict) or _is_leveraged(row.get("symbol")):
                    continue
                row["automatic_buy"] = False
                cleaned.append(row)
            radar[lane] = cleaned[:100]
        radar["watch_count"] = len(radar.get("watchlist") or [])
        radar["alerts_count"] = len(radar.get("alerts") or [])
        meta = radar.get("leaderboard_bridge") if isinstance(radar.get("leaderboard_bridge"), dict) else {}
        meta["canonical_state_key_parser"] = True
        meta["leveraged_products_excluded"] = True
        radar["leaderboard_bridge"] = meta
        radar_path.write_text(json.dumps(radar, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Base run already produced fail-closed research output; never turn a
        # cosmetic hardening failure into production action.
        pass

    report["canonical_state_key_parser"] = True
    report["leveraged_products_excluded"] = True
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
