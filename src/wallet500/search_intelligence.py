from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
CMC_TRENDING_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/trending/latest"
USER_AGENT = "Wallet500-search-intel/1.0 (+https://github.com/bitcoinforu2-ui/Wallet500)"
MAX_SNAPSHOTS = 144


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    status: str
    assets: list[dict[str, Any]]
    error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "")
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _http_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    timeout: int = 20,
    attempts: int = 4,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    merged = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers=merged)
            with opener(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("provider response is not a JSON object")
            return payload
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            retry_after = 0.0
            if isinstance(exc, HTTPError) and exc.headers:
                retry_after = _number(exc.headers.get("Retry-After")) or 0.0
            time.sleep(max(retry_after, min(2 ** attempt, 6)))
    raise RuntimeError(f"live request failed after {attempts} attempts: {last_error}")


def _normalize_coingecko(payload: dict[str, Any], observed_at: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, wrapper in enumerate(payload.get("coins") or []):
        if not isinstance(wrapper, dict):
            continue
        item = wrapper.get("item") or {}
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        token_id = str(item.get("id") or "").strip()
        if not symbol or not token_id:
            continue
        data = item.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        change24 = data.get("price_change_percentage_24h")
        if isinstance(change24, dict):
            change24 = change24.get("usd")
        output.append(
            {
                "provider": "coingecko",
                "token_id": token_id,
                "symbol": symbol,
                "name": str(item.get("name") or symbol),
                "search_rank": index + 1,
                "market_cap_rank": item.get("market_cap_rank"),
                "price_usd": _number(data.get("price")),
                "price_change_24h_pct": _number(change24),
                "observed_at": observed_at,
            }
        )
    return output


def fetch_coingecko(*, opener: Callable[..., Any] = urlopen, observed_at: str | None = None) -> ProviderResult:
    observed_at = observed_at or _utc_now()
    try:
        payload = _http_json(COINGECKO_TRENDING_URL, opener=opener)
        assets = _normalize_coingecko(payload, observed_at)
        if not assets:
            raise RuntimeError("CoinGecko returned zero trending coins")
        return ProviderResult("coingecko", "ok", assets)
    except Exception as exc:  # provider isolation is intentional
        return ProviderResult("coingecko", "error", [], str(exc))


def _normalize_cmc(payload: dict[str, Any], observed_at: str) -> list[dict[str, Any]]:
    rows = payload.get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("cryptoCurrencyList") or rows.get("data") or []
    output: list[dict[str, Any]] = []
    for index, item in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        token_id = str(item.get("id") or item.get("slug") or "").strip()
        if not symbol or not token_id:
            continue
        quote = item.get("quote") or {}
        usd = quote.get("USD") if isinstance(quote, dict) else {}
        if not isinstance(usd, dict):
            usd = {}
        output.append(
            {
                "provider": "coinmarketcap",
                "token_id": token_id,
                "symbol": symbol,
                "name": str(item.get("name") or symbol),
                "search_rank": index + 1,
                "market_cap_rank": item.get("cmc_rank"),
                "price_usd": _number(usd.get("price")),
                "price_change_24h_pct": _number(usd.get("percent_change_24h")),
                "observed_at": observed_at,
            }
        )
    return output


def fetch_coinmarketcap(
    api_key: str | None = None,
    *,
    opener: Callable[..., Any] = urlopen,
    observed_at: str | None = None,
) -> ProviderResult:
    api_key = api_key or os.getenv("CMC_API_KEY")
    if not api_key:
        return ProviderResult("coinmarketcap", "skipped_no_key", [])
    observed_at = observed_at or _utc_now()
    try:
        payload = _http_json(
            CMC_TRENDING_URL,
            headers={"X-CMC_PRO_API_KEY": api_key},
            opener=opener,
        )
        assets = _normalize_cmc(payload, observed_at)
        if not assets:
            raise RuntimeError("CoinMarketCap returned zero trending coins")
        return ProviderResult("coinmarketcap", "ok", assets)
    except Exception as exc:  # provider isolation is intentional
        return ProviderResult("coinmarketcap", "error", [], str(exc))


def _asset_key(asset: dict[str, Any]) -> tuple[str, str]:
    return str(asset.get("provider") or ""), str(asset.get("token_id") or "")


def _snapshot_index(snapshot: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not snapshot:
        return {}
    return {_asset_key(a): a for a in snapshot.get("assets") or [] if isinstance(a, dict)}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _price_change(current: dict[str, Any], previous: dict[str, Any] | None) -> float | None:
    if not previous:
        return None
    now_price = _number(current.get("price_usd"))
    old_price = _number(previous.get("price_usd"))
    if now_price is None or old_price is None or old_price <= 0:
        return None
    return (now_price / old_price - 1.0) * 100.0


def _component(value_pct: float | None, weight: float) -> dict[str, Any]:
    if value_pct is None:
        return {"available": False, "pct": None, "weight": weight, "points": 0.0}
    pct = _clamp(value_pct)
    return {"available": True, "pct": round(pct, 2), "weight": weight, "points": round(pct * weight / 100.0, 2)}


def score_snapshot(
    current_assets: list[dict[str, Any]],
    previous_snapshot: dict[str, Any] | None,
    older_snapshot: dict[str, Any] | None = None,
    *,
    revival_context: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    previous = _snapshot_index(previous_snapshot)
    older = _snapshot_index(older_snapshot)
    symbols_by_provider: dict[str, set[str]] = {}
    for asset in current_assets:
        symbol = str(asset.get("symbol") or "").upper()
        provider = str(asset.get("provider") or "")
        if symbol and provider:
            symbols_by_provider.setdefault(symbol, set()).add(provider)

    scored: list[dict[str, Any]] = []
    for asset in current_assets:
        row = dict(asset)
        key = _asset_key(row)
        prev = previous.get(key)
        old = older.get(key)
        current_rank = _number(row.get("search_rank"))
        prev_rank = _number(prev.get("search_rank")) if prev else None
        old_rank = _number(old.get("search_rank")) if old else None

        improvement = 0.0
        velocity_pct: float | None = None
        if current_rank and prev_rank:
            improvement = max(0.0, prev_rank - current_rank)
            velocity_pct = _clamp((improvement / max(prev_rank, 1.0)) * 220.0)

        acceleration_pct: float | None = None
        prior_improvement = None
        if current_rank and prev_rank and old_rank:
            prior_improvement = max(0.0, old_rank - prev_rank)
            accel = max(0.0, improvement - prior_improvement)
            acceleration_pct = _clamp((accel / max(prev_rank, 1.0)) * 350.0)

        symbol = str(row.get("symbol") or "").upper()
        providers = symbols_by_provider.get(symbol, set())
        cross_pct: float | None = 100.0 if len(providers) >= 2 else None

        interval_change = _price_change(row, prev)
        change24 = _number(row.get("price_change_24h_pct"))
        divergence_pct: float | None = None
        if improvement > 0 and (interval_change is None or abs(interval_change) <= 15):
            if interval_change is None or abs(interval_change) <= 5:
                divergence_pct = 100.0
            else:
                divergence_pct = max(0.0, 100.0 - (abs(interval_change) - 5.0) * 10.0)
            if change24 is not None and change24 > 30:
                divergence_pct *= max(0.0, 1.0 - (change24 - 30.0) / 50.0)

        revival_pct: float | None = None
        if revival_context and symbol in revival_context:
            revival_pct = _clamp(float(revival_context[symbol]))

        components = {
            "search_velocity": _component(velocity_pct, 35.0),
            "cross_source_confirmation": _component(cross_pct, 25.0),
            "search_acceleration": _component(acceleration_pct, 15.0),
            "price_search_divergence": _component(divergence_pct, 15.0),
            "revival_context": _component(revival_pct, 10.0),
        }
        raw_score = sum(c["points"] for c in components.values())
        available_weight = sum(c["weight"] for c in components.values() if c["available"])
        normalized = raw_score / available_weight * 100.0 if available_weight else 0.0
        evidence_weight = available_weight

        saturated = (
            ((current_rank is not None and current_rank <= 3) and (change24 is not None and change24 >= 40))
            or (interval_change is not None and interval_change >= 15)
        )
        enough_history = prev is not None
        if not enough_history:
            signal = "WARMING_UP"
        elif saturated:
            signal = "SEARCH_SATURATION"
        elif improvement > 0 and normalized >= 70.0 and evidence_weight >= 35.0:
            signal = "SEARCH_PRE_WAVE"
        else:
            signal = "WATCH"

        row.update(
            {
                "signal": signal,
                "search_momentum_score": round(normalized, 2),
                "raw_score": round(raw_score, 2),
                "evidence_weight": round(evidence_weight, 2),
                "rank_improvement": round(improvement, 2),
                "previous_search_rank": int(prev_rank) if prev_rank is not None else None,
                "interval_price_change_pct": round(interval_change, 4) if interval_change is not None else None,
                "components": components,
                "cross_source_providers": sorted(providers),
            }
        )
        scored.append(row)
    return sorted(scored, key=lambda x: (-float(x.get("search_momentum_score") or 0), int(x.get("search_rank") or 999999)))


def load_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"version": 1, "snapshots": []}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "snapshots": []}
    if not isinstance(data, dict) or not isinstance(data.get("snapshots"), list):
        return {"version": 1, "snapshots": []}
    return data


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)


def collect_search_intelligence(
    *,
    state_path: str | Path,
    latest_path: str | Path,
    api_key: str | None = None,
    fetchers: Iterable[Callable[[], ProviderResult]] | None = None,
    observed_at: str | None = None,
    revival_context: dict[str, float] | None = None,
    require_live: bool = False,
) -> dict[str, Any]:
    observed_at = observed_at or _utc_now()
    if fetchers is None:
        fetchers = (
            lambda: fetch_coingecko(observed_at=observed_at),
            lambda: fetch_coinmarketcap(api_key=api_key, observed_at=observed_at),
        )
    results = [fetcher() for fetcher in fetchers]
    assets = [asset for result in results if result.status == "ok" for asset in result.assets]
    live_provider_count = sum(1 for result in results if result.status == "ok")
    if require_live and live_provider_count == 0:
        errors = "; ".join(f"{r.provider}: {r.error or r.status}" for r in results)
        raise RuntimeError(f"no live search-intelligence provider succeeded: {errors}")
    if not assets:
        raise RuntimeError("search-intelligence collection produced zero assets")

    state = load_state(state_path)
    history = state.get("snapshots") or []
    previous_snapshot = history[-1] if history else None
    older_snapshot = history[-2] if len(history) >= 2 else None
    scored = score_snapshot(assets, previous_snapshot, older_snapshot, revival_context=revival_context)

    provider_status = {
        result.provider: {
            "status": result.status,
            "asset_count": len(result.assets),
            "error": result.error,
        }
        for result in results
    }
    snapshot = {
        "observed_at": observed_at,
        "assets": assets,
        "providers": provider_status,
    }
    history = (history + [snapshot])[-MAX_SNAPSHOTS:]
    state = {"version": 1, "updated_at": observed_at, "snapshots": history}
    latest = {
        "schema_version": 1,
        "updated_at": observed_at,
        "decision_mode": "shadow",
        "changes_real_alert_gate": False,
        "collection": {
            "live_provider_count": live_provider_count,
            "providers": provider_status,
            "history_depth": len(history),
        },
        "summary": {
            "asset_count": len(scored),
            "search_pre_wave_count": sum(1 for a in scored if a["signal"] == "SEARCH_PRE_WAVE"),
            "search_saturation_count": sum(1 for a in scored if a["signal"] == "SEARCH_SATURATION"),
            "warming_up_count": sum(1 for a in scored if a["signal"] == "WARMING_UP"),
        },
        "assets": scored,
    }
    _write_json(state_path, state)
    _write_json(latest_path, latest)
    return latest


def load_search_signal(symbol: str, latest_path: str | Path = "data/search-intelligence-latest.json") -> dict[str, Any] | None:
    path = Path(latest_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    wanted = symbol.strip().upper()
    matches = [a for a in payload.get("assets") or [] if str(a.get("symbol") or "").upper() == wanted]
    if not matches:
        return None
    return max(matches, key=lambda a: float(a.get("search_momentum_score") or 0))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wallet500 Search Momentum Intelligence")
    parser.add_argument("--state", default="data/search-intelligence-state.json")
    parser.add_argument("--latest", default="data/search-intelligence-latest.json")
    parser.add_argument("--require-live", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    latest = collect_search_intelligence(
        state_path=args.state,
        latest_path=args.latest,
        require_live=args.require_live,
    )
    providers = latest["collection"]["providers"]
    ok = [name for name, meta in providers.items() if meta["status"] == "ok"]
    print(
        f"SEARCH_INTEL_OK providers={','.join(ok)} assets={latest['summary']['asset_count']} "
        f"pre_wave={latest['summary']['search_pre_wave_count']} saturation={latest['summary']['search_saturation_count']} "
        f"mode={latest['decision_mode']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
