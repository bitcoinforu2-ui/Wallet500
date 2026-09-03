from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .revival_1000 import looks_like_solana_address

DATA = Path("data")
SOURCE = DATA / "revival-1000-latest.json"
LATEST = DATA / "hybrid-token-profiles.json"
STATE = DATA / "hybrid-token-state.json"
EXTERNAL = DATA / "hybrid-external-evidence.json"
MODE = "RESEARCH_ONLY_HYBRID_TOKEN_PROFILE_V1"
CONTRACT = "HYBRID_TOKEN_PROFILE_V1"
NETWORK = "solana"
ALPHA = 0.25
MIN_BASELINE_OBSERVATIONS = 3
MIN_IGNITION_VOLUME_24H_USD = 10_000.0

CHANNEL_WEIGHTS = {
    "market": 30.0,
    "liquidity_pair": 25.0,
    "holders": 15.0,
    "wallets": 15.0,
    "social": 10.0,
    "news": 5.0,
}
EXTERNAL_CHANNELS = ("holders", "wallets", "social", "news")
METRICS = (
    "price_usd",
    "market_cap_usd",
    "volume_24h_usd",
    "dex_pair_liquidity_usd",
    "dex_pair_volume_24h_usd",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _n(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _dt(value: object) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _pct(cur, base):
    cur = _n(cur)
    base = _n(base)
    if cur is None or base in (None, 0):
        return None
    return (cur / base - 1.0) * 100.0


def _metric_deviation(cur, stat: dict | None) -> dict:
    cur = _n(cur)
    stat = stat or {}
    count = int(stat.get("count") or 0)
    mean = _n(stat.get("mean"))
    var = max(0.0, _n(stat.get("var"), 0.0) or 0.0)
    last = _n(stat.get("last"))
    ratio = cur / mean if cur is not None and mean not in (None, 0) else None
    z = None
    if cur is not None and mean is not None and count >= MIN_BASELINE_OBSERVATIONS:
        sd = math.sqrt(var)
        if sd > max(abs(mean) * 1e-6, 1e-12):
            z = (cur - mean) / sd
    return {
        "baseline_count": count,
        "baseline_mean": mean,
        "ratio_to_baseline": round(ratio, 4) if ratio is not None else None,
        "z_score": round(z, 3) if z is not None else None,
        "change_from_previous_pct": round(_pct(cur, last), 3) if _pct(cur, last) is not None else None,
    }


def _update_stat(stat: dict | None, value) -> dict:
    value = _n(value)
    stat = dict(stat or {})
    if value is None:
        return stat
    count = int(stat.get("count") or 0)
    mean = _n(stat.get("mean"))
    var = max(0.0, _n(stat.get("var"), 0.0) or 0.0)
    if count <= 0 or mean is None:
        return {"count": 1, "mean": value, "var": 0.0, "last": value}
    delta = value - mean
    new_mean = mean + ALPHA * delta
    new_var = (1.0 - ALPHA) * (var + ALPHA * delta * delta)
    return {
        "count": count + 1,
        "mean": round(new_mean, 12),
        "var": round(max(0.0, new_var), 12),
        "last": value,
    }


def _market_channel(coin: dict, stats: dict) -> dict:
    score = 0.0
    signals: list[str] = []
    vol = _metric_deviation(coin.get("volume_24h_usd"), stats.get("volume_24h_usd"))
    price = _metric_deviation(coin.get("price_usd"), stats.get("price_usd"))
    legacy = max(0.0, min(100.0, _n(coin.get("watch_score_market_only"), 0.0) or 0.0))
    score += legacy * 0.25

    vr = vol.get("ratio_to_baseline")
    vz = vol.get("z_score")
    if vr is not None and vr >= 1.5:
        score += 15; signals.append(f"SELF_VOLUME_{vr:.2f}X")
    if vr is not None and vr >= 2.0:
        score += 10; signals.append("SELF_VOLUME_GE_2X")
    if vz is not None and vz >= 2.0:
        score += 15; signals.append(f"VOLUME_Z_{vz:.2f}")
    if vz is not None and vz >= 3.0:
        score += 10; signals.append("VOLUME_Z_GE_3")

    pz = price.get("z_score")
    if pz is not None and abs(pz) >= 2.0:
        score += 15; signals.append(f"PRICE_Z_{pz:.2f}")
    if pz is not None and abs(pz) >= 3.0:
        score += 10; signals.append("PRICE_Z_ABS_GE_3")

    c24 = _n(coin.get("change_24h_pct"), 0.0) or 0.0
    if abs(c24) >= 8:
        score += 10; signals.append(f"PRICE_24H_{c24:+.1f}PCT")
    if abs(c24) >= 20:
        score += 10; signals.append("PRICE_24H_ABS_GE_20")

    available = _n(coin.get("price_usd")) is not None and _n(coin.get("volume_24h_usd")) is not None
    return {
        "available": available,
        "verified": available,
        "source": "REVIVAL_MARKET+SELF_BASELINE_EWMA",
        "score": round(min(100.0, score), 2) if available else 0.0,
        "signals": signals,
        "deviation": {"volume_24h": vol, "price": price},
    }

def _liquidity_pair_channel(coin: dict, stats: dict, previous_pair: str | None) -> tuple[dict, float, list[str]]:
    exact = coin.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
    pair = str(coin.get("dex_pair_address") or "")
    liq_value = _n(coin.get("dex_pair_liquidity_usd"))
    pv_value = _n(coin.get("dex_pair_volume_24h_usd"))
    available = exact and looks_like_solana_address(pair) and liq_value is not None and pv_value is not None
    liq = _metric_deviation(liq_value, stats.get("dex_pair_liquidity_usd"))
    pv = _metric_deviation(pv_value, stats.get("dex_pair_volume_24h_usd"))
    score = 0.0
    risk = 0.0
    signals: list[str] = []
    risks: list[str] = []

    pair_changed = bool(previous_pair and pair and pair != previous_pair)
    if pair_changed:
        score += 30; risk += 35; signals.append("EXACT_PAIR_CHANGED"); risks.append("PAIR_IDENTITY_CHANGE")

    lr, lz = liq.get("ratio_to_baseline"), liq.get("z_score")
    if lr is not None and (lr >= 1.25 or lr <= 0.75):
        score += 15; signals.append(f"LIQUIDITY_BASELINE_RATIO_{lr:.2f}X")
    if lz is not None and abs(lz) >= 2:
        score += 15; signals.append(f"LIQUIDITY_Z_{lz:.2f}")
    if lz is not None and abs(lz) >= 3:
        score += 10; signals.append("LIQUIDITY_Z_ABS_GE_3")

    pr, pz = pv.get("ratio_to_baseline"), pv.get("z_score")
    if pr is not None and pr >= 1.5:
        score += 20; signals.append(f"PAIR_VOLUME_{pr:.2f}X")
    if pr is not None and pr >= 2.0:
        score += 10; signals.append("PAIR_VOLUME_GE_2X")
    if pz is not None and pz >= 2:
        score += 20; signals.append(f"PAIR_VOLUME_Z_{pz:.2f}")
    if pz is not None and pz >= 3:
        score += 10; signals.append("PAIR_VOLUME_Z_GE_3")

    liq_prev = liq.get("change_from_previous_pct")
    if liq_prev is not None and liq_prev <= -25:
        risk += 20; risks.append(f"LIQUIDITY_DROP_{liq_prev:.1f}PCT")
    if liq_prev is not None and liq_prev <= -50:
        risk += 25; risks.append("LIQUIDITY_DROP_GE_50PCT")
    if liq_value is not None and liq_value < 10_000:
        risk += 15; risks.append("LOW_EXACT_PAIR_LIQUIDITY_LT_10K")

    channel = {
        "available": available,
        "verified": available,
        "source": "DEXSCREENER_EXACT_PAIR+SELF_BASELINE_EWMA" if available else "NO_VERIFIED_EXACT_PAIR",
        "score": round(min(100.0, score), 2) if available else 0.0,
        "signals": signals,
        "deviation": {"liquidity": liq, "pair_volume_24h": pv},
        "same_pair_as_previous": True if previous_pair and pair == previous_pair else (False if previous_pair and pair else None),
    }
    return channel, min(100.0, risk), risks


def _load_external(source_generated_at: str) -> dict[str, dict]:
    payload = _load(EXTERNAL, {})
    rows = payload.get("observations") or [] if isinstance(payload, dict) else []
    cutoff = _dt(source_generated_at)
    latest: dict[str, tuple[datetime, dict]] = {}
    for row in rows:
        if not isinstance(row, dict) or str(row.get("network") or "").lower() != NETWORK:
            continue
        address = str(row.get("token_address") or "")
        observed = _dt(row.get("observed_at"))
        if not looks_like_solana_address(address) or observed is None or cutoff is None or observed > cutoff:
            continue
        old = latest.get(address)
        if old is None or observed > old[0]:
            latest[address] = (observed, row)
    return {k: v[1] for k, v in latest.items()}


def _external_channel(name: str, row: dict | None) -> dict:
    item = (row or {}).get(name) if isinstance(row, dict) else None
    if not isinstance(item, dict):
        return {"available": False, "verified": False, "score": 0.0, "source": "NOT_CONNECTED", "signals": []}
    verified = item.get("verified") is True and item.get("contract_match") is True and bool(str(item.get("source") or "").strip())
    score = max(0.0, min(100.0, _n(item.get("anomaly_score"), 0.0) or 0.0)) if verified else 0.0
    signals = [str(x) for x in (item.get("signals") or [])][:20] if verified else []
    return {
        "available": verified,
        "verified": verified,
        "score": round(score, 2),
        "source": str(item.get("source") or "UNVERIFIED") if verified else "UNVERIFIED_NOT_SCORED",
        "signals": signals,
        "observed_at": item.get("observed_at") or (row or {}).get("observed_at"),
    }


def build_profile(coin: dict, token_state: dict | None, external_row: dict | None, observed_at: str) -> tuple[dict, dict]:
    token_state = dict(token_state or {})
    stats = dict(token_state.get("metrics") or {})
    previous_pair = str(token_state.get("pair_address") or "") or None
    market = _market_channel(coin, stats)
    pair, risk, risk_reasons = _liquidity_pair_channel(coin, stats, previous_pair)
    channels = {"market": market, "liquidity_pair": pair}
    for name in EXTERNAL_CHANNELS:
        channels[name] = _external_channel(name, external_row)

    coverage = 0.0
    raw = 0.0
    strong = []
    for name, weight in CHANNEL_WEIGHTS.items():
        ch = channels[name]
        if ch.get("available") is True and ch.get("verified") is True:
            coverage += weight
            raw += weight * (_n(ch.get("score"), 0.0) or 0.0) / 100.0
            if (_n(ch.get("score"), 0.0) or 0.0) >= 55:
                strong.append(name)

    c24 = _n(coin.get("change_24h_pct"), 0.0) or 0.0
    if c24 <= -30:
        risk += 20; risk_reasons.append("PRICE_24H_CRASH_GE_30PCT")
    if c24 >= 50 and (pair.get("deviation") or {}).get("liquidity", {}).get("change_from_previous_pct") is not None:
        if pair["deviation"]["liquidity"]["change_from_previous_pct"] < 0:
            risk += 15; risk_reasons.append("PARABOLIC_PRICE_WITH_FALLING_LIQUIDITY")
    risk = min(100.0, risk)

    normalized = raw / coverage * 100.0 if coverage > 0 else 0.0
    observations_before = int(token_state.get("observations") or 0)
    ext_strong = sum(1 for x in EXTERNAL_CHANNELS if x in strong)
    baseline_ready = observations_before >= MIN_BASELINE_OBSERVATIONS or ext_strong >= 2
    volume_24h_usd = _n(coin.get("volume_24h_usd"), 0.0) or 0.0
    absolute_volume_ready = volume_24h_usd >= MIN_IGNITION_VOLUME_24H_USD

    if risk >= 50:
        status = "RISK_DISTRIBUTION"
    elif baseline_ready and absolute_volume_ready and normalized >= 70 and raw >= 35 and len(strong) >= 2 and risk < 35:
        status = "HYBRID_IGNITION"
    elif normalized >= 55 and raw >= 25 and len(strong) >= 1:
        status = "ABNORMAL_ACTIVITY"
    elif not baseline_ready:
        status = "BASELINE_LEARNING"
    else:
        status = "NORMAL"

    profile = {
        "profile_id": f"solana:{coin.get('token_address')}",
        "network": NETWORK,
        "token_address": coin.get("token_address"),
        "symbol": coin.get("symbol"),
        "name": coin.get("name"),
        "coingecko_id": coin.get("id"),
        "observed_at": observed_at,
        "identity": {
            "network_verified": coin.get("network_verified") is True,
            "solana_only_platform_verified": coin.get("solana_only_platform_verified") is True,
            "exact_pair_verified": coin.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR",
            "dex_pair_address": coin.get("dex_pair_address"),
            "dex_link": coin.get("dex_link"),
            "lookup_keys": [x for x in [coin.get("token_address"), coin.get("id"), coin.get("symbol"), coin.get("name")] if x],
        },
        "status": status,
        "hybrid_score_raw": round(raw, 2),
        "hybrid_score_verified_normalized": round(normalized, 2),
        "evidence_coverage_pct": round(coverage, 2),
        "risk_score": round(risk, 2),
        "risk_reasons": risk_reasons,
        "strong_channels": strong,
        "baseline_observations_before": observations_before,
        "baseline_ready": baseline_ready,
        "promotion_gates": {
            "min_ignition_volume_24h_usd": MIN_IGNITION_VOLUME_24H_USD,
            "volume_24h_usd": round(volume_24h_usd, 2),
            "absolute_volume_ready": absolute_volume_ready,
        },
        "channels": channels,
        "market_context": {
            "price_usd": coin.get("price_usd"),
            "market_cap_usd": coin.get("market_cap_usd"),
            "volume_24h_usd": coin.get("volume_24h_usd"),
            "change_24h_pct": coin.get("change_24h_pct"),
            "change_7d_pct": coin.get("change_7d_pct"),
            "change_30d_pct": coin.get("change_30d_pct"),
            "drawdown_from_ath_pct": coin.get("drawdown_from_ath_pct"),
            "revival_score_verified": coin.get("revival_score_verified"),
        },
    }

    new_stats = dict(stats)
    for metric in METRICS:
        new_stats[metric] = _update_stat(new_stats.get(metric), coin.get(metric))
    new_state = {
        "observations": observations_before + 1,
        "last_observed_at": observed_at,
        "pair_address": coin.get("dex_pair_address") if coin.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR" else previous_pair,
        "metrics": new_stats,
    }
    return profile, new_state


def run() -> dict:
    source = _load(SOURCE, {})
    if (
        source.get("mode") != "RESEARCH_ONLY_REVIVAL_SOLANA_EXPANDED_V6"
        or source.get("network") != NETWORK
        or source.get("production_portfolio_impact") != "NONE"
        or source.get("no_hindsight") is not True
    ):
        raise RuntimeError("HYBRID_SOURCE_TRUTH_CONTRACT_REJECTED")
    generated_at = str(source.get("generated_at") or "")
    if _dt(generated_at) is None:
        raise RuntimeError("HYBRID_SOURCE_TIMESTAMP_INVALID")

    state = _load(STATE, {"version": 1, "tokens": {}})
    last_source = str(state.get("last_source_generated_at") or "")
    if last_source and _dt(last_source) and _dt(generated_at) < _dt(last_source):
        raise RuntimeError("HYBRID_NO_HINDSIGHT_SOURCE_REGRESSION")
    if last_source == generated_at and LATEST.exists():
        return _load(LATEST, {})

    external = _load_external(generated_at)
    old_tokens = state.get("tokens") or {}
    new_tokens = dict(old_tokens)
    profiles = []
    for coin in source.get("coins") or []:
        address = str(coin.get("token_address") or "")
        if not looks_like_solana_address(address):
            continue
        profile, token_state = build_profile(coin, old_tokens.get(address), external.get(address), generated_at)
        profiles.append(profile)
        new_tokens[address] = token_state

    profiles.sort(key=lambda x: (x["status"] == "HYBRID_IGNITION", x["hybrid_score_raw"], x["hybrid_score_verified_normalized"]), reverse=True)
    counts = {
        "profiles": len(profiles),
        "hybrid_ignition": sum(x["status"] == "HYBRID_IGNITION" for x in profiles),
        "abnormal_activity": sum(x["status"] == "ABNORMAL_ACTIVITY" for x in profiles),
        "risk_distribution": sum(x["status"] == "RISK_DISTRIBUTION" for x in profiles),
        "baseline_learning": sum(x["status"] == "BASELINE_LEARNING" for x in profiles),
        "normal": sum(x["status"] == "NORMAL" for x in profiles),
        "external_evidence_tokens": sum(any((x["channels"][c] or {}).get("available") for c in EXTERNAL_CHANNELS) for x in profiles),
    }
    payload = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "network": NETWORK,
        "generated_at": now_iso(),
        "source_generated_at": generated_at,
        "source": "revival-1000-latest.json + exact-address verified external evidence when available",
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "truth_rules": [
            "each profile is keyed by exact Solana mint address",
            "self baseline uses only observations collected before the current snapshot",
            "future-dated external evidence is rejected",
            "holders/wallet/social/news data is scored only when contract_match=true and verified=true",
            "missing evidence gets zero weight and is never invented",
            "HYBRID_IGNITION requires at least $10,000 absolute 24h volume; lower-volume tokens remain visible for research",
        ],
        "channel_weights": CHANNEL_WEIGHTS,
        "baseline": {"method": "EWMA", "alpha": ALPHA, "minimum_previous_observations": MIN_BASELINE_OBSERVATIONS},
        "promotion_gates": {"min_ignition_volume_24h_usd": MIN_IGNITION_VOLUME_24H_USD},
        "counts": counts,
        "profiles": profiles,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    state_payload = {
        "version": 1,
        "contract": CONTRACT,
        "last_source_generated_at": generated_at,
        "updated_at": payload["generated_at"],
        "tokens": new_tokens,
    }
    STATE.write_text(json.dumps(state_payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    p = run()
    print("HYBRID_TOKEN_PROFILE_OK", p.get("counts"))