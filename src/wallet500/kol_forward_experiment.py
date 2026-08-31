from __future__ import annotations

import hashlib
import html
import json
import re
import statistics
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .market_data import snapshot

DATA = Path("data")
CONFIG = Path("experiments/kol-forward-v1.json")
LEDGER = DATA / "kol-forward-ledger.json"
SUMMARY = DATA / "kol-forward-summary.json"
SOL_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")
HORIZONS = (5, 15, 30, 60, 240, 1440)
UPDATE_WORDS = ("from our call", "from the call", "entry mc", "just hit 2x", "just hit 3x", "just hit 4x", "just hit 5x", "moonbag territory")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500-KOLForward/1.0", "Accept": "text/html,application/json,text/plain,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _plain(raw_html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(text)).strip()


def _template_hash(text: str) -> str:
    s = text.lower()
    s = SOL_RE.sub("<ca>", s)
    s = re.sub(r"https?://\S+", "<url>", s)
    s = re.sub(r"\$?\d+(?:[.,]\d+)?\s*[kmbx%]?", "<n>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]


def _is_original_call(text: str) -> bool:
    low = text.lower()
    if any(x in low for x in UPDATE_WORDS):
        return False
    return bool(re.search(r"\bmc\s*:", low) or re.search(r"\bmarket\s*cap\s*:", low) or re.search(r"\bca\s*:", low))


def _source_numbers(text: str) -> dict:
    def amount(label: str):
        m = re.search(label + r"\s*[:=]?\s*\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([kmb])?", text, flags=re.I)
        if not m:
            return None
        value = float(m.group(1))
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1.0)
        return round(value * mult, 6)

    return {"source_stated_market_cap_usd": amount(r"(?:\bMC\b|market\s*cap)"), "source_stated_liquidity_usd": amount(r"(?:\bLiq\b|liquidity)")}


def _telegram_events(source: dict, errors: list[dict]) -> list[dict]:
    channel = str(source.get("channel") or "").strip()
    if not channel:
        return []
    try:
        raw = _get_text(str(source["url"]))
    except Exception as exc:
        errors.append({"source": source.get("id"), "stage": "FETCH", "error": f"{type(exc).__name__}: {exc}"[:300]})
        return []
    marker = re.compile(rf'data-post="{re.escape(channel)}/(\d+)"')
    matches = list(marker.finditer(raw))
    out = []
    for idx, match in enumerate(matches):
        chunk = raw[match.start() : matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)]
        tm = re.search(r'<time[^>]+datetime="([^"]+)"', chunk, flags=re.I)
        if not tm:
            continue
        text = _plain(chunk)
        if not _is_original_call(text):
            continue
        tokens = SOL_RE.findall(text)
        if not tokens:
            continue
        nums = _source_numbers(text)
        for token in dict.fromkeys(tokens):
            out.append(
                {
                    "source_id": source.get("id"),
                    "source_name": source.get("name"),
                    "source_kind": source.get("kind"),
                    "source_event_id": match.group(1),
                    "source_url": f"https://t.me/{channel}/{match.group(1)}",
                    "published_at": tm.group(1),
                    "chain": "solana",
                    "token": token,
                    "text": text[:2500],
                    "template_hash": _template_hash(text),
                    **nums,
                }
            )
    return out


def _jsonl_events(source: dict, errors: list[dict]) -> list[dict]:
    try:
        raw = _get_text(str(source["url"]))
    except Exception as exc:
        errors.append({"source": source.get("id"), "stage": "FETCH", "error": f"{type(exc).__name__}: {exc}"[:300]})
        return []
    out = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict) or not row.get("mint"):
            continue
        published = row.get("utc") or row.get("t")
        d = _dt(published)
        if not d:
            continue
        token = str(row["mint"]).strip()
        text = f"{row.get('sym') or ''} {token} mc:{row.get('mc') or ''}"
        out.append(
            {
                "source_id": source.get("id"),
                "source_name": source.get("name"),
                "source_kind": source.get("kind"),
                "source_event_id": str(row.get("tg") or row.get("t") or token),
                "source_url": str(source.get("url")),
                "published_at": d.isoformat(),
                "chain": "solana",
                "token": token,
                "text": text[:2500],
                "template_hash": _template_hash(text),
                "source_stated_market_cap_usd": row.get("mc"),
                "source_stated_liquidity_usd": None,
                "source_dataset_peak_multiple": row.get("peak"),
                "source_dataset_peak_is_not_used_for_forward_scoring": True,
            }
        )
    return out


