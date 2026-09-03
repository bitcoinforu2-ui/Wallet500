from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
STUDY = DATA / "winner-separator-study.json"
OUT = DATA / "survivor-wave-watch.json"
STATE = DATA / "survivor-wave-watch-state.json"
LIQ_FLOOR = 50_000.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def f(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def norm(v):
    return str(v or "").lower()


def http_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pair_snapshot(chain: str, pair: str):
    chain_id = {"bsc": "bsc", "solana": "solana", "ethereum": "ethereum"}.get(norm(chain), norm(chain))
    try:
        d = http_json(f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pair}")
        rows = d.get("pairs") or []
        exact = next((x for x in rows if norm(x.get("pairAddress")) == norm(pair)), None)
        if not exact:
            return None, "PAIR_NOT_RETURNED"
        return exact, None
    except Exception as e:  # network evidence gap must never be guessed
        return None, f"{type(e).__name__}: {e}"


def holder_index():
    # Reuse Wallet500's own point-in-time holder tracker; do not mix vendors.
    d = load(DATA / "revival-holder-latest.json", {})
    rows = d.get("tokens") or d.get("rows") or d.get("items") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    out = {}
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, dict):
            continue
        token = x.get("token_address") or x.get("token") or x.get("mint") or x.get("address")
        if not token:
            continue
        holders = x.get("holders")
        if holders is None:
            holders = x.get("holder_count")
        if holders is None:
            holders = x.get("current_holders")
        out[norm(token)] = {
            "holders": int(holders) if f(holders) is not None else None,
            "source_generated_at": d.get("generated_at") or d.get("updated_at"),
        }
    return out


def organic_index():
    d = load(DATA / "social-organic-acceleration.json", {})
    out = {}
    for x in d.get("tokens") or []:
        if not isinstance(x, dict):
            continue
        token = x.get("contract") or x.get("token_address") or x.get("mint")
        if token:
            out[norm(token)] = x
    return out


def kol_index():
    d = load(DATA / "kol-revival-convergence-summary.json", {})
    out = {}
    for x in d.get("active") or []:
        if isinstance(x, dict) and x.get("mint"):
            out[norm(x.get("mint"))] = x
    return out


def listing_index():
    d = load(DATA / "global-listing-radar.json", {})
    out = {}
    rows = d.get("records") or d.get("items") or d.get("tokens") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, dict):
            continue
        token = x.get("token") or x.get("token_address") or x.get("mint") or x.get("address")
        if token:
            out.setdefault(norm(token), []).append(x)
    return out


def wave_state(price_change_h1, price_change_h6, vol_h1, liq, buys_h1, sells_h1, holder_delta, organic_score, kol_groups):
    turnover = (vol_h1 / liq) if liq and vol_h1 is not None else None
    buy_ratio = (buys_h1 / max(1.0, sells_h1)) if buys_h1 is not None and sells_h1 is not None else None
    score = 0
    reasons = []
    if turnover is not None and turnover >= 0.25:
        score += 20; reasons.append("H1_TURNOVER")
    if turnover is not None and turnover >= 0.75:
        score += 15; reasons.append("H1_TURNOVER_STRONG")
    if buy_ratio is not None and buy_ratio >= 1.25:
        score += 15; reasons.append("BUY_PRESSURE")
    if price_change_h1 is not None and price_change_h1 >= 5:
        score += 10; reasons.append("PRICE_H1")
    if price_change_h6 is not None and price_change_h6 >= 12:
        score += 10; reasons.append("PRICE_H6")
    if holder_delta is not None and holder_delta > 0:
        score += 10; reasons.append("HOLDER_GROWTH")
    if organic_score is not None and organic_score >= 60:
        score += 10; reasons.append("ORGANIC_SOCIAL")
    if kol_groups is not None and kol_groups >= 2:
        score += 10; reasons.append("KOL_CONVERGENCE")
    status = "WAVE_BUILDING" if score >= 60 else "EARLY_REACCELERATION" if score >= 40 else "SURVIVOR_WATCH"
    return min(score, 100), status, reasons, turnover, buy_ratio


