from __future__ import annotations

import json
import math
import statistics
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    import resilient_http
except ImportError:  # package import in pytest / module mode
    from scripts import resilient_http

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/chain-context-shadow.json"
USER_STATE = ROOT / "data/user-watch-final-buy-state.json"
UNIFIED_REPORT = ROOT / "data/unified-watch-intelligence-report.json"
REAL_ALERT_LEDGER = ROOT / "data/real-alert-10usd-ledger.json"
GATE = "https://api.gateio.ws/api/v4"
UA = "Wallet500-ChainContextShadow/1.0"

MODE = "SHADOW_RESEARCH_ONLY_NO_BUY_GATING"
MAX_TARGET_HISTORY = 192
MIN_HISTORY_SPACING_SECONDS = 10 * 60

# Benchmark means the liquid network/ecosystem asset used to measure market beta.
# Base has no native token, so ETH is intentionally used as the execution/network proxy.
CHAIN_BENCHMARK = {
    "ethereum": "ETH",
    "eth": "ETH",
    "base": "ETH",
    "arbitrum": "ARB",
    "optimism": "OP",
    "bsc": "BNB",
    "binance-smart-chain": "BNB",
    "solana": "SOL",
    "polygon": "POL",
    "avalanche": "AVAX",
    "harmony": "ONE",
}
BENCHMARK_PAIR = {symbol: f"{symbol}_USDT" for symbol in set(CHAIN_BENCHMARK.values())}


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_dt().isoformat()


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def num(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def ts(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        if value > 1e12:
            value /= 1000.0
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        try:
            value = float(text)
            if value > 1e12:
                value /= 1000.0
            return value
        except ValueError:
            return None


def iso_from_ts(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def pct_change(old, new) -> float | None:
    old = num(old)
    new = num(new)
    if old is None or new is None or old <= 0:
        return None
    return (new / old - 1.0) * 100.0


def round_or_none(value, digits=4):
    value = num(value)
    return None if value is None else round(value, digits)


def network_regime(value, threshold=1.0) -> str:
    value = num(value)
    if value is None:
        return "UNKNOWN"
    if value > threshold:
        return "RISING"
    if value < -threshold:
        return "FALLING"
    return "STABLE"


def parse_identity_network(identity_key: str) -> str | None:
    text = str(identity_key or "").strip()
    if not text or ":" not in text:
        return None
    network = text.split(":", 1)[0].lower()
    if network in {"cex", "gate", "binance"}:
        return None
    return network


def benchmark_for_network(network: str | None) -> str | None:
    return CHAIN_BENCHMARK.get(str(network or "").lower())


def get_json(url: str, timeout: int = 12):
    try:
        return resilient_http.request_json(
            url,
            timeout=timeout,
            attempts=3,
            cache_ttl=20,
            min_interval=0.35,
            user_agent=UA,
        )
    except Exception as exc:
        print("CHAIN_CONTEXT_FETCH_ERROR", url.split("?")[0], type(exc).__name__)
        return None


def gate_ticker_price(symbol: str) -> float | None:
    pair = BENCHMARK_PAIR.get(symbol)
    if not pair:
        return None
    q = urllib.parse.urlencode({"currency_pair": pair})
    rows = get_json(f"{GATE}/spot/tickers?{q}")
    if isinstance(rows, list) and rows:
        return num(rows[0].get("last") if isinstance(rows[0], dict) else None)
    if isinstance(rows, dict):
        return num(rows.get("last"))
    return None


def parse_gate_candles(rows) -> list[tuple[float, float]]:
    out = []
    for row in rows or []:
        candle_ts = None
        close = None
        if isinstance(row, dict):
            candle_ts = ts(row.get("t") or row.get("timestamp") or row.get("time"))
            close = num(row.get("c") or row.get("close"))
        elif isinstance(row, (list, tuple)) and len(row) >= 3:
            candle_ts = ts(row[0])
            # Gate v4 spot candlesticks: [timestamp, quote_volume, close, high, low, open, ...]
            close = num(row[2])
        if candle_ts is None or close is None or close <= 0:
            continue
        out.append((candle_ts, close))
    out.sort(key=lambda x: x[0])
    dedup = {}
    for candle_ts, close in out:
        dedup[candle_ts] = close
    return sorted(dedup.items())


def gate_candles(symbol: str, interval: str, limit: int) -> list[tuple[float, float]]:
    pair = BENCHMARK_PAIR.get(symbol)
    if not pair:
        return []
    q = urllib.parse.urlencode({
        "currency_pair": pair,
        "interval": interval,
        "limit": int(limit),
    })
    return parse_gate_candles(get_json(f"{GATE}/spot/candlesticks?{q}"))


def price_at_or_before(
    candles: list[tuple[float, float]],
    target_ts: float | None,
    *,
    max_age_seconds: float | None = None,
) -> float | None:
    if target_ts is None or not candles:
        return None
    chosen = None
    for candle_ts, price in candles:
        if candle_ts <= target_ts:
            chosen = (candle_ts, price)
        else:
            break
    if chosen is None:
        return None
    if max_age_seconds is not None and target_ts - chosen[0] > max_age_seconds:
        return None
    return chosen[1]


def current_network_metrics(
    current_price: float | None,
    candles_15m: list[tuple[float, float]],
    candles_1h: list[tuple[float, float]],
    now_ts: float,
) -> dict:
    current_price = num(current_price)

    def ret(seconds, candles, max_age):
        past = price_at_or_before(candles, now_ts - seconds, max_age_seconds=max_age)
        return round_or_none(pct_change(past, current_price))

    metrics = {
        "price_usd": current_price,
        "return_15m_pct": ret(15 * 60, candles_15m, 45 * 60),
        "return_1h_pct": ret(60 * 60, candles_15m, 90 * 60),
        "return_4h_pct": ret(4 * 60 * 60, candles_15m, 90 * 60),
        "return_24h_pct": ret(24 * 60 * 60, candles_1h, 2 * 60 * 60),
    }
    metrics["regime_4h"] = network_regime(metrics["return_4h_pct"], 1.0)
    metrics["regime_24h"] = network_regime(metrics["return_24h_pct"], 2.0)
    return metrics


def event_network_context(
    event_at,
    benchmark_current: float | None,
    candles_1h: list[tuple[float, float]],
    now_ts: float,
) -> dict | None:
    event_ts = ts(event_at)
    if event_ts is None:
        return None
    event_price = price_at_or_before(candles_1h, event_ts, max_age_seconds=2 * 60 * 60)
    if event_price is None:
        return None
    pre_1h = price_at_or_before(candles_1h, event_ts - 60 * 60, max_age_seconds=2 * 60 * 60)
    pre_4h = price_at_or_before(candles_1h, event_ts - 4 * 60 * 60, max_age_seconds=2 * 60 * 60)
    pre_24h = price_at_or_before(candles_1h, event_ts - 24 * 60 * 60, max_age_seconds=2 * 60 * 60)
    current = num(benchmark_current)
    return {
        "event_at": iso_from_ts(event_ts),
        "benchmark_price_usd": event_price,
        "network_pre_1h_pct": round_or_none(pct_change(pre_1h, event_price)),
        "network_pre_4h_pct": round_or_none(pct_change(pre_4h, event_price)),
        "network_pre_24h_pct": round_or_none(pct_change(pre_24h, event_price)),
        "network_since_event_pct": round_or_none(pct_change(event_price, current))
        if event_ts <= now_ts else None,
        "network_regime_pre_4h": network_regime(pct_change(pre_4h, event_price), 1.0),
    }


def token_event_relative(
    event_token_price,
    current_token_price,
    event_network: dict | None,
) -> dict | None:
    if not event_network:
        return None
    token_move = pct_change(event_token_price, current_token_price)
    network_move = num(event_network.get("network_since_event_pct"))
    relative = None
    if token_move is not None and network_move is not None:
        relative = token_move - network_move
    out = dict(event_network)
    out.update({
        "token_event_price_usd": num(event_token_price),
        "token_since_event_pct": round_or_none(token_move),
        "relative_strength_since_event_pct": round_or_none(relative),
    })
    return out


def build_flags(
    token_since_discovery,
    network_since_discovery,
    relative_since_discovery,
    network_since_final_buy,
) -> list[str]:
    token_move = num(token_since_discovery)
    net_move = num(network_since_discovery)
    rel = num(relative_since_discovery)
    post_buy_net = num(network_since_final_buy)
    flags = []
    if token_move is not None and net_move is not None:
        if token_move >= 2.0 and net_move <= -1.0:
            flags.append("TOKEN_UP_NETWORK_DOWN")
        if token_move >= -1.0 and net_move <= -3.0:
            flags.append("TOKEN_HOLDS_NETWORK_DUMPS")
        if token_move < 0.0 and net_move >= 2.0:
            flags.append("TOKEN_WEAK_NETWORK_UP")
    if rel is not None and rel >= 5.0:
        flags.append("RELATIVE_STRENGTH_POSITIVE")
    if rel is not None and rel <= -5.0:
        flags.append("RELATIVE_STRENGTH_NEGATIVE")
    if post_buy_net is not None and post_buy_net <= -2.0:
        flags.append("POST_BUY_NETWORK_DETERIORATION")
    return flags


def append_history(existing: list, row: dict, now_ts: float) -> list:
    existing = [x for x in (existing or []) if isinstance(x, dict)]
    last_ts = ts(existing[-1].get("at")) if existing else None
    if last_ts is None or now_ts - last_ts >= MIN_HISTORY_SPACING_SECONDS:
        existing.append(row)
    return existing[-MAX_TARGET_HISTORY:]


def unified_target_index(report: dict) -> dict:
    out = {}
    for row in (report or {}).get("targets") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("identity_key") or "")
        if key:
            out[key] = row
    return out


def _bucket_stats(rows: list[dict]) -> dict:
    values = [num(x.get("token_24h_pct")) for x in rows]
    values = [x for x in values if x is not None]
    if not values:
        return {
            "n": 0,
            "positive_24h_pct": None,
            "avg_token_24h_pct": None,
            "median_token_24h_pct": None,
        }
    return {
        "n": len(values),
        "positive_24h_pct": round(sum(1 for x in values if x > 0) / len(values) * 100, 2),
        "avg_token_24h_pct": round(sum(values) / len(values), 4),
        "median_token_24h_pct": round(statistics.median(values), 4),
    }


def build_real_alert_research(
    ledger: dict,
    benchmark_data: dict[str, dict],
) -> dict:
    samples = []
    for p in (ledger or {}).get("positions") or []:
        if not isinstance(p, dict):
            continue
        token_24h = num(((p.get("checkpoints") or {}).get("24h") or {}).get("return_pct"))
        entry_ts = ts(p.get("entry_time"))
        network = str(p.get("chain") or "").lower()
        benchmark = benchmark_for_network(network)
        if token_24h is None or entry_ts is None or benchmark not in benchmark_data:
            continue
        candles = benchmark_data[benchmark].get("candles_1h") or []
        at_entry = price_at_or_before(candles, entry_ts, max_age_seconds=2 * 60 * 60)
        pre_4h = price_at_or_before(candles, entry_ts - 4 * 60 * 60, max_age_seconds=2 * 60 * 60)
        pre_24h = price_at_or_before(candles, entry_ts - 24 * 60 * 60, max_age_seconds=2 * 60 * 60)
        post_24h = price_at_or_before(candles, entry_ts + 24 * 60 * 60, max_age_seconds=2 * 60 * 60)
        net_pre_4h = pct_change(pre_4h, at_entry)
        net_pre_24h = pct_change(pre_24h, at_entry)
        net_post_24h = pct_change(at_entry, post_24h)
        if at_entry is None or net_pre_4h is None:
            continue
        samples.append({
            "symbol": p.get("symbol"),
            "chain": network,
            "benchmark": benchmark,
            "entry_at": iso_from_ts(entry_ts),
            "network_pre_4h_pct": round_or_none(net_pre_4h),
            "network_pre_24h_pct": round_or_none(net_pre_24h),
            "network_post_24h_pct": round_or_none(net_post_24h),
            "token_24h_pct": round_or_none(token_24h),
            "relative_24h_pct": round_or_none(token_24h - net_post_24h)
            if net_post_24h is not None else None,
            "network_regime_pre_4h": network_regime(net_pre_4h, 1.0),
        })
    groups = {
        "RISING": _bucket_stats([x for x in samples if x["network_regime_pre_4h"] == "RISING"]),
        "STABLE": _bucket_stats([x for x in samples if x["network_regime_pre_4h"] == "STABLE"]),
        "FALLING": _bucket_stats([x for x in samples if x["network_regime_pre_4h"] == "FALLING"]),
    }
    return {
        "sample_size": len(samples),
        "basis": "REAL_ALERT_TOKEN_24H_OUTCOME_VS_NETWORK_4H_PRE_ENTRY_REGIME",
        "research_only": True,
        "buy_gate_effect": False,
        "groups": groups,
        "samples": samples,
    }


def run() -> dict:
    generated_at = now_iso()
    now_ts = ts(generated_at) or time.time()
    previous = load_json(OUTPUT, {})
    user_state = load_json(USER_STATE, {})
    unified_report = load_json(UNIFIED_REPORT, {})
    ledger = load_json(REAL_ALERT_LEDGER, {})
    report_index = unified_target_index(unified_report)

    raw_targets = (user_state or {}).get("targets") or {}
    target_rows = []
    benchmark_symbols = set()
    for key, state in raw_targets.items():
        if not isinstance(state, dict):
            continue
        identity_key = str(state.get("identity_key") or key)
        network = parse_identity_network(identity_key)
        benchmark = benchmark_for_network(network)
        if not network or not benchmark:
            continue
        if num(state.get("last_price")) is None:
            continue
        benchmark_symbols.add(benchmark)
        target_rows.append((identity_key, network, benchmark, state))

    for p in (ledger or {}).get("positions") or []:
        benchmark = benchmark_for_network((p or {}).get("chain"))
        if benchmark:
            benchmark_symbols.add(benchmark)

    benchmark_data = {}
    for symbol in sorted(benchmark_symbols):
        current = gate_ticker_price(symbol)
        candles_15m = gate_candles(symbol, "15m", 110)
        candles_1h = gate_candles(symbol, "1h", 500)
        benchmark_data[symbol] = {
            "price_usd": current,
            "candles_15m": candles_15m,
            "candles_1h": candles_1h,
            "metrics": current_network_metrics(current, candles_15m, candles_1h, now_ts),
        }

    prev_targets = (previous or {}).get("targets") or {}
    targets_out = {}
    for identity_key, network, benchmark, state in target_rows:
        current_token_price = num(state.get("last_price"))
        report_row = report_index.get(identity_key) or {}
        first_seen_at = report_row.get("first_seen_at") or state.get("first_seen_at")
        discovery_token_price = num(
            report_row.get("discovery_price"),
            num(state.get("watch_low_price"), current_token_price),
        )
        bench = benchmark_data.get(benchmark) or {}
        bench_current = num(bench.get("price_usd"))
        candles_1h = bench.get("candles_1h") or []
        discovery_net = event_network_context(first_seen_at, bench_current, candles_1h, now_ts)
        discovery = token_event_relative(
            discovery_token_price,
            current_token_price,
            discovery_net,
        )
        old = prev_targets.get(identity_key) if isinstance(prev_targets, dict) else {}
        if discovery is None:
            discovery = (old or {}).get("discovery_context")
        pre_buy = token_event_relative(
            state.get("last_pre_buy_alert_price"),
            current_token_price,
            event_network_context(
                state.get("last_pre_buy_alert_at"),
                bench_current,
                candles_1h,
                now_ts,
            ),
        )
        final_buy = token_event_relative(
            state.get("last_alert_price"),
            current_token_price,
            event_network_context(
                state.get("last_alert_at"),
                bench_current,
                candles_1h,
                now_ts,
            ),
        )
        if pre_buy is None:
            pre_buy = (old or {}).get("pre_buy_context")
        if final_buy is None:
            final_buy = (old or {}).get("final_buy_context")

        token_since_discovery = (discovery or {}).get("token_since_event_pct")
        network_since_discovery = (discovery or {}).get("network_since_event_pct")
        relative_since_discovery = (discovery or {}).get("relative_strength_since_event_pct")
        network_since_final_buy = (final_buy or {}).get("network_since_event_pct")
        flags = build_flags(
            token_since_discovery,
            network_since_discovery,
            relative_since_discovery,
            network_since_final_buy,
        )

        history = append_history(
            (old or {}).get("history") or [],
            {
                "at": generated_at,
                "token_price_usd": current_token_price,
                "benchmark_price_usd": bench_current,
                "network_4h_pct": (bench.get("metrics") or {}).get("return_4h_pct"),
                "network_24h_pct": (bench.get("metrics") or {}).get("return_24h_pct"),
                "relative_strength_since_discovery_pct": relative_since_discovery,
            },
            now_ts,
        )
        targets_out[identity_key] = {
            "symbol": state.get("symbol"),
            "identity_key": identity_key,
            "network": network,
            "benchmark": benchmark,
            "shadow_only": True,
            "buy_gate_effect": False,
            "last_engine_state": state.get("last_state"),
            "last_seen_at": state.get("last_seen_at"),
            "current_token_price_usd": current_token_price,
            "network_now": bench.get("metrics") or {},
            "discovery_context": discovery,
            "pre_buy_context": pre_buy,
            "final_buy_context": final_buy,
            "flags": flags,
            "history": history,
        }

    benchmark_snapshot = {
        symbol: {
            **(row.get("metrics") or {}),
            "benchmark": symbol,
            "source": "Gate spot public ticker/candles",
        }
        for symbol, row in benchmark_data.items()
    }
    research = build_real_alert_research(ledger, benchmark_data)
    output = {
        "version": 1,
        "generated_at": generated_at,
        "mode": MODE,
        "policy": {
            "research_only": True,
            "shadow_only": True,
            "affects_buy_gate": False,
            "affects_pre_buy_gate": False,
            "telegram_alerts": False,
            "automatic_trade": False,
            "purpose": (
                "Measure token alpha and regime dependence versus its network benchmark "
                "before discovery, at discovery, PRE-BUY/FINAL-BUY and after."
            ),
        },
        "benchmark_map": CHAIN_BENCHMARK,
        "benchmark_snapshot": benchmark_snapshot,
        "target_count": len(targets_out),
        "targets": targets_out,
        "real_alert_research": research,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        "CHAIN_CONTEXT_SHADOW",
        json.dumps({
            "generated_at": generated_at,
            "target_count": len(targets_out),
            "benchmarks": sorted(benchmark_snapshot),
            "real_alert_sample_size": research.get("sample_size"),
            "mode": MODE,
        }, ensure_ascii=False),
    )
    return output


if __name__ == "__main__":
    run()