def _collect(config: dict, errors: list[dict]) -> list[dict]:
    rows = []
    for source in config.get("sources") or []:
        kind = source.get("kind")
        if kind == "telegram_public":
            rows.extend(_telegram_events(source, errors))
        elif kind == "jsonl_public":
            rows.extend(_jsonl_events(source, errors))
    return rows


def _norm_token(chain: str, token: str) -> str:
    return token.lower() if chain in {"ethereum", "bsc"} else token


def _qualified_map() -> dict[tuple[str, str], dict]:
    rows = _load(DATA / "active-qualified-candidates.json", [])
    out = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("chain") or not row.get("token"):
            continue
        chain = str(row["chain"]).lower()
        out[(chain, _norm_token(chain, str(row["token"])))] = row
    return out


def _safe_snapshot(chain: str, token: str, pair: str | None, errors: list[dict], stage: str) -> dict | None:
    try:
        return snapshot(chain, token, pair)
    except Exception as exc:
        errors.append({"stage": stage, "token": token, "error": f"{type(exc).__name__}: {exc}"[:300]})
        return None


def _compact_market(s: dict | None) -> dict | None:
    if not s:
        return None
    return {k: s.get(k) for k in ("pair_address", "dex", "price_usd", "liquidity_usd", "market_cap", "fdv", "volume_m5", "volume_h1", "buys_h1", "sells_h1", "price_change_m5", "price_change_h1", "pair_created_at")}


def _coordination(events: list[dict]) -> None:
    templates: dict[str, set[str]] = {}
    tokens: dict[str, set[str]] = {}
    for event in events:
        templates.setdefault(str(event.get("template_hash") or ""), set()).add(str(event.get("source_id") or ""))
        tokens.setdefault(str(event.get("token") or ""), set()).add(str(event.get("source_id") or ""))
    for event in events:
        tsize = len(templates.get(str(event.get("template_hash") or ""), set()))
        consensus = len(tokens.get(str(event.get("token") or ""), set()))
        event["coordination_template_source_count"] = tsize
        event["coordinated_template"] = tsize > 1
        event["source_consensus_count"] = consensus


def _mark_entry(entry: dict, t: datetime, errors: list[dict]) -> None:
    snap = _safe_snapshot(str(entry.get("chain") or "solana"), str(entry.get("token") or ""), str(entry.get("pair_address") or ""), errors, "MARK_EXACT_PAIR")
    if not snap:
        entry["current_status"] = "UNRESOLVED"
        entry["last_mark_at"] = t.isoformat()
        return
    price = float(snap.get("price_usd") or 0)
    liq = float(snap.get("liquidity_usd") or 0)
    entry_price = float(entry.get("entry_price_usd") or 0)
    if entry_price <= 0 or price <= 0:
        ret = -100.0
        value = 0.0
    else:
        ret = (price / entry_price - 1.0) * 100.0
        value = float(entry.get("quantity") or 0) * price
    entry["current_price_usd"] = price
    entry["current_liquidity_usd"] = liq
    entry["current_value_usd"] = round(value, 10)
    entry["current_return_pct"] = round(ret, 6)
    entry["peak_return_pct"] = round(max(float(entry.get("peak_return_pct") or ret), ret), 6)
    entry["max_drawdown_pct"] = round(min(float(entry.get("max_drawdown_pct") or ret), ret), 6)
    entry["last_mark_at"] = t.isoformat()
    if liq < 50000 or price <= 0:
        entry["ever_failed_survival"] = True
    if entry.get("ever_failed_survival"):
        entry["current_status"] = "FAILED_SURVIVAL"
    else:
        entry["current_status"] = "LIVE"
    started = _dt(entry.get("entry_at"))
    elapsed = ((t - started).total_seconds() / 60.0) if started else 0.0
    marks = entry.setdefault("horizon_marks", {})
    for horizon in HORIZONS:
        key = f"{horizon}m"
        if key not in marks and elapsed >= horizon:
            marks[key] = {
                "marked_at": t.isoformat(),
                "elapsed_minutes": round(elapsed, 2),
                "price_usd": price,
                "liquidity_usd": liq,
                "return_pct": round(ret, 6),
                "survived_50k": liq >= 50000 and price > 0,
            }


