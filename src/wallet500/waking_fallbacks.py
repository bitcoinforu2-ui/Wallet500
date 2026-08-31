from __future__ import annotations

import html
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .revival_1000 import looks_like_solana_address
from .waking_confirmation import NEGATIVE_CATALYSTS, POSITIVE_CATALYSTS, score_holder_growth, score_social

DATA = Path("data")
LATEST = DATA / "waking-confirmation-latest.json"
STATE = DATA / "waking-confirmation-state.json"
NETWORK = "solana"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _n(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _get_json(url: str, timeout: int = 20):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Wallet500-Waking-Fallback/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_text(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0 Wallet500-Waking-Fallback/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _safe_error(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code:
        return f"HTTP_{code}"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _recursive_find(obj, keys: set[str]):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in keys:
                return v
        for v in obj.values():
            found = _recursive_find(v, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _recursive_find(v, keys)
            if found is not None:
                return found
    return None


def extract_rugcheck_metrics(report: dict) -> dict:
    """Extract exact-mint holder count and top-token-account concentration conservatively."""
    holder_count = _recursive_find(
        report,
        {"totalholders", "total_holders", "holdercount", "holder_count", "holderscount", "holders_count"},
    )
    holder_count = _n(holder_count)

    top = _recursive_find(report, {"topholders", "top_holders"})
    pcts: list[float] = []
    if isinstance(top, list):
        for row in top:
            if not isinstance(row, dict):
                continue
            pct = None
            for key in ("pct", "percentage", "percent", "supply_pct", "supplyPct"):
                if key in row:
                    pct = _n(row.get(key))
                    if pct is not None:
                        break
            if pct is None:
                continue
            # Some providers express ratios as 0..1, RugCheck normally emits percent values.
            if 0 < pct <= 1 and any(k in row for k in ("supply_pct", "supplyPct")):
                pct *= 100.0
            if 0 <= pct <= 100:
                pcts.append(float(pct))
    pcts.sort(reverse=True)
    return {
        "holder_count": int(holder_count) if holder_count is not None and holder_count >= 0 else None,
        "top_holder_rows": len(pcts),
        "top1_pct": round(sum(pcts[:1]), 4) if pcts else None,
        "top5_pct": round(sum(pcts[:5]), 4) if pcts else None,
        "top10_pct": round(sum(pcts[:10]), 4) if pcts else None,
        "top20_pct": round(sum(pcts[:20]), 4) if pcts else None,
    }


def concentration_risk(top1, top10) -> tuple[float, list[str]]:
    top1 = _n(top1)
    top10 = _n(top10)
    if top1 is None or top10 is None:
        return 0.0, ["RUGCHECK_CONCENTRATION_INCOMPLETE"]
    risk = 0.0
    signals = [f"TOP1_TOKEN_ACCOUNT_{top1:.2f}PCT", f"TOP10_TOKEN_ACCOUNTS_{top10:.2f}PCT"]
    if top1 >= 20:
        risk += 35; signals.append("TOP1_TOKEN_ACCOUNT_GE_20PCT")
    elif top1 >= 10:
        risk += 18; signals.append("TOP1_TOKEN_ACCOUNT_GE_10PCT")
    if top10 >= 60:
        risk += 30; signals.append("TOP10_TOKEN_ACCOUNTS_GE_60PCT")
    elif top10 >= 40:
        risk += 15; signals.append("TOP10_TOKEN_ACCOUNTS_GE_40PCT")
    return min(100.0, risk), signals


def scan_rugcheck(address: str, state_row: dict, observed_at: str):
    try:
        report = _get_json(f"https://api.rugcheck.xyz/v1/tokens/{quote(address)}/report")
        metrics = extract_rugcheck_metrics(report if isinstance(report, dict) else {})
    except Exception as exc:
        return None, None, state_row, {"provider": "rugcheck", "status": _safe_error(exc)}

    st = dict(state_row)
    holders = None
    current = metrics.get("holder_count")
    previous = st.get("rugcheck_holder_count")
    if current is not None:
        score, signals, change = score_holder_growth(current, previous)
        holders = {
            "available": True,
            "verified": True,
            "source": "RUGCHECK_EXACT_MINT_PUBLIC_REPORT",
            "observed_at": observed_at,
            "score": round(score, 2),
            "signals": [*signals, "RUGCHECK_HOLDER_COUNT_THIRD_PARTY_CACHE_POSSIBLE"],
            "metrics": {
                "holder_count": current,
                "previous_holder_count": previous,
                "holder_change_pct": change,
            },
            "limitations": [
                "third-party holder count may be cached and is used as confirmation research only",
                "first observation is baseline learning and receives no growth score",
            ],
        }
        st["rugcheck_holder_count"] = current
        st["rugcheck_observed_at"] = observed_at

    risk, signals = concentration_risk(metrics.get("top1_pct"), metrics.get("top10_pct"))
    distribution = None
    if metrics.get("top1_pct") is not None and metrics.get("top10_pct") is not None:
        distribution = {
            "verified": True,
            "contract_match": True,
            "source": "RUGCHECK_EXACT_MINT_TOP_TOKEN_ACCOUNTS",
            "observed_at": observed_at,
            "risk_score": round(risk, 2),
            "anomaly_score": round(max(0.0, 100.0 - risk), 2),
            "score_semantics": "CONCENTRATION_RISK_ONLY_NOT_INDEPENDENT_POSITIVE_FAMILY",
            "signals": signals,
            "metrics": metrics,
            "limitations": [
                "top-holder rows are token-account concentration, not verified owner-cluster concentration",
                "LP/burn/infrastructure exclusions are not independently verified here",
                "therefore RugCheck concentration can add risk but never supplies an independent positive family",
            ],
        }
    return holders, distribution, st, {"provider": "rugcheck", "status": "OK"}


def telegram_handle(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(str(url))
        if parsed.hostname not in {"t.me", "telegram.me", "www.t.me"}:
            return None
        parts = [x for x in parsed.path.split("/") if x]
        if not parts:
            return None
        if parts[0] == "s" and len(parts) > 1:
            parts = parts[1:]
        handle = parts[0]
        if handle.startswith("+") or handle.lower() in {"joinchat", "share", "iv"}:
            return None
        return handle
    except Exception:
        return None


def _strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _dt(value: object) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def parse_telegram_messages(page: str, handle: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    matches = list(re.finditer(r'data-post="([^"]+)"', page, flags=re.I))
    rows: list[dict] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(page), match.start() + 40000)
        block = page[match.start():end]
        tm = re.search(r'<time[^>]+datetime="([^"]+)"', block, flags=re.I)
        if not tm:
            continue
        published = _dt(tm.group(1))
        if published is None or published < now - timedelta(hours=24) or published > now + timedelta(minutes=5):
            continue
        txt = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        text = _strip_tags(txt.group(1)) if txt else ""
        post_id = match.group(1)
        rows.append({
            "source": "telegram",
            "id": post_id,
            "author": handle,
            "published_at": published.isoformat(),
            "text": text[:1500],
            "url": "https://t.me/" + post_id,
            "identity_match": "OFFICIAL_TELEGRAM_FROM_TOKEN_IDENTITY_PACK",
        })
    seen = set()
    out = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
    return out


def scan_telegram(identity: dict, observed_at: str):
    handle = telegram_handle(identity.get("official_telegram"))
    if not handle:
        return [], {"provider": "telegram_official", "status": "NO_OFFICIAL_PUBLIC_CHANNEL"}
    try:
        page = _get_text(f"https://t.me/s/{quote(handle)}")
        rows = parse_telegram_messages(page, handle)
        return rows, {"provider": "telegram_official", "status": "OK", "count": len(rows)}
    except Exception as exc:
        return [], {"provider": "telegram_official", "status": _safe_error(exc)}


def telegram_catalyst_score(rows: list[dict], previous_count: int | None) -> tuple[float, list[str]]:
    score = min(20.0, len(rows) * 4.0)
    signals = [f"OFFICIAL_TELEGRAM_24H_POSTS_{len(rows)}"]
    catalysts = set()
    for row in rows:
        text = str(row.get("text") or "").lower()
        catalysts.update(x for x in (*POSITIVE_CATALYSTS, *NEGATIVE_CATALYSTS) if x in text)
    if catalysts:
        score += min(30.0, 10.0 * len(catalysts))
        signals.append("OFFICIAL_TELEGRAM_CATALYST_KEYWORDS:" + ",".join(sorted(catalysts)[:8]))
    if previous_count is not None and previous_count > 0:
        ratio = len(rows) / previous_count
        signals.append(f"TELEGRAM_POST_COUNT_VS_PREVIOUS_{ratio:.2f}X")
        if ratio >= 2:
            score += 20.0
        if ratio >= 4:
            score += 15.0
    elif rows:
        signals.append("TELEGRAM_BASELINE_LEARNING")
    return min(100.0, score), signals


def conservative_confirmation_status(channels: dict, distribution: dict | None) -> tuple[str, float, list[str]]:
    """Do not double count RugCheck holder growth and RugCheck concentration as independent positives."""
    weights = {"holders": 25.0, "wallets": 25.0, "social": 20.0, "news": 15.0, "distribution": 15.0}
    score = 0.0
    strong: list[str] = []
    for name in ("holders", "wallets", "social", "news"):
        ch = channels.get(name) or {}
        if ch.get("verified") is not True:
            continue
        s = max(0.0, min(100.0, _n(ch.get("score"), 0.0) or 0.0))
        score += weights[name] * s / 100.0
        if s >= 55:
            strong.append(name)

    risk = _n((distribution or {}).get("risk_score"))
    source = str((distribution or {}).get("source") or "")
    if risk is not None and not source.startswith("RUGCHECK_"):
        dist_score = max(0.0, 100.0 - risk)
        score += weights["distribution"] * dist_score / 100.0
        if dist_score >= 70:
            strong.append("distribution")
    if risk is not None and risk >= 50:
        return "WAKING_RISK_RESEARCH", round(score, 2), strong
    if len(set(strong)) >= 3 and score >= 45:
        return "WAKING_STRONG_RESEARCH", round(score, 2), strong
    if len(set(strong)) >= 2 and score >= 30:
        return "WAKING_CONFIRMED_RESEARCH", round(score, 2), strong
    return "WAKING_UNCONFIRMED_RESEARCH", round(score, 2), strong


def _dedupe(rows: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        key = (row.get("source"), row.get("id") or row.get("url") or row.get("text"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def run() -> dict:
    payload = _load(LATEST, {})
    state = _load(STATE, {"version": 1, "tokens": {}})
    if payload.get("mode") != "RESEARCH_ONLY_WAKING_CONFIRMATION_V1" or payload.get("network") != NETWORK:
        raise RuntimeError("WAKING_FALLBACK_SOURCE_CONTRACT_REJECTED")
    if payload.get("production_portfolio_impact") != "NONE" or payload.get("no_hindsight") is not True:
        raise RuntimeError("WAKING_FALLBACK_SAFETY_CONTRACT_REJECTED")

    observed_at = now_iso()
    tokens = state.setdefault("tokens", {})
    provider_counts: dict[str, int] = {}
    rows = []
    for row in payload.get("targets") or []:
        if not isinstance(row, dict):
            continue
        address = str(row.get("token_address") or "")
        if not looks_like_solana_address(address) or row.get("base_watch_status") != "WAKING_MARKET_ONLY":
            continue
        st = dict(tokens.get(address) or {})
        channels = dict(row.get("channels") or {})
        distribution = row.get("distribution_evidence") if isinstance(row.get("distribution_evidence"), dict) else None
        statuses = list(row.get("provider_status") or [])

        # Exact-mint no-key holder fallback. Birdeye remains preferred when already verified.
        rug_holders, rug_distribution, st, rug_status = scan_rugcheck(address, st, observed_at)
        statuses.append(rug_status)
        if (channels.get("holders") or {}).get("verified") is not True and rug_holders:
            channels["holders"] = rug_holders
        if distribution is None and rug_distribution:
            distribution = rug_distribution

        identity = row.get("identity") or {}
        telegram_rows, telegram_status = scan_telegram(identity, observed_at)
        statuses.append(telegram_status)
        old_social = channels.get("social") or {}
        existing_events = list(old_social.get("events") or []) if isinstance(old_social, dict) else []
        social_events = _dedupe(existing_events + telegram_rows)
        telegram_score, telegram_signals = telegram_catalyst_score(telegram_rows, st.get("telegram_mentions"))
        base_score = _n(old_social.get("score"), 0.0) or 0.0
        generic_score, generic_signals = score_social(social_events, st.get("social_mentions_augmented"))
        social_verified = old_social.get("verified") is True or telegram_status.get("status") == "OK"
        social_score = min(100.0, max(base_score, generic_score, telegram_score)) if social_verified else 0.0
        channels["social"] = {
            "available": social_verified,
            "verified": social_verified,
            "source": "WAKING_SOCIAL_MULTI_SOURCE+OFFICIAL_TELEGRAM_V2" if social_verified else "NOT_CONNECTED",
            "observed_at": observed_at,
            "score": round(social_score, 2),
            "signals": list(dict.fromkeys([
                *(old_social.get("signals") or []),
                *generic_signals,
                *telegram_signals,
            ]))[:30] if social_verified else [],
            "metrics": {
                "mentions": len(social_events),
                "sources": len({x.get("source") for x in social_events if x.get("source")}),
                "authors": len({x.get("author") for x in social_events if x.get("author")}),
                "official_telegram_24h_posts": len(telegram_rows),
            },
            "events": social_events[:40],
        }

        status, score, strong = conservative_confirmation_status(channels, distribution)
        st["telegram_mentions"] = len(telegram_rows)
        st["social_mentions_augmented"] = len(social_events)
        st["fallback_observed_at"] = observed_at
        tokens[address] = st

        for p in (rug_status, telegram_status):
            key = f"{p.get('provider')}:{p.get('status')}"
            provider_counts[key] = provider_counts.get(key, 0) + 1

        row = dict(row)
        row["channels"] = channels
        row["distribution_evidence"] = distribution
        row["provider_status"] = statuses
        row["confirmation_status"] = status
        row["confirmation_score"] = score
        row["strong_families"] = strong
        row["fallback_enriched_at"] = observed_at
        rows.append(row)
        time.sleep(0.25)

    payload["targets"] = rows
    payload["fallback_enriched_at"] = observed_at
    payload["fallback_contract"] = {
        "version": "WAKING_NO_KEY_FALLBACKS_V1",
        "rugcheck": "EXACT_MINT_HOLDER_COUNT_AND_TOKEN_ACCOUNT_CONCENTRATION_RESEARCH_ONLY",
        "telegram": "OFFICIAL_PUBLIC_CHANNEL_FROM_IDENTITY_PACK_LAST_24H_ONLY",
        "rugcheck_distribution_positive_double_count": "FORBIDDEN",
        "production_portfolio_impact": "NONE",
    }
    payload["counts"] = {
        "waking_targets": len(rows),
        "confirmed": sum(1 for x in rows if x.get("confirmation_status") == "WAKING_CONFIRMED_RESEARCH"),
        "strong": sum(1 for x in rows if x.get("confirmation_status") == "WAKING_STRONG_RESEARCH"),
        "risk": sum(1 for x in rows if x.get("confirmation_status") == "WAKING_RISK_RESEARCH"),
        "unconfirmed": sum(1 for x in rows if x.get("confirmation_status") == "WAKING_UNCONFIRMED_RESEARCH"),
    }
    combined_counts = dict(payload.get("provider_status_counts") or {})
    for key, value in provider_counts.items():
        combined_counts[key] = combined_counts.get(key, 0) + value
    payload["provider_status_counts"] = combined_counts

    state["updated_at"] = observed_at
    state["tokens"] = tokens
    _write(STATE, state)
    _write(LATEST, payload)
    print("WAKING_NO_KEY_FALLBACKS_V1_OK", payload["counts"], provider_counts)
    return payload


if __name__ == "__main__":
    run()
