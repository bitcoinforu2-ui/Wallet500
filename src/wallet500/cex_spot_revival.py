from __future__ import annotations

import gzip
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = {"User-Agent": "Wallet500/1.8", "Accept": "application/json"}
WATCH_SCORE = 25
ALERT_SCORE = 35
LEVERAGED_SUFFIXES = ("2L", "2S", "3L", "3S", "4L", "4S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN")
REGIONAL_EXCHANGES = {"upbit"}
PRESSURE_HORIZONS = ((6, 1.20), (12, 1.35), (24, 1.50))
STATE_HISTORY_LIMIT = 192
CROSS_LANE_MIN_DERIVATIVES_SCORE = 50
CROSS_LANE_MIN_DERIVATIVES_COHERENT_CONFIRMATIONS = 2
CROSS_LANE_MAX_SIGNAL_MOVE_PCT = 35.0
CROSS_LANE_MAX_PRICE_ERROR_PCT = 12.0
CROSS_LANE_MAX_SPOT_BEFORE_DERIVATIVES_MINUTES = 90.0
CROSS_LANE_MAX_SPOT_AFTER_DERIVATIVES_MINUTES = 30.0


def _get(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _f(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _pct(cur, prev):
    try:
        cur = float(cur)
        prev = float(prev)
        if prev == 0:
            return 0.0
        return (cur / prev - 1.0) * 100.0
    except Exception:
        return 0.0


def _multiple(cur, prev):
    try:
        cur = float(cur)
        prev = float(prev)
        if prev <= 0:
            return 0.0
        return cur / prev
    except Exception:
        return 0.0


def _parse_ts(value):
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _asof_value(hist: list[dict], now_dt: datetime | None, hours: int, key: str):
    if not now_dt:
        return 0.0
    target = now_dt - timedelta(hours=hours)
    best_ts = None
    best_value = 0.0
    for item in hist:
        ts = _parse_ts(item.get("observed_at"))
        value = _f(item.get(key))
        if ts is None or ts > target or value <= 0:
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_value = value
    return best_value


def _norm_symbol(symbol: str) -> str:
    return (symbol or "").upper().strip().replace("-", "").replace("_", "").replace("/", "")


def _base_symbol(symbol: str) -> str:
    s = _norm_symbol(symbol)
    return s[:-4] if s.endswith("USDT") else s


def _is_leveraged_product(symbol: str) -> bool:
    base = _base_symbol(symbol)
    return any(base.endswith(suffix) and len(base) > len(suffix) for suffix in LEVERAGED_SUFFIXES)


def _leveraged_underlying_symbol(symbol: str) -> str | None:
    base = _base_symbol(symbol)
    for suffix in sorted(LEVERAGED_SUFFIXES, key=len, reverse=True):
        if base.endswith(suffix) and len(base) > len(suffix):
            return base[:-len(suffix)] + "USDT"
    return None


def _price_coherent_partition(markets: list[dict], max_ratio: float = 1.35) -> tuple[list[dict], list[dict], list[dict], float]:
    """Split same-ticker markets into a USD-like price-coherent cohort plus outliers.

    Same ticker text is not identity. If exchanges use the same ticker for different
    assets, cross-exchange confirmation must not be manufactured by symbol alone.
    Native-quote regional markets stay research-only and never choose the USD cohort.
    """
    usd = [
        x for x in markets
        if x.get("volume_comparable_usd_like", True) and _f(x.get("price")) > 0
    ]
    regional = [x for x in markets if not x.get("volume_comparable_usd_like", True)]
    if len(usd) <= 1:
        return usd, [], regional, 1.0

    ordered = sorted(usd, key=lambda x: _f(x.get("price")))
    best: list[dict] = []
    best_volume = -1.0
    for i in range(len(ordered)):
        cohort = []
        low = _f(ordered[i].get("price"))
        if low <= 0:
            continue
        for j in range(i, len(ordered)):
            high = _f(ordered[j].get("price"))
            if high / low > max_ratio:
                break
            cohort.append(ordered[j])
        volume = sum(_f(x.get("volume_24h")) for x in cohort)
        if len(cohort) > len(best) or (len(cohort) == len(best) and volume > best_volume):
            best = cohort
            best_volume = volume

    best_ids = {(str(x.get("exchange")), str(x.get("market_id"))) for x in best}
    outliers = [
        x for x in usd
        if (str(x.get("exchange")), str(x.get("market_id"))) not in best_ids
    ]
    prices = [_f(x.get("price")) for x in usd if _f(x.get("price")) > 0]
    observed_ratio = max(prices) / min(prices) if prices else 1.0
    return best or usd[:1], outliers, regional, observed_ratio


def _load_derivatives_first_alerts(out: Path) -> dict[str, dict]:
    """Load immutable derivatives FIRST_ALERT milestones for cross-lane early-warning fusion.

    cex-state.json.gz is the persistent source of truth. cex-learning.json is only
    a fallback for repositories/tests where the rolling state is unavailable.
    """
    state = _load_state(out / "cex-state.json", {})
    index: dict[str, dict] = {}
    milestones = state.get("signal_milestones") if isinstance(state, dict) else {}
    if isinstance(milestones, dict):
        for symbol, bundle in milestones.items():
            if not isinstance(bundle, dict):
                continue
            alert = bundle.get("first_alert")
            if isinstance(alert, dict) and alert.get("observed_at"):
                index[_norm_symbol(str(symbol))] = dict(alert)

    try:
        learning = json.loads((out / "cex-learning.json").read_text(encoding="utf-8"))
    except Exception:
        learning = {}
    for row in learning.get("top_candidates") or []:
        if not isinstance(row, dict):
            continue
        alert = ((row.get("milestones") or {}).get("first_alert"))
        symbol = _norm_symbol(str(row.get("symbol") or ""))
        if symbol and symbol not in index and isinstance(alert, dict) and alert.get("observed_at"):
            index[symbol] = dict(alert)

    # Current RAW derivatives evidence is attached separately and never overwrites
    # the immutable FIRST_ALERT. It can only create an identity-priority shadow for
    # extended/dislocated moves; it is never backdated into an earlier signal.
    try:
        raw = json.loads((out / "cex-revival-raw.json").read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    raw_at = raw.get("generated_at")
    current_rows = []
    seen_current = set()
    for collection in ("alerts", "watchlist"):
        for row in raw.get(collection) or []:
            if not isinstance(row, dict):
                continue
            symbol = _norm_symbol(str(row.get("symbol") or ""))
            if not symbol or symbol in seen_current:
                continue
            seen_current.add(symbol)
            current_rows.append(row)
    for row in current_rows:
        symbol = _norm_symbol(str(row.get("symbol") or ""))
        markets = [x for x in (row.get("markets") or []) if isinstance(x, dict) and _f(x.get("price")) > 0]
        ref = max(markets, key=lambda x: (_f(x.get("volume_24h")), _f(x.get("open_interest"))), default={})
        if not symbol or not raw_at or _f(ref.get("price")) <= 0:
            continue
        current = {
            "kind": "CURRENT_DERIVATIVES_ALERT",
            "observed_at": raw_at,
            "reference_exchange": ref.get("exchange"),
            "reference_price": _f(ref.get("price")),
            "reference_change_24h_pct": _f(ref.get("change_24h_pct")),
            "score": int(_f(row.get("cex_revival_score"))),
            "confirmations": int(_f(row.get("confirmations"))),
            "coherent_confirmations": int(_f(row.get("coherent_confirmations"))),
            "dispersion_status": row.get("dispersion_status"),
            "change_24h_max_pct": _f(row.get("change_24h_max_pct")),
            "watch_reason": row.get("watch_reason"),
            "mover_watch": row.get("mover_watch") is True,
            "max_derivatives_turnover_usd": _f(row.get("max_derivatives_turnover_usd")),
        }
        bundle = index.setdefault(symbol, {})
        if isinstance(bundle, dict):
            bundle["_current_alert"] = current
    return index


def _cross_lane_derivatives_precursor(
    symbol: str,
    spot_milestones: dict,
    derivatives_first_alerts: dict[str, dict],
) -> dict | None:
    """Fuse derivatives evidence into an identity-priority spot shadow.

    Coherent, early immutable FIRST_ALERT evidence may remain eligible for downstream
    action-score fusion after exact identity. Extended or cross-exchange-dislocated
    evidence is retained only for identity/re-entry monitoring and can never raise the
    spot score or become actionable by itself.
    """
    bundle = derivatives_first_alerts.get(_norm_symbol(symbol))
    if not isinstance(bundle, dict):
        return None

    candidates = []
    if bundle.get("observed_at"):
        candidates.append(("FIRST_ALERT", bundle))
    current = bundle.get("_current_alert")
    if isinstance(current, dict) and current.get("observed_at"):
        candidates.append(("CURRENT_ALERT", current))

    qualified = []
    for evidence_kind, alert in candidates:
        score = int(_f(alert.get("score")))
        coherent = int(_f(alert.get("coherent_confirmations")))
        dispersion = str(alert.get("dispersion_status") or "").upper()
        signal_move = _f(alert.get("reference_change_24h_pct"))
        derivative_price = _f(alert.get("reference_price"))
        derivative_at = _parse_ts(alert.get("observed_at"))
        early_coherent = (
            score >= CROSS_LANE_MIN_DERIVATIVES_SCORE
            and coherent >= CROSS_LANE_MIN_DERIVATIVES_COHERENT_CONFIRMATIONS
            and dispersion == "COHERENT_RANGE"
            and signal_move <= CROSS_LANE_MAX_SIGNAL_MOVE_PCT
        )
        current_mover_watch = (
            evidence_kind == "CURRENT_ALERT"
            and alert.get("mover_watch") is True
            and _f(alert.get("change_24h_max_pct")) >= 30.0
            and _f(alert.get("max_derivatives_turnover_usd")) >= 50_000.0
        )
        identity_only = (
            (
                score >= ALERT_SCORE
                and coherent >= 2
                and (
                    (dispersion == "EXTREME_DISLOCATION_VERIFY" and coherent >= 3)
                    or evidence_kind == "CURRENT_ALERT"
                    and (signal_move > CROSS_LANE_MAX_SIGNAL_MOVE_PCT or dispersion != "COHERENT_RANGE")
                )
            )
            or current_mover_watch
        )
        if not (early_coherent or identity_only) or derivative_price <= 0 or derivative_at is None:
            continue

        anchors = []
        for name in ("first_seen", "first_anomaly", "first_watch", "first_alert"):
            item = spot_milestones.get(name) if isinstance(spot_milestones, dict) else None
            if not isinstance(item, dict):
                continue
            spot_price = _f(item.get("reference_price"))
            spot_at = _parse_ts(item.get("observed_at"))
            if spot_price <= 0 or spot_at is None:
                continue
            delta_minutes = (spot_at - derivative_at).total_seconds() / 60.0
            if delta_minutes < -CROSS_LANE_MAX_SPOT_BEFORE_DERIVATIVES_MINUTES:
                continue
            if delta_minutes > CROSS_LANE_MAX_SPOT_AFTER_DERIVATIVES_MINUTES:
                continue
            price_error = abs(spot_price / derivative_price - 1.0) * 100.0
            if price_error > CROSS_LANE_MAX_PRICE_ERROR_PCT:
                continue
            anchors.append((abs(delta_minutes), price_error, name, item, spot_at, delta_minutes))
        if not anchors:
            continue

        _, price_error, anchor_name, anchor, spot_at, delta_minutes = min(anchors)
        fused_at = max(spot_at, derivative_at)
        fused_change = max(_f(anchor.get("reference_change_24h_pct")), signal_move)
        action_fusion_eligible = bool(early_coherent)
        qualified.append({
            "status": (
                "QUALIFIED_CEX_DERIVATIVES_SPOT_PRECURSOR"
                if action_fusion_eligible
                else "QUALIFIED_CEX_DERIVATIVES_IDENTITY_ONLY_PRECURSOR"
            ),
            "research_only": True,
            "actionable": False,
            "affects_spot_score": False,
            "identity_priority": True,
            "eligible_for_action_score_fusion_after_exact_identity": action_fusion_eligible,
            "no_hindsight": True,
            "evidence_kind": evidence_kind,
            "identity_only_reason": None if action_fusion_eligible else (
                "CURRENT_MOVER_WATCH"
                if current_mover_watch
                else "EXTREME_DISLOCATION_VERIFY"
                if dispersion == "EXTREME_DISLOCATION_VERIFY"
                else "CURRENT_MOVE_EXTENDED_OR_NONCOHERENT"
            ),
            "action_signal_score": score,
            "action_signal_at": fused_at.isoformat(),
            "action_signal_price": _f(anchor.get("reference_price")),
            "action_signal_change_24h_pct": round(fused_change, 4),
            "derivatives_first_alert_at": derivative_at.isoformat(),
            "derivatives_score": score,
            "derivatives_coherent_confirmations": coherent,
            "derivatives_dispersion_status": dispersion,
            "derivatives_reference_price": derivative_price,
            "spot_anchor_kind": anchor_name,
            "spot_anchor_at": spot_at.isoformat(),
            "spot_anchor_price": _f(anchor.get("reference_price")),
            "spot_derivatives_time_delta_minutes": round(delta_minutes, 3),
            "spot_derivatives_price_error_pct": round(price_error, 4),
            "fusion_rule": (
                "IMMUTABLE_DERIVATIVES_FIRST_ALERT_PLUS_CONTEMPORANEOUS_SPOT_PRICE_ANCHOR"
                if evidence_kind == "FIRST_ALERT"
                else "CURRENT_DERIVATIVES_ALERT_PLUS_CONTEMPORANEOUS_SPOT_PRICE_ANCHOR_IDENTITY_ONLY"
            ),
        })

    if not qualified:
        return None
    qualified.sort(
        key=lambda x: (
            x.get("eligible_for_action_score_fusion_after_exact_identity") is True,
            x.get("evidence_kind") == "FIRST_ALERT",
            int(x.get("derivatives_score") or 0),
        ),
        reverse=True,
    )
    return qualified[0]


def _row(
    exchange: str,
    symbol: str,
    price=0,
    change=0,
    volume=0,
    market_id=None,
    *,
    quote_symbol: str = "USDT",
    volume_comparable: bool = True,
    regional_market: bool = False,
):
    return {
        "exchange": exchange,
        "market_type": "spot",
        "symbol": _norm_symbol(symbol),
        "market_id": market_id or symbol,
        "price": _f(price),
        "change_24h_pct": _f(change),
        "volume_24h": _f(volume),
        "quote_symbol": quote_symbol,
        "volume_comparable_usd_like": bool(volume_comparable),
        "regional_market": bool(regional_market),
    }


def gate_spot():
    rows = _get("https://api.gateio.ws/api/v4/spot/tickers")
    return [
        _row(
            "gate",
            x.get("currency_pair", ""),
            x.get("last"),
            x.get("change_percentage"),
            x.get("quote_volume"),
            x.get("currency_pair"),
        )
        for x in rows
        if str(x.get("currency_pair", "")).endswith("_USDT")
    ]


def bybit_spot():
    rows = ((_get("https://api.bybit.com/v5/market/tickers?category=spot").get("result") or {}).get("list") or [])
    return [
        _row(
            "bybit",
            x.get("symbol", ""),
            x.get("lastPrice"),
            _f(x.get("price24hPcnt")) * 100.0,
            x.get("turnover24h"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("USDT")
    ]


def okx_spot():
    rows = _get("https://www.okx.com/api/v5/market/tickers?instType=SPOT").get("data", []) or []
    out = []
    for x in rows:
        market = str(x.get("instId", ""))
        if not market.endswith("-USDT"):
            continue
        last = _f(x.get("last"))
        open24h = _f(x.get("open24h"))
        change = (last / open24h - 1.0) * 100.0 if last and open24h else 0.0
        out.append(_row("okx", market, last, change, x.get("volCcy24h"), market))
    return out


def mexc_spot():
    rows = _get("https://api.mexc.com/api/v3/ticker/24hr")
    if isinstance(rows, dict):
        rows = [rows]
    return [
        _row(
            "mexc",
            x.get("symbol", ""),
            x.get("lastPrice"),
            x.get("priceChangePercent"),
            x.get("quoteVolume"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("USDT")
    ]


def kucoin_spot():
    rows = ((_get("https://api.kucoin.com/api/v1/market/allTickers").get("data") or {}).get("ticker") or [])
    return [
        _row(
            "kucoin",
            x.get("symbol", ""),
            x.get("last"),
            _f(x.get("changeRate")) * 100.0,
            x.get("volValue"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("-USDT")
    ]


def binance_spot():
    rows = _get("https://api.binance.com/api/v3/ticker/24hr")
    if isinstance(rows, dict):
        rows = [rows]
    return [
        _row(
            "binance",
            x.get("symbol", ""),
            x.get("lastPrice"),
            x.get("priceChangePercent"),
            x.get("quoteVolume"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("USDT")
    ]


def bitget_spot():
    payload = _get("https://api.bitget.com/api/v2/spot/market/tickers")
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    return [
        _row(
            "bitget",
            x.get("symbol", ""),
            x.get("lastPr"),
            _f(x.get("change24h")) * 100.0,
            x.get("quoteVolume"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("USDT")
    ]


def coinex_spot():
    payload = _get("https://api.coinex.com/v2/spot/ticker")
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    out = []
    for x in rows:
        market = str(x.get("market", ""))
        if not market.endswith("USDT"):
            continue
        last = _f(x.get("last") if x.get("last") is not None else x.get("close"))
        open24h = _f(x.get("open"))
        change = (last / open24h - 1.0) * 100.0 if last and open24h else 0.0
        out.append(_row("coinex", market, last, change, x.get("value"), market))
    return out


def upbit_spot():
    markets = _get("https://api.upbit.com/v1/market/all?is_details=false")
    krw_markets = [str(x.get("market", "")) for x in markets if str(x.get("market", "")).startswith("KRW-")]
    out = []
    for start in range(0, len(krw_markets), 100):
        batch = krw_markets[start : start + 100]
        if not batch:
            continue
        query = urllib.parse.urlencode({"markets": ",".join(batch)})
        rows = _get(f"https://api.upbit.com/v1/ticker?{query}")
        for x in rows:
            market = str(x.get("market", ""))
            if not market.startswith("KRW-"):
                continue
            base = market.split("-", 1)[1].upper()
            # Canonical symbol joins regional evidence to the same token research
            # group. Native KRW price/turnover remains explicitly non-USD-like.
            out.append(
                _row(
                    "upbit",
                    f"{base}USDT",
                    x.get("trade_price"),
                    _f(x.get("signed_change_rate")) * 100.0,
                    x.get("acc_trade_price_24h"),
                    market,
                    quote_symbol="KRW",
                    volume_comparable=False,
                    regional_market=True,
                )
            )
    return out


SPOT_SOURCES = [
    ("gate", gate_spot),
    ("bybit", bybit_spot),
    ("okx", okx_spot),
    ("mexc", mexc_spot),
    ("kucoin", kucoin_spot),
    ("binance", binance_spot),
    ("bitget", bitget_spot),
    ("coinex", coinex_spot),
    ("upbit", upbit_spot),
]


def _load_state(path: Path, default):
    gz = Path(str(path) + ".gz")
    try:
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8") as f:
                return json.load(f)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _write_state(path: Path, state: dict) -> None:
    gz = Path(str(path) + ".gz")
    tmp = Path(str(gz) + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(state, f, separators=(",", ":"))
    tmp.replace(gz)
    if path.exists():
        path.unlink()


def _oldest_valid(hist: list[dict], key: str):
    for item in hist:
        value = _f(item.get(key))
        if value > 0:
            return value
    return 0.0


def _enrich(rows: list[dict], state: dict, now: str):
    histories = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    now_dt = _parse_ts(now)
    enriched = []
    for row in rows:
        key = f"spot:{row['exchange']}:{row['symbol']}:{row.get('market_id') or row['symbol']}"
        hist = histories.get(key) if isinstance(histories.get(key), list) else []
        prev = hist[-1] if hist else {}
        baseline_price = _oldest_valid(hist, "price")
        baseline_volume = _oldest_valid(hist, "volume_24h")

        horizon_fields = {}
        for hours, _threshold in PRESSURE_HORIZONS:
            hp = _asof_value(hist, now_dt, hours, "price")
            hv = _asof_value(hist, now_dt, hours, "volume_24h")
            horizon_fields[f"price_change_{hours}h_pct"] = round(_pct(row.get("price"), hp), 4) if hp else 0.0
            horizon_fields[f"volume_multiple_{hours}h"] = round(_multiple(row.get("volume_24h"), hv), 4) if hv else 0.0

        enriched.append(
            {
                **row,
                "price_delta_pct": round(_pct(row.get("price"), prev.get("price")), 4) if prev else 0.0,
                "volume24_delta_pct": round(_pct(row.get("volume_24h"), prev.get("volume_24h")), 4) if prev else 0.0,
                "price_window_pct": round(_pct(row.get("price"), baseline_price), 4) if baseline_price else 0.0,
                "volume_window_multiple": round(_multiple(row.get("volume_24h"), baseline_volume), 4)
                if baseline_volume
                else 0.0,
                "history_points": len(hist),
                **horizon_fields,
            }
        )
        hist.append(
            {
                "observed_at": now,
                "price": row.get("price"),
                "change_24h_pct": row.get("change_24h_pct"),
                "volume_24h": row.get("volume_24h"),
                "quote_symbol": row.get("quote_symbol"),
                "volume_comparable_usd_like": row.get("volume_comparable_usd_like", True),
                "regional_market": row.get("regional_market", False),
                "market_id": row.get("market_id"),
            }
        )
        histories[key] = hist[-STATE_HISTORY_LIMIT:]
    return enriched, {
        "version": 3,
        "updated_at": now,
        "markets": histories,
        "signal_milestones": state.get("signal_milestones")
        if isinstance(state.get("signal_milestones"), dict)
        else {},
    }


def _market_signal(row: dict) -> dict:
    change = _f(row.get("change_24h_pct"))
    price_acc = _f(row.get("price_delta_pct"))
    volume_acc = _f(row.get("volume24_delta_pct"))
    volume = _f(row.get("volume_24h"))
    price_window = _f(row.get("price_window_pct"))
    volume_multiple = _f(row.get("volume_window_multiple"))
    score = 0
    hits = []
    reasons = []
    shadow_hits = []
    shadow_reasons = []

    if change >= 8:
        score += 10
        hits.append("MOMENTUM")
        reasons.append(f"24h spot momentum {change:.1f}%")
    if change >= 20:
        score += 10
    if change >= 50:
        score += 5
    if price_acc >= 2:
        score += 15
        hits.append("PRICE_ACCEL")
        reasons.append(f"spot price acceleration {price_acc:.2f}%/scan")
    if price_acc >= 5:
        score += 10
    if volume_acc >= 8:
        score += 12
        hits.append("VOLUME_ACCEL")
        reasons.append(f"spot volume acceleration {volume_acc:.1f}%/scan")
    if volume_acc >= 25:
        score += 8

    # Absolute turnover bonuses are valid only when the quote is USD-like.
    if row.get("volume_comparable_usd_like", True):
        if volume >= 100_000:
            score += 3
            reasons.append("spot turnover >= $100k")
        if volume >= 1_000_000:
            score += 2

    # LSK-derived absorption remains shadow-only until broad forward validation.
    if (
        row.get("history_points", 0) >= 6
        and volume_multiple >= 3.0
        and abs(price_window) <= 15.0
    ):
        shadow_hits.append("VOLUME_PRICE_ABSORPTION_SHADOW")
        shadow_reasons.append(
            f"volume window {volume_multiple:.2f}x while price window {price_window:.2f}%"
        )
    elif volume_acc >= 25.0 and abs(change) <= 15.0 and abs(price_acc) < 2.0:
        shadow_hits.append("VOLUME_PRICE_ABSORPTION_SHADOW")
        shadow_reasons.append(
            f"volume acceleration {volume_acc:.1f}% with muted 24h price {change:.1f}%"
        )

    # CPOOL-derived hole fix: persistent multi-hour turnover expansion can lead
    # a veteran-token move without any single 15-minute spike. This is strictly
    # observational/shadow-only and cannot alter score or coherent confirmation.
    pressure_hits = []
    pressure_available = []
    for hours, threshold in PRESSURE_HORIZONS:
        multiple = _f(row.get(f"volume_multiple_{hours}h"))
        if multiple > 0:
            pressure_available.append(f"{hours}h")
        if multiple >= threshold:
            pressure_hits.append(f"{hours}h")

    if 3.0 <= change <= 15.0 and pressure_hits:
        shadow_hits.append("PERSISTENT_SPOT_PRESSURE_SHADOW")
        details = ", ".join(
            f"{hours}h={_f(row.get(f'volume_multiple_{hours}h')):.2f}x"
            for hours, _threshold in PRESSURE_HORIZONS
            if f"{hours}h" in pressure_hits
        )
        shadow_reasons.append(
            f"moderate 24h move {change:.1f}% with persistent turnover expansion ({details})"
        )
        if len(pressure_hits) >= 2:
            shadow_hits.append("PERSISTENT_SPOT_PRESSURE_MULTI_HORIZON_SHADOW")

    return {
        "exchange": row.get("exchange"),
        "score": score,
        "hits": hits,
        "hit_count": len(hits),
        "reasons": reasons,
        "shadow_hits": shadow_hits,
        "shadow_reasons": shadow_reasons,
        "change": change,
        "price_acc": price_acc,
        "volume_acc": volume_acc,
        "price_window_pct": price_window,
        "volume_window_multiple": volume_multiple,
        "pressure_horizons_available": pressure_available,
        "pressure_horizon_hits": pressure_hits,
        "volume_multiple_6h": _f(row.get("volume_multiple_6h")),
        "volume_multiple_12h": _f(row.get("volume_multiple_12h")),
        "volume_multiple_24h": _f(row.get("volume_multiple_24h")),
        "volume_comparable_usd_like": bool(row.get("volume_comparable_usd_like", True)),
        "regional_market": bool(row.get("regional_market")),
    }


def _snapshot(now: str, markets: list[dict], score: int, coherent_conf: int, kind: str, best: dict) -> dict:
    usd_like = [x for x in markets if x.get("volume_comparable_usd_like", True)]
    ref_pool = usd_like or markets
    ref = max(ref_pool, key=lambda x: (_f(x.get("volume_24h")), _f(x.get("price"))), default={})
    return {
        "kind": kind,
        "observed_at": now,
        "reference_exchange": ref.get("exchange"),
        "reference_price": _f(ref.get("price")),
        "reference_quote_symbol": ref.get("quote_symbol", "USDT"),
        "reference_change_24h_pct": _f(ref.get("change_24h_pct")),
        "score": min(int(score), 100),
        "confirmations": len({x.get("exchange") for x in markets}),
        "coherent_confirmations": coherent_conf,
        "coherent_exchange": best.get("exchange"),
        "coherent_feature_hits": best.get("hits", []),
        "price_acceleration_max_pct": round(max((_f(x.get("price_delta_pct")) for x in markets), default=0), 4),
        "volume_acceleration_max_pct": round(max((_f(x.get("volume24_delta_pct")) for x in markets), default=0), 4),
        "change_24h_max_pct": round(max((_f(x.get("change_24h_pct")) for x in markets), default=0), 4),
    }


def _regional_lead(local: list[dict]) -> dict:
    regional = [x for x in local if x.get("exchange") in REGIONAL_EXCHANGES]
    nonregional = [x for x in local if x.get("exchange") not in REGIONAL_EXCHANGES]
    regional_real = [x for x in regional if x.get("hit_count", 0) > 0]
    regional_shadow = [x for x in regional if x.get("shadow_hits")]
    nonregional_real = [x for x in nonregional if x.get("hit_count", 0) > 0]

    status = "NONE"
    if regional_real and not nonregional_real:
        status = "REGIONAL_FIRST"
    elif regional_shadow and not nonregional_real:
        status = "REGIONAL_ABSORPTION_FIRST"
    elif regional_real and nonregional_real:
        status = "REGIONAL_CONFIRMED"

    return {
        "status": status,
        "regional_exchanges": sorted({x.get("exchange") for x in regional_real + regional_shadow if x.get("exchange")}),
        "regional_hits": sorted(
            {
                hit
                for x in regional
                for hit in (x.get("hits", []) + x.get("shadow_hits", []))
            }
        ),
        "nonregional_coherent_confirmations": len(
            {x.get("exchange") for x in nonregional_real if x.get("exchange")}
        ),
        "shadow_only": status == "REGIONAL_ABSORPTION_FIRST",
    }


def _slow_ignition(local: list[dict]) -> dict:
    pressure = [
        x
        for x in local
        if "PERSISTENT_SPOT_PRESSURE_SHADOW" in set(x.get("shadow_hits") or [])
    ]
    exchanges = sorted({x.get("exchange") for x in pressure if x.get("exchange")})
    multi_horizon = [x for x in pressure if len(x.get("pressure_horizon_hits") or []) >= 2]
    multi_exchanges = sorted({x.get("exchange") for x in multi_horizon if x.get("exchange")})

    status = "NONE"
    if len(exchanges) >= 2:
        status = "CROSS_VENUE_PERSISTENT"
    elif len(exchanges) == 1:
        status = "BUILDING"

    return {
        "status": status,
        "confirmations": len(exchanges),
        "exchanges": exchanges,
        "multi_horizon_confirmations": len(multi_exchanges),
        "multi_horizon_exchanges": multi_exchanges,
        "shadow_only": True,
        "affects_score": False,
        "actionable": False,
    }


def _coverage(health: dict, markets: list[dict]) -> dict:
    requested = len(SPOT_SOURCES)
    healthy = sum(1 for x in health.values() if x.get("ok"))
    global_ratio = healthy / requested if requested else 0.0
    candidate_exchanges = len({x.get("exchange") for x in markets if x.get("exchange")})
    candidate_ratio = candidate_exchanges / healthy if healthy else 0.0
    if global_ratio >= 0.85:
        confidence = "HIGH"
    elif global_ratio >= 0.6:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    return {
        "requested_sources": requested,
        "healthy_sources": healthy,
        "global_source_coverage_ratio": round(global_ratio, 4),
        "candidate_exchange_breadth_ratio": round(candidate_ratio, 4),
        "confidence": confidence,
    }


def _shadow_sort_key(record: dict):
    slow = record.get("slow_ignition") or {}
    status_rank = {"CROSS_VENUE_PERSISTENT": 2, "BUILDING": 1, "NONE": 0}.get(slow.get("status"), 0)
    return (
        status_rank,
        int(slow.get("confirmations") or 0),
        int(slow.get("multi_horizon_confirmations") or 0),
        len(record.get("shadow_features") or []),
        int(record.get("spot_revival_score") or 0),
    )


def run_cex_spot_revival(out: Path, now: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    errors = []
    health = {}
    with ThreadPoolExecutor(max_workers=len(SPOT_SOURCES)) as pool:
        futures = {pool.submit(fn): name for name, fn in SPOT_SOURCES}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                got = fut.result()
                rows.extend(got)
                health[name] = {"ok": bool(got), "markets": len(got)}
            except Exception as exc:
                errors.append({"exchange": name, "error": str(exc)[:300]})
                health[name] = {"ok": False, "markets": 0}

    state_path = out / "cex-spot-state.json"
    rows, state = _enrich(rows, _load_state(state_path, {}), now)
    milestones = state["signal_milestones"]
    derivatives_first_alerts = _load_derivatives_first_alerts(out)
    groups = {}
    leveraged_products = set()
    leveraged_sensors: dict[str, dict] = {}
    for row in rows:
        symbol = row.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue
        if _is_leveraged_product(symbol):
            leveraged_products.add(symbol)
            underlying = _leveraged_underlying_symbol(symbol)
            if underlying:
                bucket = leveraged_sensors.setdefault(
                    underlying,
                    {
                        "underlying_symbol": underlying,
                        "products": set(),
                        "exchanges": set(),
                        "max_change_24h_pct": 0.0,
                        "max_abs_change_24h_pct": 0.0,
                        "max_volume_24h_usd_like": 0.0,
                        "research_only": True,
                        "affects_score": False,
                        "actionable": False,
                    },
                )
                change = _f(row.get("change_24h_pct"))
                bucket["products"].add(symbol)
                if row.get("exchange"):
                    bucket["exchanges"].add(row.get("exchange"))
                if abs(change) >= _f(bucket.get("max_abs_change_24h_pct")):
                    bucket["max_abs_change_24h_pct"] = abs(change)
                    bucket["max_change_24h_pct"] = change
                if row.get("volume_comparable_usd_like", True):
                    bucket["max_volume_24h_usd_like"] = max(
                        _f(bucket.get("max_volume_24h_usd_like")),
                        _f(row.get("volume_24h")),
                    )
            continue
        groups.setdefault(symbol, []).append(row)

    for sensor in leveraged_sensors.values():
        sensor["products"] = sorted(sensor["products"])
        sensor["exchanges"] = sorted(sensor["exchanges"])
        sensor["active"] = _f(sensor.get("max_abs_change_24h_pct")) >= 25.0

    watchlist = []
    alerts = []
    shadow_watchlist = []
    collision_diagnostics = []
    cross_lane_precursor_count = 0
    for symbol, markets in groups.items():
        scoring_markets, collision_outliers, regional_markets, price_ratio = _price_coherent_partition(markets)
        local = [_market_signal(x) for x in scoring_markets]
        regional_local = [_market_signal(x) for x in regional_markets]
        best = max(
            local,
            key=lambda x: (x["score"], x["hit_count"]),
            default={"score": 0, "hit_count": 0, "reasons": [], "shadow_hits": []},
        )
        coherent = [x for x in local if x.get("hit_count", 0) > 0]
        coherent_conf = len({x.get("exchange") for x in coherent if x.get("exchange")})
        score = int(best.get("score", 0))
        reasons = list(best.get("reasons") or [])
        if coherent_conf >= 2:
            score += 8
            reasons.append(f"{coherent_conf} coherent spot exchange confirmation")
        if coherent_conf >= 4:
            score += 8
        score = min(score, 100)

        shadow_features = sorted({hit for x in local for hit in x.get("shadow_hits", [])})
        shadow_reasons = [reason for x in local for reason in x.get("shadow_reasons", [])]
        if any(x.get("hit_count", 0) > 0 for x in regional_local):
            shadow_features = sorted(set(shadow_features + ["REGIONAL_MOMENTUM_SHADOW"]))
            shadow_reasons.append("regional native-quote momentum detected; research-only until exact identity")
        leveraged_sensor = leveraged_sensors.get(symbol)
        if leveraged_sensor and leveraged_sensor.get("active"):
            shadow_features = sorted(set(shadow_features + ["LEVERAGED_UNDERLYING_MOMENTUM_SHADOW"]))
            shadow_reasons.append(
                "leveraged products accelerated "
                f"{_f(leveraged_sensor.get('max_change_24h_pct')):.2f}% "
                "without changing the underlying action score"
            )
        regional_lead = _regional_lead(local + regional_local)
        slow_ignition = _slow_ignition(local)
        coverage = _coverage(health, scoring_markets + regional_markets)
        symbol_collision = {
            "suspected": bool(collision_outliers),
            "usd_price_ratio_max_min": round(price_ratio, 6),
            "price_coherent_exchanges": sorted({x.get("exchange") for x in scoring_markets if x.get("exchange")}),
            "outlier_exchanges": sorted({x.get("exchange") for x in collision_outliers if x.get("exchange")}),
            "outlier_markets": [
                {
                    "exchange": x.get("exchange"),
                    "market_id": x.get("market_id"),
                    "price": _f(x.get("price")),
                    "change_24h_pct": _f(x.get("change_24h_pct")),
                }
                for x in collision_outliers
            ],
            "promotion_effect": "OUTLIERS_EXCLUDED_FROM_CROSS_EXCHANGE_CONFIRMATION",
        }
        if collision_outliers:
            collision_diagnostics.append({
                "symbol": symbol,
                **symbol_collision,
            })
            outlier_signals = [_market_signal(x) for x in collision_outliers]
            if any(x.get("hit_count", 0) > 0 for x in outlier_signals):
                shadow_features = sorted(set(shadow_features + ["SYMBOL_COLLISION_OUTLIER_SHADOW"]))
                shadow_reasons.append(
                    "same-ticker USD markets split into divergent price cohorts; outlier momentum kept research-only"
                )

        ms = milestones.setdefault(symbol, {})
        first = _snapshot(now, scoring_markets, score, coherent_conf, "FIRST_SEEN", best)
        if "first_seen" not in ms:
            ms["first_seen"] = first
        if best.get("hit_count") and "first_anomaly" not in ms:
            ms["first_anomaly"] = {**first, "kind": "FIRST_ANOMALY"}

        cross_lane_precursor = _cross_lane_derivatives_precursor(symbol, ms, derivatives_first_alerts)
        if cross_lane_precursor:
            cross_lane_precursor_count += 1
            shadow_features = sorted(set(shadow_features + ["CEX_DERIVATIVES_PRECURSOR_SHADOW"]))
            shadow_reasons.append(
                "strong coherent derivatives FIRST_ALERT is price/time anchored by spot; "
                "identity resolution accelerated without changing spot score"
            )

        if shadow_features and "first_shadow_watch" not in ms:
            ms["first_shadow_watch"] = {
                **first,
                "kind": "FIRST_SHADOW_WATCH",
                "shadow_features": shadow_features,
                "slow_ignition_status": slow_ignition.get("status"),
            }
        if slow_ignition.get("status") == "CROSS_VENUE_PERSISTENT" and "first_cross_venue_slow_ignition" not in ms:
            ms["first_cross_venue_slow_ignition"] = {
                **first,
                "kind": "FIRST_CROSS_VENUE_SLOW_IGNITION",
                "exchanges": slow_ignition.get("exchanges", []),
            }
        if score >= WATCH_SCORE and "first_watch" not in ms:
            ms["first_watch"] = {**first, "kind": "FIRST_WATCH"}
        if score >= ALERT_SCORE and "first_alert" not in ms:
            ms["first_alert"] = {**first, "kind": "FIRST_ALERT"}

        if score >= ALERT_SCORE:
            status = "DNA_WATCH_RESEARCH"
        elif score >= WATCH_SCORE:
            status = "MOMENTUM_WATCH_RESEARCH"
        else:
            status = "SHADOW_WATCH_RESEARCH"

        record = {
            "symbol": symbol,
            "market_type": "spot",
            "spot_revival_score": score,
            "status": status,
            "research_only": True,
            "actionable": False,
            "automatic_buy": False,
            "identity_required_before_actionable": True,
            "leveraged_product": False,
            "learning_eligible": True,
            "reasons": reasons,
            "shadow_features": shadow_features,
            "shadow_reasons": shadow_reasons,
            "shadow_features_affect_score": False,
            "shadow_watch_eligible": bool(shadow_features),
            "leveraged_underlying_sensor": leveraged_sensor,
            "cross_lane_derivatives_precursor": cross_lane_precursor,
            "regional_spot_lead": regional_lead,
            "slow_ignition": slow_ignition,
            "source_coverage": coverage,
            "symbol_collision": symbol_collision,
            "confirmations": len({x.get("exchange") for x in markets}),
            "price_coherent_confirmations": len({x.get("exchange") for x in scoring_markets}),
            "coherent_confirmations": coherent_conf,
            "coherent_exchange": best.get("exchange"),
            "coherent_feature_hits": best.get("hits", []),
            "change_24h_max_pct": round(max((_f(x.get("change_24h_pct")) for x in scoring_markets), default=0), 4),
            "observed_change_24h_max_pct_all_markets": round(max((_f(x.get("change_24h_pct")) for x in markets), default=0), 4),
            "price_acceleration_max_pct": round(max((_f(x.get("price_delta_pct")) for x in scoring_markets), default=0), 4),
            "volume_acceleration_max_pct": round(max((_f(x.get("volume24_delta_pct")) for x in scoring_markets), default=0), 4),
            "volume_window_multiple_max": round(max((_f(x.get("volume_window_multiple")) for x in scoring_markets), default=0), 4),
            "volume_multiple_6h_max": round(max((_f(x.get("volume_multiple_6h")) for x in scoring_markets), default=0), 4),
            "volume_multiple_12h_max": round(max((_f(x.get("volume_multiple_12h")) for x in scoring_markets), default=0), 4),
            "volume_multiple_24h_max": round(max((_f(x.get("volume_multiple_24h")) for x in scoring_markets), default=0), 4),
            "price_change_6h_max_pct": round(max((_f(x.get("price_change_6h_pct")) for x in scoring_markets), default=0), 4),
            "price_change_12h_max_pct": round(max((_f(x.get("price_change_12h_pct")) for x in scoring_markets), default=0), 4),
            "price_change_24h_window_max_pct": round(max((_f(x.get("price_change_24h_pct")) for x in scoring_markets), default=0), 4),
            "price_window_abs_min_pct": round(min((abs(_f(x.get("price_window_pct"))) for x in scoring_markets), default=0), 4),
            "exchanges": sorted({x.get("exchange") for x in markets if x.get("exchange")}),
            "milestones": ms,
            "markets": markets,
        }
        if shadow_features:
            shadow_watchlist.append(record)
        if score >= WATCH_SCORE:
            watchlist.append(record)
        if score >= ALERT_SCORE:
            alerts.append(record)

    _write_state(state_path, state)
    watchlist.sort(
        key=lambda x: (x["spot_revival_score"], x["coherent_confirmations"], x["confirmations"]),
        reverse=True,
    )
    alerts.sort(
        key=lambda x: (x["spot_revival_score"], x["coherent_confirmations"], x["confirmations"]),
        reverse=True,
    )
    shadow_watchlist.sort(key=_shadow_sort_key, reverse=True)

    excluded = sorted(leveraged_products)
    healthy_sources = sum(1 for x in health.values() if x.get("ok"))
    source_coverage_ratio = healthy_sources / len(SPOT_SOURCES) if SPOT_SOURCES else 0.0
    payload = {
        "version": 4,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_CEX_SPOT_REVIVAL_V4",
        "production_portfolio_impact": "NONE",
        "symbol_only_actionable": False,
        "shadow_watch_actionable": False,
        "shadow_watch_score_effect": False,
        "identity_rule": "EXACT_CHAIN_CONTRACT_AND_PAIR_REQUIRED_BEFORE_ANY_ACTIONABLE_PROMOTION",
        "learning_truth_contract": {
            "leveraged_cex_products_excluded": True,
            "no_hindsight": True,
            "regional_native_quote_not_compared_as_usd": True,
            "regional_native_quote_never_counts_as_action_coherence": True,
            "same_ticker_price_collision_outliers_excluded_from_coherence": True,
            "leveraged_underlying_signal_shadow_only": True,
            "derivatives_spot_cross_lane_precursor_shadow_only_until_exact_identity": True,
            "derivatives_spot_cross_lane_requires_immutable_time_price_anchor": True,
            "derivatives_spot_cross_lane_never_changes_spot_score": True,
            "new_lsk_features_shadow_only": True,
            "slow_ignition_shadow_only": True,
            "shadow_watch_below_watch_score_allowed": True,
            "shadow_watch_never_actionable": True,
        },
        "leveraged_products_excluded_count": len(excluded),
        "leveraged_products_excluded": excluded[:100],
        "leveraged_underlying_sensors": sorted(
            leveraged_sensors.values(),
            key=lambda x: _f(x.get("max_abs_change_24h_pct")),
            reverse=True,
        )[:100],
        "requested_sources": [name for name, _ in SPOT_SOURCES],
        "source_health": health,
        "healthy_sources": healthy_sources,
        "source_coverage_ratio": round(source_coverage_ratio, 4),
        "markets_seen": len(rows),
        "symbols_seen": len(groups),
        "watch_score": WATCH_SCORE,
        "alert_score": ALERT_SCORE,
        "watch_count": len(watchlist),
        "alerts_count": len(alerts),
        "shadow_watch_count": len(shadow_watchlist),
        "symbol_collision_count": len(collision_diagnostics),
        "symbol_collisions": collision_diagnostics[:100],
        "cross_lane_derivatives_precursor_count": cross_lane_precursor_count,
        "cross_lane_derivatives_source_count": len(derivatives_first_alerts),
        "watchlist": watchlist[:100],
        "alerts": alerts[:100],
        "shadow_watchlist": shadow_watchlist[:100],
        "errors": errors,
    }
    (out / "cex-spot-revival-radar.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def learning_row(x: dict) -> dict:
        return {
            "symbol": x["symbol"],
            "score": x["spot_revival_score"],
            "status": x["status"],
            "confirmations": x["confirmations"],
            "coherent_confirmations": x["coherent_confirmations"],
            "coherent_feature_hits": x["coherent_feature_hits"],
            "shadow_features": x["shadow_features"],
            "leveraged_underlying_sensor": x.get("leveraged_underlying_sensor"),
            "cross_lane_derivatives_precursor": x.get("cross_lane_derivatives_precursor"),
            "symbol_collision": x.get("symbol_collision"),
            "regional_spot_lead": x["regional_spot_lead"],
            "slow_ignition": x["slow_ignition"],
            "source_coverage": x["source_coverage"],
            "change_24h_max_pct": x["change_24h_max_pct"],
            "price_acceleration_max_pct": x["price_acceleration_max_pct"],
            "volume_acceleration_max_pct": x["volume_acceleration_max_pct"],
            "volume_window_multiple_max": x["volume_window_multiple_max"],
            "volume_multiple_6h_max": x["volume_multiple_6h_max"],
            "volume_multiple_12h_max": x["volume_multiple_12h_max"],
            "volume_multiple_24h_max": x["volume_multiple_24h_max"],
            "milestones": x.get("milestones", {}),
        }

    learning = {
        "version": 4,
        "updated_at": now,
        "purpose": "learn whether spot acceleration, regional leadership, absorption, and persistent cross-venue pressure predict veteran-token revival before late pumps",
        "research_only": True,
        "no_hindsight": True,
        "leveraged_cex_products_excluded": True,
        "new_lsk_features_shadow_only": True,
        "slow_ignition_shadow_only": True,
        "shadow_watch_below_watch_score_allowed": True,
        "shadow_watch_never_actionable": True,
        "cross_lane_derivatives_precursor_shadow_only": True,
        "excluded_products": excluded[:100],
        "features": [
            "spot_24h_momentum",
            "spot_price_acceleration",
            "spot_volume_acceleration",
            "cross_exchange_spot_confirmation",
            "volume_window_multiple",
            "volume_price_absorption_shadow",
            "regional_spot_lead_upbit",
            "source_coverage_confidence",
            "persistent_spot_pressure_shadow",
            "slow_ignition_cross_venue_shadow",
            "shadow_watch_below_watch_score",
        ],
        "top_candidates": [learning_row(x) for x in watchlist[:50]],
        "top_shadow_candidates": [learning_row(x) for x in shadow_watchlist[:50]],
    }
    (out / "cex-spot-learning.json").write_text(json.dumps(learning, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(
        json.dumps(
            run_cex_spot_revival(Path("data"), datetime.now(timezone.utc).isoformat()),
            indent=2,
        )
    )