def _source_stats(config: dict, events: list[dict], entries: list[dict]) -> list[dict]:
    required = int(config.get("minimum_forward_entries_before_source_rank") or 30)
    output = []
    for source in config.get("sources") or []:
        sid = source.get("id")
        ev = [x for x in events if x.get("source_id") == sid]
        en = [x for x in entries if x.get("source_id") == sid]
        returns = [float(x.get("current_return_pct") or 0) for x in en]
        survivors = [x for x in en if not x.get("ever_failed_survival")]
        two_x = [x for x in en if float(x.get("peak_return_pct") or 0) >= 100]
        five_x = [x for x in en if float(x.get("peak_return_pct") or 0) >= 400]
        output.append(
            {
                "source_id": sid,
                "name": source.get("name"),
                "source_status": source.get("status"),
                "forward_calls": len(ev),
                "wallet500_qualified_entries": len(en),
                "qualification_rate_pct": round(len(en) / len(ev) * 100.0, 2) if ev else 0.0,
                "median_current_return_pct": round(statistics.median(returns), 4) if returns else None,
                "current_positive_rate_pct": round(sum(x > 0 for x in returns) / len(returns) * 100.0, 2) if returns else None,
                "ever_2x_rate_pct": round(len(two_x) / len(en) * 100.0, 2) if en else None,
                "ever_5x_rate_pct": round(len(five_x) / len(en) * 100.0, 2) if en else None,
                "survival_rate_pct": round(len(survivors) / len(en) * 100.0, 2) if en else None,
                "rank_state": "ELIGIBLE_FOR_FORWARD_RANK" if len(en) >= required else f"PROBATION_{len(en)}/{required}",
            }
        )
    output.sort(key=lambda x: (x["rank_state"].startswith("ELIGIBLE"), x["wallet500_qualified_entries"], x["forward_calls"]), reverse=True)
    return output


