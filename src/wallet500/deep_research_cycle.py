from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from .revival_1000 import looks_like_solana_address
from .waking_confirmation import (
    _dedupe,
    _get_json,
    _identity,
    _scan_birdeye,
    _scan_news,
    _scan_reddit,
    _scan_x,
    _scan_youtube,
)

DATA = Path("data")
QUEUE = DATA / "hybrid-catalyst-scan-queue.json"
ORGANIC = DATA / "social-organic-acceleration.json"
DOSSIERS = DATA / "deep-research-dossiers.json"
LEDGER = DATA / "deep-research-ledger.json"
STATE = DATA / "deep-research-state.json"

MODE = "RESEARCH_ONLY_AUTONOMOUS_DEEP_RESEARCH_V1"
CONTRACT = "AUTONOMOUS_DEEP_RESEARCH_V1"
NETWORK = "solana"
DEFAULT_BUDGET = 12

POSITIVE_CATALYSTS = {
    "listing", "listed", "partnership", "partner", "integration", "mainnet",
    "buyback", "burn", "staking", "upgrade", "release", "roadmap", "governance",
    "funding", "adoption", "migration", "launch", "airdrop",
}
NEGATIVE_CATALYSTS = {
    "hack", "hacked", "exploit", "breach", "delist", "delisting", "lawsuit",
    "investigation", "unlock", "rug", "scam", "shutdown",
}


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _n(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _pct(cur, prev):
    cur = _n(cur)
    prev = _n(prev)
    if cur is None or prev in (None, 0):
        return None
    return round((cur / prev - 1.0) * 100.0, 3)


def _dt(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except Exception:
            return None
    text = str(v).strip()
    try:
        d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            d = parsedate_to_datetime(text)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _exact_market(token: str, pair: str) -> tuple[dict, dict]:
    if not looks_like_solana_address(token) or not looks_like_solana_address(pair):
        return {}, {"provider": "dexscreener_deep_research", "status": "INVALID_EXACT_IDENTITY"}
    try:
        payload = _get_json(f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair}")
        pairs = payload.get("pairs") or []
        exact = next((x for x in pairs if str(x.get("pairAddress") or "") == pair), None)
        if not isinstance(exact, dict):
            return {}, {"provider": "dexscreener_deep_research", "status": "PAIR_NOT_FOUND"}
        base = exact.get("baseToken") or {}
        if str(base.get("address") or "") != token:
            return {}, {"provider": "dexscreener_deep_research", "status": "BASE_TOKEN_MISMATCH"}
        liq = exact.get("liquidity") or {}
        vol = exact.get("volume") or {}
        tx = exact.get("txns") or {}
        pc = exact.get("priceChange") or {}
        h24 = tx.get("h24") or {}
        return {
            "pair_address": pair,
            "price_usd": _n(exact.get("priceUsd")),
            "liquidity_usd": _n(liq.get("usd")),
            "volume_24h_usd": _n(vol.get("h24")),
            "buys_24h": int(_n(h24.get("buys"), 0) or 0),
            "sells_24h": int(_n(h24.get("sells"), 0) or 0),
            "price_change_h1_pct": _n(pc.get("h1")),
            "price_change_h6_pct": _n(pc.get("h6")),
            "price_change_h24_pct": _n(pc.get("h24")),
            "market_cap_usd": _n(exact.get("marketCap")),
            "fdv_usd": _n(exact.get("fdv")),
            "dex_id": exact.get("dexId"),
            "symbol": base.get("symbol"),
            "name": base.get("name"),
        }, {"provider": "dexscreener_deep_research", "status": "OK"}
    except Exception as exc:
        return {}, {"provider": "dexscreener_deep_research", "status": type(exc).__name__}


def _organic_map(payload: dict) -> dict[str, dict]:
    out = {}
    for row in payload.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        token = str(row.get("contract") or "")
        if looks_like_solana_address(token):
            out[token] = row
    return out


def _context_identity(event: dict, identity: dict) -> str:
    """How confidently a public item belongs to this exact token.

    Exact CA is strongest. Official X is project context even without the CA. Broad
    name/ticker matches are preserved for research but are never called exact proof.
    """
    text = str(event.get("text") or "")
    mint = str(identity.get("token_address") or "")
    if mint and mint in text:
        return "EXACT_CONTRACT"
    source = str(event.get("source") or "")
    official_x = str(identity.get("official_x") or "")
    official_handle = urlparse(official_x).path.strip("/").split("/")[0].lower() if official_x else ""
    author = str(event.get("author") or "").strip().lower().lstrip("@")
    if source == "x" and official_handle and author == official_handle:
        return "OFFICIAL_CHANNEL_CONTEXT"
    return "NAME_SYMBOL_CONTEXT"


def _event_catalysts(events: list[dict]) -> dict:
    positive = set()
    negative = set()
    for event in events:
        text = str(event.get("text") or "").lower()
        positive.update(x for x in POSITIVE_CATALYSTS if x in text)
        negative.update(x for x in NEGATIVE_CATALYSTS if x in text)
    return {"positive": sorted(positive), "negative": sorted(negative)}


def _github_repo_name(url: str) -> str | None:
    try:
        p = urlparse(url)
        if p.netloc.lower() not in {"github.com", "www.github.com"}:
            return None
        bits = [x for x in p.path.strip("/").split("/") if x]
        if len(bits) < 2:
            return None
        return f"{bits[0]}/{bits[1].removesuffix('.git')}"
    except Exception:
        return None


def _github_activity(identity: dict) -> tuple[list[dict], list[dict]]:
    rows = []
    statuses = []
    for url in (identity.get("github_repos") or [])[:3]:
        repo = _github_repo_name(str(url))
        if not repo:
            continue
        try:
            payload = _get_json(f"https://api.github.com/repos/{repo}")
            rows.append({
                "repo": repo,
                "url": str(url),
                "pushed_at": payload.get("pushed_at"),
                "updated_at": payload.get("updated_at"),
                "open_issues_count": payload.get("open_issues_count"),
                "stargazers_count": payload.get("stargazers_count"),
                "archived": payload.get("archived"),
            })
            statuses.append({"provider": f"github:{repo}", "status": "OK"})
        except Exception as exc:
            statuses.append({"provider": f"github:{repo}", "status": type(exc).__name__})
    if not rows and not statuses:
        statuses.append({"provider": "github_project_activity", "status": "NO_OFFICIAL_REPO"})
    return rows, statuses


def _select_targets(queue_payload: dict, budget: int) -> list[dict]:
    rows = []
    seen = set()
    for row in queue_payload.get("queue") or []:
        if not isinstance(row, dict):
            continue
        token = str(row.get("token_address") or "")
        pair = str(row.get("pair_address") or "")
        if not looks_like_solana_address(token) or not looks_like_solana_address(pair):
            continue
        if token in seen:
            continue
        seen.add(token)
        rows.append(row)
    rows.sort(key=lambda x: (_n(x.get("risk_score"), 999) or 999, -(_n(x.get("hybrid_score_verified_normalized"), 0) or 0)))
    return rows[:max(1, budget)]


def _prior_observation(state_row: dict) -> dict:
    history = state_row.get("history") if isinstance(state_row.get("history"), list) else []
    return history[-1] if history else {}


def _research_state(*, market: dict, previous: dict, organic: dict | None, catalysts: dict, risk_score: float) -> tuple[str, list[str], int]:
    reasons = []
    score = 0.0
    liq_change = _pct(market.get("liquidity_usd"), (previous.get("market") or {}).get("liquidity_usd"))
    vol_change = _pct(market.get("volume_24h_usd"), (previous.get("market") or {}).get("volume_24h_usd"))
    organic_status = str((organic or {}).get("status") or "NO_ORGANIC_SIGNAL")

    if organic_status == "STRONG_ORGANIC_ACCELERATION":
        score += 30; reasons.append("STRONG_ORGANIC_SOCIAL_ACCELERATION")
    elif organic_status == "ORGANIC_ACCELERATION":
        score += 20; reasons.append("ORGANIC_SOCIAL_ACCELERATION")

    if catalysts.get("positive"):
        score += min(25.0, len(catalysts["positive"]) * 8.0); reasons.append("POSITIVE_PUBLIC_CATALYST_CONTEXT")
    if catalysts.get("negative"):
        score -= min(25.0, len(catalysts["negative"]) * 8.0); reasons.append("NEGATIVE_PUBLIC_CATALYST_CONTEXT")

    if liq_change is not None and liq_change >= 15:
        score += 15; reasons.append(f"LIQUIDITY_STRENGTHENING_{liq_change:+.1f}PCT")
    if vol_change is not None and vol_change >= 30:
        score += 10; reasons.append(f"VOLUME_STRENGTHENING_{vol_change:+.1f}PCT")
    if liq_change is not None and liq_change <= -25:
        score -= 35; reasons.append(f"LIQUIDITY_DETERIORATION_{liq_change:+.1f}PCT")
    if risk_score >= 35:
        score -= 35; reasons.append("UPSTREAM_RISK_GE_35")

    if risk_score >= 35 or (liq_change is not None and liq_change <= -25):
        state = "RISK_DIVERGENCE"
    elif organic_status in {"ORGANIC_ACCELERATION", "STRONG_ORGANIC_ACCELERATION"} and catalysts.get("positive"):
        state = "CATALYST_ORGANIC_CONVERGENCE"
    elif catalysts.get("positive"):
        state = "VERIFIED_CATALYST_CONTEXT"
    elif organic_status in {"ORGANIC_ACCELERATION", "STRONG_ORGANIC_ACCELERATION"}:
        state = "ORGANIC_ATTENTION_ACCELERATING"
    elif (liq_change is not None and liq_change >= 15) or (vol_change is not None and vol_change >= 30):
        state = "MARKET_STRUCTURE_STRENGTHENING"
    else:
        state = "NO_NEW_CONTEXT"

    return state, reasons or ["NO_MATERIAL_CONTEXT_CHANGE"], int(round(max(0.0, min(100.0, 50.0 + score))))


def _context_summary(state: str, reasons: list[str], catalysts: dict, organic: dict | None) -> str:
    organic_status = str((organic or {}).get("status") or "NO_ORGANIC_SIGNAL")
    pos = ", ".join(catalysts.get("positive") or []) or "none"
    neg = ", ".join(catalysts.get("negative") or []) or "none"
    return (
        f"Research state={state}. Organic social={organic_status}. "
        f"Positive catalyst terms={pos}; negative catalyst terms={neg}. "
        f"Material evidence: {', '.join(reasons[:6])}. "
        "Raw mention counts are not treated as organic acceleration, and this research layer has no production/trading impact."
    )


def run(output_dir: str | Path = "data") -> dict:
    global DATA, QUEUE, ORGANIC, DOSSIERS, LEDGER, STATE
    DATA = Path(output_dir)
    QUEUE = DATA / "hybrid-catalyst-scan-queue.json"
    ORGANIC = DATA / "social-organic-acceleration.json"
    DOSSIERS = DATA / "deep-research-dossiers.json"
    LEDGER = DATA / "deep-research-ledger.json"
    STATE = DATA / "deep-research-state.json"
    DATA.mkdir(parents=True, exist_ok=True)

    observed_at = datetime.now(timezone.utc)
    observed_iso = observed_at.isoformat()
    queue = _load(QUEUE, {})
    if queue.get("mode") != "RESEARCH_ONLY_CATALYST_SCAN_QUEUE_V1" or queue.get("network") != NETWORK:
        raise RuntimeError("DEEP_RESEARCH_QUEUE_CONTRACT_REJECTED")

    budget = int(_n(os.getenv("DEEP_RESEARCH_BUDGET"), DEFAULT_BUDGET) or DEFAULT_BUDGET)
    budget = max(1, min(30, budget))
    targets = _select_targets(queue, budget)
    organic_by_token = _organic_map(_load(ORGANIC, {}))
    state = _load(STATE, {"version": 1, "tokens": {}})
    tokens_state = state.setdefault("tokens", {})
    old_ledger = _load(LEDGER, {"version": 1, "events": []})
    ledger_events = list(old_ledger.get("events") or [])
    dossiers = []

    for target in targets:
        token = str(target.get("token_address") or "")
        pair = str(target.get("pair_address") or "")
        risk_score = _n(target.get("risk_score"), 0.0) or 0.0
        market, market_status = _exact_market(token, pair)
        coin = {
            "network": NETWORK,
            "token_address": token,
            "dex_pair_address": pair,
            "symbol": target.get("symbol") or market.get("symbol"),
            "name": target.get("name") or market.get("name"),
            "id": None,
        }
        identity, provider_status = _identity(coin)
        provider_status.append(market_status)

        token_state = dict(tokens_state.get(token) or {})
        birdeye_state = dict(token_state.get("birdeye") or {})
        holders, wallets, birdeye_state, birdeye_status = _scan_birdeye(token, birdeye_state, observed_iso)
        provider_status.append(birdeye_status)

        social_events = []
        for scanner in (_scan_x, _scan_youtube, _scan_reddit):
            events, status = scanner(identity)
            provider_status.append(status)
            social_events.extend(events)
        news_events, news_status = _scan_news(identity)
        provider_status.append(news_status)
        social_events = _dedupe(social_events)
        news_events = _dedupe(news_events)

        contextual_social = []
        for e in social_events:
            contextual_social.append({**e, "identity_confidence": _context_identity(e, identity)})
        contextual_news = []
        for e in news_events:
            contextual_news.append({**e, "identity_confidence": _context_identity(e, identity)})

        github_rows, github_status = _github_activity(identity)
        provider_status.extend(github_status)
        catalysts = _event_catalysts(contextual_social + contextual_news)
        organic = organic_by_token.get(token)
        previous = _prior_observation(token_state)
        research_state, reasons, context_score = _research_state(
            market=market,
            previous=previous,
            organic=organic,
            catalysts=catalysts,
            risk_score=risk_score,
        )

        observation = {
            "observed_at": observed_iso,
            "market": market,
            "holders": holders,
            "wallets": wallets,
            "organic_social": organic,
            "catalysts": catalysts,
            "social_events": contextual_social[:30],
            "news_events": contextual_news[:30],
            "github_activity": github_rows,
            "provider_status": provider_status,
            "research_state": research_state,
            "context_confidence_score": context_score,
            "reasons": reasons,
        }
        history = token_state.get("history") if isinstance(token_state.get("history"), list) else []
        history.append(observation)
        history = history[-48:]
        token_state.update({
            "token_address": token,
            "pair_address": pair,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "first_researched_at": token_state.get("first_researched_at") or observed_iso,
            "last_researched_at": observed_iso,
            "runs": int(token_state.get("runs") or 0) + 1,
            "birdeye": birdeye_state,
            "history": history,
        })
        tokens_state[token] = token_state

        price_delta = _pct(market.get("price_usd"), (previous.get("market") or {}).get("price_usd"))
        liq_delta = _pct(market.get("liquidity_usd"), (previous.get("market") or {}).get("liquidity_usd"))
        vol_delta = _pct(market.get("volume_24h_usd"), (previous.get("market") or {}).get("volume_24h_usd"))
        dossier = {
            "network": NETWORK,
            "token_address": token,
            "pair_address": pair,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "engine_trigger_at": target.get("first_requested_at"),
            "trigger_families": target.get("trigger_families") or [],
            "hybrid_status": target.get("hybrid_status"),
            "hybrid_score": target.get("hybrid_score_verified_normalized"),
            "upstream_risk_score": risk_score,
            "researched_at": observed_iso,
            "research_run_number": token_state["runs"],
            "research_state": research_state,
            "context_confidence_score": context_score,
            "context_summary": _context_summary(research_state, reasons, catalysts, organic),
            "what_changed_since_previous_research": {
                "price_pct": price_delta,
                "liquidity_pct": liq_delta,
                "volume_24h_pct": vol_delta,
                "organic_status_previous": (previous.get("organic_social") or {}).get("status"),
                "organic_status_now": (organic or {}).get("status"),
                "new_positive_catalysts": sorted(set(catalysts.get("positive") or []) - set((previous.get("catalysts") or {}).get("positive") or [])),
                "new_negative_catalysts": sorted(set(catalysts.get("negative") or []) - set((previous.get("catalysts") or {}).get("negative") or [])),
            },
            "identity": identity,
            "market": market,
            "holders": holders,
            "wallets": wallets,
            "organic_social": organic,
            "catalysts": catalysts,
            "public_context": {
                "social_items": contextual_social[:12],
                "news_items": contextual_news[:12],
                "github_activity": github_rows,
            },
            "provider_status": provider_status,
            "production_portfolio_impact": "NONE",
            "no_hindsight": True,
            "rules": [
                "exact Solana mint and exact pair are immutable research identity",
                "raw social mention count is not organic social acceleration",
                "project-owned/paid/copy-paste activity cannot become organic acceleration",
                "public context is accumulated prospectively every cycle and compared only to prior saved research observations",
                "research context does not create a BUY/SELL action",
            ],
        }
        dossiers.append(dossier)
        ledger_events.append({
            "event_key": f"{token}:{observed_iso}",
            "token_address": token,
            "pair_address": pair,
            "observed_at": observed_iso,
            "research_state": research_state,
            "context_confidence_score": context_score,
            "changes": dossier["what_changed_since_previous_research"],
            "catalysts": catalysts,
            "organic_status": (organic or {}).get("status"),
            "production_portfolio_impact": "NONE",
        })
        time.sleep(0.08)

    dossiers.sort(key=lambda x: (x.get("research_state") == "RISK_DIVERGENCE", -(x.get("context_confidence_score") or 0)))
    next_due = observed_at + timedelta(hours=4)
    dossier_payload = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "network": NETWORK,
        "generated_at": observed_iso,
        "next_nominal_research_at": next_due.isoformat(),
        "cadence_hours": 4,
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "input_queue_generated_at": queue.get("generated_at"),
        "selected_targets": len(targets),
        "dossiers": dossiers,
    }
    state.update({"version": 1, "updated_at": observed_iso, "tokens": tokens_state})
    ledger_payload = {
        "version": 1,
        "mode": "IMMUTABLE_AUTONOMOUS_DEEP_RESEARCH_LEDGER_V1",
        "updated_at": observed_iso,
        "events_count": len(ledger_events[-10000:]),
        "events": ledger_events[-10000:],
    }
    _write(DOSSIERS, dossier_payload)
    _write(STATE, state)
    _write(LEDGER, ledger_payload)
    return {
        "status": "OK",
        "targets": len(targets),
        "dossiers": len(dossiers),
        "risk_divergence": sum(1 for x in dossiers if x.get("research_state") == "RISK_DIVERGENCE"),
        "context_convergence": sum(1 for x in dossiers if x.get("research_state") == "CATALYST_ORGANIC_CONVERGENCE"),
        "next_nominal_research_at": next_due.isoformat(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