def main():
    study = load(STUDY, {})
    prev = load(STATE, {"tokens": {}})
    prev_tokens = prev.get("tokens") or {}
    holders = holder_index()
    organic = organic_index()
    kols = kol_index()
    listings = listing_index()

    winner_rows = [x for x in study.get("rows") or [] if isinstance(x, dict) and x.get("label") == "WINNER"]
    results = []
    state_tokens = {}
    errors = []

    for w in winner_rows:
        token = w.get("token")
        pair = w.get("pair_address")
        chain = w.get("chain")
        if not token or not pair or not chain:
            continue
        snap, err = pair_snapshot(chain, pair)
        if err:
            errors.append({"token": token, "pair": pair, "error": err})
            continue
        liq = f((snap.get("liquidity") or {}).get("usd"), 0.0) or 0.0
        if liq < LIQ_FLOOR:
            continue

        txns = snap.get("txns") or {}
        volume = snap.get("volume") or {}
        changes = snap.get("priceChange") or {}
        h1_tx = txns.get("h1") or {}
        h = holders.get(norm(token), {})
        holder_count = h.get("holders")
        prev_count = (prev_tokens.get(norm(token)) or {}).get("holders")
        holder_delta = holder_count - prev_count if holder_count is not None and prev_count is not None else None
        org = organic.get(norm(token), {})
        org_score = f(org.get("organic_acceleration_score"))
        kol = kols.get(norm(token), {})
        kol_groups = f(kol.get("independent_wallet_groups") or kol.get("independent_sources"))
        score, status, reasons, turnover, buy_ratio = wave_state(
            f(changes.get("h1")), f(changes.get("h6")), f(volume.get("h1")), liq,
            f(h1_tx.get("buys")), f(h1_tx.get("sells")), holder_delta, org_score, kol_groups,
        )
        row = {
            "chain": chain,
            "token": token,
            "pair_address": pair,
            "source_winner_t0": w.get("t0"),
            "source_return_24h_pct": w.get("return_24h_pct"),
            "survival": "EXACT_PAIR_LIQUIDITY_SURVIVED",
            "price_usd": f(snap.get("priceUsd")),
            "liquidity_usd": liq,
            "market_cap_usd": f(snap.get("marketCap")) or f(snap.get("fdv")),
            "volume_h1_usd": f(volume.get("h1")),
            "volume_h24_usd": f(volume.get("h24")),
            "price_change_h1_pct": f(changes.get("h1")),
            "price_change_h6_pct": f(changes.get("h6")),
            "price_change_h24_pct": f(changes.get("h24")),
            "buys_h1": int(f(h1_tx.get("buys"), 0) or 0),
            "sells_h1": int(f(h1_tx.get("sells"), 0) or 0),
            "turnover_h1": round(turnover, 6) if turnover is not None else None,
            "buy_sell_ratio_h1": round(buy_ratio, 4) if buy_ratio is not None else None,
            "holders": holder_count,
            "holder_delta_since_prior_hourly_snapshot": holder_delta,
            "holder_source_generated_at": h.get("source_generated_at"),
            "organic_social_status": org.get("status") or "NO_TIMESTAMP_SAFE_SIGNAL",
            "organic_acceleration_score": org_score,
            "kol_independent_groups": kol_groups,
            "listing_evidence_count": len(listings.get(norm(token), [])),
            "wave_score": score,
            "wave_status": status,
            "wave_reasons": reasons,
            "dex_url": snap.get("url"),
        }
        results.append(row)
        state_tokens[norm(token)] = {"holders": holder_count, "price_usd": row["price_usd"], "liquidity_usd": liq}

    results.sort(key=lambda x: (x.get("wave_score") or 0, x.get("source_return_24h_pct") or 0), reverse=True)
    generated = now_iso()
    payload = {
        "version": 1,
        "generated_at": generated,
        "mode": "HOURLY_WINNER_SURVIVOR_WAVE_WATCH_V1",
        "research_only": True,
        "automatic_buy": False,
        "exact_pair_only": True,
        "liquidity_survival_floor_usd": LIQ_FLOOR,
        "source_method": study.get("method"),
        "source_winner_n": len(winner_rows),
        "survivor_n": len(results),
        "wave_building_n": sum(1 for x in results if x.get("wave_status") == "WAVE_BUILDING"),
        "note": "Survivor means the same exact pair is still retrievable with >=$50K liquidity now. Holder/social/KOL/listing fields are included only when timestamp-safe Wallet500 sources exist; missing evidence is never imputed.",
        "tokens": results,
        "errors": errors[:50],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    STATE.write_text(json.dumps({"generated_at": generated, "tokens": state_tokens}, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"survivor_n": payload["survivor_n"], "wave_building_n": payload["wave_building_n"], "errors": len(errors)}, indent=2))


if __name__ == "__main__":
    main()
