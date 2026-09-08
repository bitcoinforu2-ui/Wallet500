from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

MODE = "RESEARCH_ONLY_PAID_SECONDARY_FEED_V1"
CONTRACT = "PAID_SECONDARY_FEED_V1"
NETWORK = "solana"
PRODUCTION_IMPACT = "NONE"

SOURCES = [
    {"handle": "dexpaidalerts", "role": "DEXSCREENER_PAID_TIME_AND_SECURITY"},
    {"handle": "dexpaidboost", "role": "DEXSCREENER_BOOST"},
    {"handle": "dexpaid_solana", "role": "DEXSCREENER_PAID_AND_BOOST"},
]

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_INDEX = {c: i for i, c in enumerate(BASE58)}
ADDRESS_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value):
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _err(exc: BaseException) -> str:
    if isinstance(exc, HTTPError): return f"HTTP_{exc.code}"
    if isinstance(exc, URLError): return "NETWORK_UNAVAILABLE"
    return type(exc).__name__


def _text(url: str, timeout: int = 15) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 Wallet500-PaidSecondary/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _json(url: str, timeout: int = 15):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Wallet500-PaidSecondary/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _b58decode(value: str) -> bytes | None:
    n = 0
    try:
        for c in value:
            n = n * 58 + BASE58_INDEX[c]
    except KeyError:
        return None
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + raw


def is_solana_address(value: str) -> bool:
    value = str(value or "").strip()
    raw = _b58decode(value)
    return 32 <= len(value) <= 44 and raw is not None and len(raw) == 32


def classify(text: str) -> list[str]:
    low = str(text or "").lower()
    out = []
    if "dex paid" in low or "dexscreener: ✅ paid" in low or "dexscreener 💵 paid" in low or "detected paid dexscreener" in low:
        out.append("DEXSCREENER_PAID")
    if "boosted ⚡" in low or "detected boost" in low or "dexscreener boost" in low:
        out.append("DEXSCREENER_BOOST")
    if "dex profile changed" in low:
        out.append("DEXSCREENER_PROFILE_CHANGE")
    return out


