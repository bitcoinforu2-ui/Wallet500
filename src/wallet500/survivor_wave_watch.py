from __future__ import annotations

import json
import math
import os
import urllib.parse
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


def pct_change(current, baseline):
    current = f(current)
    baseline = f(baseline)
    if current is None or baseline is None or baseline <= 0:
        return None
    return ((current / baseline) - 1.0) * 100.0


def http_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def telegram_send(text: str) -> tuple[bool, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "TELEGRAM_SECRETS_MISSING"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"User-Agent": "Wallet500/1.0", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            body = json.loads(r.read().decode("utf-8"))
        return bool(body.get("ok")), "OK" if body.get("ok") else str(body.get("description") or "TELEGRAM_API_ERROR")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def pair_snapshot(chain: str, pair: str):
    chain_id = {"bsc": "bsc", "solana": "solana", "ethereum": "ethereum"}.get(norm(chain), norm(chain))
    try:
        d = http_json(f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pair}")
        rows = d.get("pairs") or []
        exact = next((x for x in rows if norm(x.get("pairAddress")) == norm(pair)), None)
        if not exact:
            return None, "PAIR_NOT_RETURNED"
        return exact, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def holder_index():
    d = load(DATA / "revival-holder-latest.json", {})
    rows = d.get("coins") or d.get("tokens") or d.get("rows") or d.get("items") or []
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
        if isinstance(x, dict):
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
        if isinstance(x, dict):
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


def dna_match(turnover, buy_ratio, wave_status, reasons):
    if turnover is not None and buy_ratio is not None and turnover >= 0.75 and buy_ratio >= 1.25:
        return "HIGH", ["TURNOVER>=0.75", "BUY_SELL_RATIO>=1.25"]
    medium = False
    hits = []
    if turnover is not None and turnover >= 0.25:
        medium = True; hits.append("TURNOVER>=0.25")
    if buy_ratio is not None and buy_ratio >= 1.25:
        medium = True; hits.append("BUY_SELL_RATIO>=1.25")
    if medium and wave_status in {"EARLY_REACCELERATION", "WAVE_BUILDING"} and len(reasons) >= 2:
        return "MEDIUM", hits
    return "LOW", hits


def classify_dna_event(previous_level: str | None, current_level: str | None, had_prior_alert: bool) -> str:
    previous = str(previous_level or "LOW").upper()
    current = str(current_level or "LOW").upper()
    if not had_prior_alert:
        return "FIRST_DNA_MATCH"
    if previous == "LOW" and current in {"MEDIUM", "HIGH"}:
        return "DNA_REENTRY_REACCELERATION"
    if previous == "MEDIUM" and current == "HIGH":
        return "DNA_UPGRADE_MEDIUM_TO_HIGH"
    if previous != current:
        return "DNA_UPGRADE"
    return "DNA_REACCELERATION"


def dna_event_label(event_type: str, previous_level: str | None, current_level: str | None) -> str:
    previous = str(previous_level or "LOW").upper()
    current = str(current_level or "LOW").upper()
    labels = {
        "FIRST_DNA_MATCH": "FIRST DNA MATCH",
        "DNA_REENTRY_REACCELERATION": "DNA RE-ENTRY / REACCELERATION",
        "DNA_UPGRADE_MEDIUM_TO_HIGH": "DNA UPGRADE MEDIUM → HIGH",
        "DNA_REACCELERATION": "DNA REACCELERATION",
    }
    return labels.get(event_type, f"DNA UPGRADE {previous} → {current}")


def _fmt_price(value) -> str:
    value = f(value)
    return f"${value:.10g}" if value is not None else "n/a"


def format_alert(row: dict, previous_level: str | None) -> str:
    current_level = str(row.get("winner_dna_match") or "LOW").upper()
    event_type = str(row.get("dna_event_type") or "FIRST_DNA_MATCH")
    event_label = dna_event_label(event_type, previous_level, current_level)
    discovery_price = f(row.get("discovery_price_usd"))
    first_alert_price = f(row.get("first_dna_alert_price_usd") or row.get("alert_price_usd"))
    current_price = f(row.get("price_usd"))
    since_discovery = pct_change(current_price, discovery_price)
    since_first_alert = pct_change(current_price, first_alert_price)
    discovery_line = f"Discovery: {_fmt_price(discovery_price)}\n"
    current_line = f"Current: {_fmt_price(current_price)}\n"
    discovery_move_line = f"Since discovery: {since_discovery:+.2f}%\n" if since_discovery is not None else "Since discovery: n/a\n"
    first_alert_move_line = f"Since first DNA alert: {since_first_alert:+.2f}%\n" if since_first_alert is not None else "Since first DNA alert: n/a\n"
    holders_delta = row.get("holder_delta_since_prior_hourly_snapshot")
    holders_line = f"Holders Δ: {holders_delta}" if holders_delta is not None else "Holders Δ: n/a (no timestamp-safe comparison)"
    return (
        "🚨 Wallet500 WINNER DNA ALERT\n"
        f"Event: {event_label}\n"
        f"DNA transition: {str(previous_level or 'LOW').upper()} → {current_level}\n"
        f"DNA alert #: {int(row.get('dna_alert_count') or 1)}\n"
        f"Chain: {row.get('chain')}\n"
        f"Token: {row.get('token')}\n"
        f"Pair: {row.get('pair_address')}\n"
        f"DNA: {current_level}\n"
        f"Wave: {row.get('wave_status')} | score {row.get('wave_score')}\n"
        f"{discovery_line}"
        f"First DNA alert: {_fmt_price(first_alert_price)}\n"
        f"First DNA alert time: {row.get('first_dna_alerted_at') or row.get('alerted_at') or 'n/a'}\n"
        f"{current_line}"
        f"{discovery_move_line}"
        f"{first_alert_move_line}"
        f"Discovered at: {row.get('discovered_at') or 'n/a'}\n"
        f"Liquidity: ${float(row.get('liquidity_usd') or 0):,.0f}\n"
        f"Vol 1H: ${float(row.get('volume_h1_usd') or 0):,.0f}\n"
        f"Turnover 1H: {row.get('turnover_h1')}\n"
        f"Buy/Sell 1H: {row.get('buy_sell_ratio_h1')} (transaction count ratio)\n"
        f"{holders_line}\n"
        f"DNA hits: {', '.join(row.get('winner_dna_hits') or []) or 'n/a'}\n"
        f"Reasons: {', '.join(row.get('wave_reasons') or []) or 'n/a'}\n"
        "Research alert only — no automatic BUY."
    )


def main():
    study = load(STUDY, {})
    previous_output = load(OUT, {})
    prev = load(STATE, {"tokens": {}})
    prev_tokens = prev.get("tokens") or {}
    holders = holder_index()
    organic = organic_index()
    kols = kol_index()
    listings = listing_index()
    observed_at = now_iso()

    winner_rows = [x for x in study.get("rows") or [] if isinstance(x, dict) and x.get("label") == "WINNER"]
    results = []
    state_tokens = dict(prev_tokens)
    errors = []
    telegram_events = []

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
        token_key = norm(token)
        prev_row = prev_tokens.get(token_key) or {}
        prev_count = prev_row.get("holders")
        holder_delta = holder_count - prev_count if holder_count is not None and prev_count is not None else None
        current_price = f(snap.get("priceUsd"))
        is_first_observation = token_key not in prev_tokens
        discovery_price = current_price if is_first_observation else f(prev_row.get("discovery_price_usd"))
        discovered_at = observed_at if is_first_observation else prev_row.get("discovered_at")

        legacy_first_alert_price = f(prev_row.get("alert_price_usd"))
        legacy_first_alerted_at = prev_row.get("alerted_at")
        first_alert_price = f(prev_row.get("first_dna_alert_price_usd"), legacy_first_alert_price)
        first_alerted_at = prev_row.get("first_dna_alerted_at") or legacy_first_alerted_at
        last_alert_price = f(prev_row.get("last_dna_alert_price_usd"), first_alert_price)
        last_alerted_at = prev_row.get("last_dna_alerted_at") or first_alerted_at
        prior_alert_count = int(prev_row.get("dna_alert_count") or (1 if first_alert_price is not None or first_alerted_at else 0))
        had_prior_alert = prior_alert_count > 0

        org = organic.get(token_key, {})
        org_score = f(org.get("organic_acceleration_score"))
        kol = kols.get(token_key, {})
        kol_groups = f(kol.get("independent_wallet_groups") or kol.get("independent_sources"))
        score, status, reasons, turnover, buy_ratio = wave_state(
            f(changes.get("h1")), f(changes.get("h6")), f(volume.get("h1")), liq,
            f(h1_tx.get("buys")), f(h1_tx.get("sells")), holder_delta, org_score, kol_groups,
        )
        dna_level, dna_hits = dna_match(turnover, buy_ratio, status, reasons)
        previous_level = str(prev_row.get("winner_dna_match") or "LOW").upper()
        should_alert = dna_level == "HIGH" and previous_level != "HIGH"
        if dna_level == "MEDIUM" and previous_level == "LOW" and status in {"EARLY_REACCELERATION", "WAVE_BUILDING"} and len(reasons) >= 2:
            should_alert = True

        event_type = None
        event_price = None
        event_alerted_at = None
        alert_count = prior_alert_count
        if should_alert:
            event_type = classify_dna_event(previous_level, dna_level, had_prior_alert)
            event_price = current_price
            event_alerted_at = observed_at
            alert_count = prior_alert_count + 1
            if not had_prior_alert:
                first_alert_price = current_price
                first_alerted_at = observed_at
            last_alert_price = current_price
            last_alerted_at = observed_at

        row = {
            "chain": chain,
            "token": token,
            "pair_address": pair,
            "source_winner_t0": w.get("t0"),
            "source_return_24h_pct": w.get("return_24h_pct"),
            "survival": "EXACT_PAIR_LIQUIDITY_SURVIVED",
            "price_usd": current_price,
            "current_price_usd": current_price,
            "discovery_price_usd": discovery_price,
            "discovered_at": discovered_at,
            "alert_price_usd": first_alert_price,
            "alerted_at": first_alerted_at,
            "first_dna_alert_price_usd": first_alert_price,
            "first_dna_alerted_at": first_alerted_at,
            "last_dna_alert_price_usd": last_alert_price,
            "last_dna_alerted_at": last_alerted_at,
            "dna_alert_count": alert_count,
            "dna_event_type": event_type,
            "since_discovery_pct": round(pct_change(current_price, discovery_price), 6) if pct_change(current_price, discovery_price) is not None else None,
            "since_first_dna_alert_pct": round(pct_change(current_price, first_alert_price), 6) if pct_change(current_price, first_alert_price) is not None else None,
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
            "listing_evidence_count": len(listings.get(token_key, [])),
            "wave_score": score,
            "wave_status": status,
            "wave_reasons": reasons,
            "winner_dna_match": dna_level,
            "winner_dna_hits": dna_hits,
            "dex_url": snap.get("url"),
        }

        if should_alert:
            ok, telegram_status = telegram_send(format_alert(row, previous_level))
            telegram_events.append({
                "token": token,
                "dna": dna_level,
                "previous_dna": previous_level,
                "event_type": event_type,
                "sent": ok,
                "status": telegram_status,
                "event_price_usd": event_price,
                "event_alerted_at": event_alerted_at,
                "first_dna_alert_price_usd": first_alert_price,
                "first_dna_alerted_at": first_alerted_at,
                "dna_alert_count": alert_count,
            })

        results.append(row)
        state_tokens[token_key] = {
            "chain": chain,
            "pair_address": pair,
            "holders": holder_count,
            "price_usd": current_price,
            "current_price_usd": current_price,
            "liquidity_usd": liq,
            "winner_dna_match": dna_level,
            "wave_status": status,
            "discovery_price_usd": discovery_price,
            "discovered_at": discovered_at,
            "alert_price_usd": first_alert_price,
            "alerted_at": first_alerted_at,
            "first_dna_alert_price_usd": first_alert_price,
            "first_dna_alerted_at": first_alerted_at,
            "last_dna_alert_price_usd": last_alert_price,
            "last_dna_alerted_at": last_alerted_at,
            "dna_alert_count": alert_count,
            "last_dna_alert_event_type": event_type or prev_row.get("last_dna_alert_event_type"),
            "last_seen_at": observed_at,
        }

    results.sort(key=lambda x: (x.get("wave_score") or 0, x.get("source_return_24h_pct") or 0), reverse=True)
    generated = now_iso()
    previous_rows = previous_output.get("tokens") or previous_output.get("last_known_tokens") or []
    last_known_tokens = []
    if results:
        last_known_tokens = [dict(results[0])]
    elif previous_rows:
        stale = dict(previous_rows[0])
        stale["stale_snapshot"] = True
        stale["stale_reason"] = "NO_CURRENT_SURVIVOR_SIGNAL"
        stale["stale_since"] = generated
        last_known_tokens = [stale]

    payload = {
        "version": 3,
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
        "dna_high_n": sum(1 for x in results if x.get("winner_dna_match") == "HIGH"),
        "dna_medium_n": sum(1 for x in results if x.get("winner_dna_match") == "MEDIUM"),
        "telegram_events": telegram_events,
        "discovery_price_contract": {
            "immutable": True,
            "definition": "exact-pair price at first timestamp-safe observation by Survivor Wave Watch",
            "legacy_missing_policy": "NULL_NEVER_INFERRED",
            "current_price_definition": "latest exact-pair DexScreener snapshot",
        },
        "alert_semantics_contract": {
            "version": 2,
            "first_dna_match_requires_no_prior_dna_alert": True,
            "low_to_medium_or_high_after_prior_alert_is_reentry": True,
            "first_dna_alert_price_immutable": True,
            "last_dna_alert_snapshot_tracked": True,
            "dna_alert_count_tracked": True,
            "buy_sell_ratio_definition": "TRANSACTION_COUNT_RATIO_NOT_CAPITAL_FLOW",
        },
        "note": "Research-only Winner DNA alerting. Discovery price and first DNA alert price are immutable timestamp-safe snapshots. Repeat DNA events are labeled as re-entry/reacceleration or upgrade rather than FIRST DNA MATCH.",
        "tokens": results,
        "last_known_tokens": last_known_tokens,
        "errors": errors[:50],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    STATE.write_text(json.dumps({"generated_at": generated, "tokens": state_tokens}, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"survivor_n": payload["survivor_n"], "wave_building_n": payload["wave_building_n"], "dna_high_n": payload["dna_high_n"], "dna_medium_n": payload["dna_medium_n"], "telegram_events": telegram_events, "errors": len(errors)}, indent=2))


if __name__ == "__main__":
    main()