def run() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    config = _load(CONFIG, {})
    t = _now()
    state = _load(LEDGER, {})
    if not state:
        state = {
            "version": "KOL_FORWARD_V1",
            "mode": "PROSPECTIVE_ONLY_NO_BACKFILL",
            "started_at": t.isoformat(),
            "position_size_usd": float(config.get("position_size_usd") or 1.0),
            "events": [],
            "entries": [],
            "truth_contract": config.get("truth_contract") or {},
        }
    start = _dt(state.get("started_at")) or t
    errors: list[dict] = []
    fetched = _collect(config, errors)
    events = state.setdefault("events", [])
    entries = state.setdefault("entries", [])
    known_event = {str(x.get("event_key")) for x in events if isinstance(x, dict)}
    known_source_token = {(str(x.get("source_id")), str(x.get("token"))) for x in events if isinstance(x, dict)}
    qmap = _qualified_map()
    new_events = 0

    for raw in sorted(fetched, key=lambda x: str(x.get("published_at") or "")):
        published = _dt(raw.get("published_at"))
        if not published or published < start:
            continue
        source_token = (str(raw.get("source_id")), str(raw.get("token")))
        if source_token in known_source_token:
            continue
        event_key = f"{raw.get('source_id')}:{raw.get('source_event_id')}:{raw.get('token')}"
        if event_key in known_event:
            continue
        raw["event_key"] = event_key
        raw["wallet500_first_ingested_at"] = t.isoformat()
        raw["forward_only_verified"] = True
        snap = _safe_snapshot(str(raw.get("chain") or "solana"), str(raw.get("token") or ""), None, errors, "FIRST_INGEST_MARKET")
        raw["market_at_wallet500_ingest"] = _compact_market(snap)
        q = qmap.get((str(raw.get("chain") or "solana").lower(), _norm_token(str(raw.get("chain") or "solana").lower(), str(raw.get("token") or ""))))
        raw["wallet500_qualified_at_first_ingest"] = bool(q)
        raw["qualification_state"] = "QUALIFIED_ENTRY_READY" if q else "WAITING_WALLET500_GATE"
        events.append(raw)
        known_event.add(event_key)
        known_source_token.add(source_token)
        new_events += 1

    _coordination(events)
    existing_entries = {str(x.get("event_key")) for x in entries if isinstance(x, dict)}
    for event in events:
        if event.get("event_key") in existing_entries:
            continue
        chain = str(event.get("chain") or "solana").lower()
        token = str(event.get("token") or "")
        qualified = qmap.get((chain, _norm_token(chain, token)))
        if not qualified:
            event["qualification_state"] = "WAITING_WALLET500_GATE"
            continue
        pair = str(qualified.get("pair_address") or qualified.get("entry_pair_address") or "")
        price = float(qualified.get("price_usd") or qualified.get("current_price_usd") or 0)
        liq = float(qualified.get("liquidity_usd") or qualified.get("live_liquidity_usd") or 0)
        if not pair or price <= 0 or liq < 50000:
            event["qualification_state"] = "QUALIFIED_RECORD_NOT_EXECUTABLE"
            continue
        pos = float(state.get("position_size_usd") or 1.0)
        entry_at = t.isoformat()
        published = _dt(event.get("published_at"))
        entry = {
            "event_key": event.get("event_key"),
            "source_id": event.get("source_id"),
            "source_name": event.get("source_name"),
            "source_event_id": event.get("source_event_id"),
            "source_url": event.get("source_url"),
            "source_call_at": event.get("published_at"),
            "chain": chain,
            "token": token,
            "pair_address": pair,
            "pair_identity_locked": True,
            "entry_at": entry_at,
            "source_to_wallet500_gate_seconds": round((t - published).total_seconds(), 2) if published else None,
            "entry_price_usd": price,
            "entry_liquidity_usd": liq,
            "entry_market_cap": qualified.get("market_cap"),
            "entry_volume_h1": qualified.get("volume_h1") or qualified.get("live_volume_h1"),
            "entry_buys_h1": qualified.get("buys_h1") or qualified.get("live_buys_h1"),
            "entry_sells_h1": qualified.get("sells_h1") or qualified.get("live_sells_h1"),
            "wallet500_anomaly_score": qualified.get("anomaly_score"),
            "wallet500_qualification": qualified.get("qualification"),
            "wallet500_survival_gate": qualified.get("live_survival_gate"),
            "wallet500_production_risk_gate": qualified.get("production_risk_gate"),
            "source_consensus_count": event.get("source_consensus_count"),
            "coordinated_template": event.get("coordinated_template"),
            "cost_usd": pos,
            "quantity": pos / price,
            "current_price_usd": price,
            "current_liquidity_usd": liq,
            "current_value_usd": pos,
            "current_return_pct": 0.0,
            "peak_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "current_status": "LIVE",
            "ever_failed_survival": False,
            "horizon_marks": {},
            "truth_note": "Paper entry exists only because the exact token/pair appeared in Wallet500 active-qualified-candidates. The KOL recommendation did not bypass any Wallet500 production gate.",
        }
        entries.append(entry)
        existing_entries.add(str(event.get("event_key")))
        event["qualification_state"] = "ENTERED_AFTER_WALLET500_GATE"
        event["wallet500_gate_crossed_at"] = entry_at
        event["wallet500_gate_pair"] = pair

    for entry in entries:
        _mark_entry(entry, t, errors)

    _coordination(events)
    state["updated_at"] = t.isoformat()
    state["fetch_errors"] = errors[-50:]
    state["last_new_events"] = new_events
    state["source_count"] = len(config.get("sources") or [])
    _write(LEDGER, state)

    invested = sum(float(x.get("cost_usd") or 0) for x in entries)
    value = sum(float(x.get("current_value_usd") or 0) for x in entries)
    leaderboard = _source_stats(config, events, entries)
    summary = {
        "version": "KOL_FORWARD_V1",
        "updated_at": t.isoformat(),
        "started_at": state.get("started_at"),
        "mode": "PROSPECTIVE_ONLY_NO_BACKFILL",
        "status": "ACTIVE" if not errors else "ACTIVE_WITH_SOURCE_ERRORS",
        "sources_configured": len(config.get("sources") or []),
        "forward_calls": len(events),
        "new_calls_this_run": new_events,
        "waiting_wallet500_gate": sum(x.get("qualification_state") == "WAITING_WALLET500_GATE" for x in events),
        "qualified_paper_entries": len(entries),
        "coordinated_template_events": sum(bool(x.get("coordinated_template")) for x in events),
        "multi_source_tokens": len({x.get("token") for x in events if int(x.get("source_consensus_count") or 0) > 1}),
        "paper_invested_usd": round(invested, 6),
        "paper_current_value_usd": round(value, 6),
        "paper_pnl_usd": round(value - invested, 6),
        "paper_roi_pct": round((value / invested - 1.0) * 100.0, 4) if invested else 0.0,
        "live_entries": sum(x.get("current_status") == "LIVE" for x in entries),
        "failed_survival_entries": sum(bool(x.get("ever_failed_survival")) for x in entries),
        "source_leaderboard": leaderboard,
        "errors": errors,
        "truth_rules": [
            "No call published before experiment start is imported.",
            "Historical claimed wins are not scored.",
            "Every raw forward recommendation is retained, including recommendations that never qualify.",
            "A paper position opens only after the exact token/pair appears in Wallet500 active-qualified-candidates.",
            "Pair identity is locked at entry and subsequent marks use the same pair.",
            "Copy/template coordination is flagged and must not be counted as independent consensus.",
            "Sources remain probationary until the configured minimum forward sample is reached."
        ],
    }
    _write(SUMMARY, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    run()