def _strip(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_preview(page: str, handle: str, reference: datetime) -> list[dict]:
    starts = list(re.finditer(r'data-post="([^"]+)"', page, flags=re.I))
    rows = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else min(len(page), start.start() + 50000)
        block = page[start.start():end]
        tm = re.search(r'<time[^>]+datetime="([^"]+)"', block, flags=re.I)
        body = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        if not tm or not body:
            continue
        published = _dt(tm.group(1))
        if published is None or published < reference - timedelta(hours=24) or published > reference + timedelta(minutes=5):
            continue
        text = _strip(body.group(1))
        kinds = classify(text)
        if not kinds:
            continue
        addresses = [a for a in ADDRESS_RE.findall(text) if is_solana_address(a)]
        for token in dict.fromkeys(addresses):
            rows.append({"source": "telegram", "source_handle": handle, "post_id": start.group(1), "published_at": published.isoformat(), "text": text[:2000], "event_types": kinds, "token_address": token, "url": f"https://t.me/{start.group(1)}"})
    return rows


def exact_pair(token: str, observed_at: str):
    try:
        payload = _json(f"https://api.dexscreener.com/token-pairs/v1/solana/{quote(token)}")
        candidates = []
        for pair in payload if isinstance(payload, list) else []:
            if not isinstance(pair, dict) or str((pair.get("baseToken") or {}).get("address") or "") != token:
                continue
            liq = float(((pair.get("liquidity") or {}).get("usd")) or 0)
            candidates.append((liq, pair))
        if not candidates:
            return None, "PAIR_NOT_FOUND"
        pair = max(candidates, key=lambda x: x[0])[1]
        return {"observed_at": observed_at, "pair_address": pair.get("pairAddress"), "symbol": (pair.get("baseToken") or {}).get("symbol"), "name": (pair.get("baseToken") or {}).get("name"), "dex_id": pair.get("dexId"), "price_usd": pair.get("priceUsd"), "liquidity_usd": (pair.get("liquidity") or {}).get("usd"), "market_cap_usd": pair.get("marketCap"), "boosts_active": (pair.get("boosts") or {}).get("active")}, "OK"
    except Exception as exc:
        return None, _err(exc)


def _covered_tokens(data: Path) -> tuple[set[str], set[str]]:
    main = _load(data / "paid-visibility-ledger.json", {})
    fast = _load(data / "paid-fast-redundancy-ledger.json", {})
    main_tokens = {str(x.get("token_address")) for x in main.get("events") or [] if isinstance(x, dict) and str(x.get("chain") or "").lower() == NETWORK}
    fast_tokens = {str(x.get("token_address")) for x in fast.get("events") or [] if isinstance(x, dict) and x.get("network") == NETWORK and x.get("pair_identity_locked") is True}
    return main_tokens, fast_tokens


def run(output_dir: str = "data") -> dict:
    data = Path(output_dir)
    observed_at = now_iso()
    reference = _dt(observed_at) or datetime.now(timezone.utc)
    main_tokens, fast_tokens = _covered_tokens(data)
    status = []
    observations = []
    for src in SOURCES:
        try:
            rows = parse_preview(_text(f"https://t.me/s/{quote(src['handle'])}"), src["handle"], reference)
            for row in rows:
                row["source_role"] = src["role"]
            observations.extend(rows)
            status.append({"provider": "telegram", "handle": src["handle"], "status": "OK", "relevant_observations": len(rows)})
        except Exception as exc:
            status.append({"provider": "telegram", "handle": src["handle"], "status": _err(exc), "relevant_observations": 0})

    by_token: dict[str, dict] = {}
    pair_status: dict[str, int] = {}
    for obs in observations:
        token = obs["token_address"]
        row = by_token.setdefault(token, {"network": NETWORK, "token_address": token, "event_types": [], "source_handles": [], "evidence": []})
        row["event_types"] = sorted(set([*row["event_types"], *obs["event_types"]]))
        if obs["source_handle"] not in row["source_handles"]:
            row["source_handles"].append(obs["source_handle"])
        row["evidence"].append({k: obs.get(k) for k in ("source_handle", "source_role", "post_id", "published_at", "url", "event_types")})

    rows = []
    for token, row in by_token.items():
        market, ps = exact_pair(token, observed_at)
        pair_status[ps] = pair_status.get(ps, 0) + 1
        if not market or not market.get("pair_address"):
            continue
        row.update({"pair_address": market["pair_address"], "pair_identity_locked": True, "market": market, "main_paid_ledger_covered": token in main_tokens, "fast_redundancy_covered": token in fast_tokens, "production_portfolio_impact": PRODUCTION_IMPACT})
        if token in main_tokens:
            row["coverage_status"] = "COVERED_BY_MAIN_PAID_LEDGER"
        elif token in fast_tokens:
            row["coverage_status"] = "COVERED_BY_FAST_REDUNDANCY"
        else:
            row["coverage_status"] = "SECONDARY_EXACT_PAIR_GAP_RESEARCH"
        rows.append(row)

    payload = {"version": 1, "mode": MODE, "contract": CONTRACT, "network": NETWORK, "generated_at": observed_at, "production_portfolio_impact": PRODUCTION_IMPACT, "no_hindsight": True, "sources": SOURCES, "counts": {"raw_relevant_observations": len(observations), "unique_strict_solana_tokens": len(by_token), "exact_pair_verified_tokens": len(rows), "covered_main": sum(x["coverage_status"] == "COVERED_BY_MAIN_PAID_LEDGER" for x in rows), "covered_fast": sum(x["coverage_status"] == "COVERED_BY_FAST_REDUNDANCY" for x in rows), "secondary_exact_pair_gaps": sum(x["coverage_status"] == "SECONDARY_EXACT_PAIR_GAP_RESEARCH" for x in rows)}, "provider_status": status, "pair_status_counts": pair_status, "targets": sorted(rows, key=lambda x: (x["coverage_status"], x["token_address"])), "rule": "Secondary public accounts are redundancy evidence only. Exact Solana base58 + exact DEXScreener pair is mandatory; no buy/PRE-ALPHA/production effect."}
    _write(data / "paid-secondary-feed.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
