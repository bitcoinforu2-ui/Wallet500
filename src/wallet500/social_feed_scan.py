from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .revival_1000 import looks_like_solana_address
from .social_catalyst import _normalize
from .waking_confirmation import _identity, _scan_news, _scan_reddit, _scan_x, _scan_youtube

DATA = Path("data")
OUTPUT = DATA / "social-source-scan.json"
LEDGER = DATA / "social-catalyst-ledger.json"
MODE = "RESEARCH_ONLY_SOCIAL_SOURCE_SCAN_V1"
NETWORK = "solana"


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


def _official_handle(url: str | None) -> str | None:
    if not url:
        return None
    try:
        p = urlparse(str(url)).path.strip("/")
        return p.split("/")[0].lower() if p else None
    except Exception:
        return None


def _attribution(event: dict, identity: dict) -> str:
    mint = str(identity.get("token_address") or "")
    text = str(event.get("text") or "")
    if mint and mint in text:
        return "EXACT_CONTRACT"
    src = str(event.get("source") or "").lower()
    author = str(event.get("author") or "").lower().lstrip("@")
    handle = _official_handle(identity.get("official_x"))
    if src == "x" and handle and author == handle:
        return "OFFICIAL_CHANNEL_CONTEXT"
    if src == "telegram" and identity.get("official_telegram"):
        return "OFFICIAL_CHANNEL_CONTEXT"
    return "NAME_SYMBOL_CONTEXT"


def _scan_public_telegram(identity: dict) -> tuple[list[dict], dict]:
    url = str(identity.get("official_telegram") or "")
    if not url:
        return [], {"provider": "telegram_official", "status": "NO_OFFICIAL_PUBLIC_CHANNEL"}
    try:
        p = urlparse(url)
        handle = p.path.strip("/").split("/")[0]
        if not handle or handle.startswith("+"):
            return [], {"provider": "telegram_official", "status": "PRIVATE_OR_INVITE_CHANNEL"}
        req = Request(f"https://t.me/s/{handle}", headers={"User-Agent": "Wallet500-Social/2.0"})
        with urlopen(req, timeout=18) as r:
            html = r.read().decode("utf-8", errors="replace")
        chunks = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', html, flags=re.S | re.I)
        rows = []
        for i, chunk in enumerate(chunks[-15:]):
            text = re.sub(r"<[^>]+>", " ", chunk)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                rows.append({"source": "telegram", "author": handle, "text": text[:1500], "id": f"{handle}:{i}"})
        return rows, {"provider": "telegram_official", "status": "OK", "count": len(rows)}
    except Exception as exc:
        return [], {"provider": "telegram_official", "status": type(exc).__name__}


def _coin_map(revival: dict) -> dict[str, dict]:
    out = {}
    for row in revival.get("coins") or []:
        if isinstance(row, dict) and looks_like_solana_address(str(row.get("token_address") or "")):
            out[str(row["token_address"])] = row
    return out


def _select_targets(envelope: dict, budget: int) -> list[dict]:
    rows = [x for x in (envelope.get("candidates") or []) if isinstance(x, dict)]
    rows = [x for x in rows if x.get("status") != "BLOCKED_TRUTH" and looks_like_solana_address(str(x.get("token_address") or "")) and looks_like_solana_address(str(x.get("pair_address") or ""))]
    tier = {"WAKING_EVIDENCE_READY": 0, "PRE_WAKING_EVIDENCE_READY": 1, "ANOMALY_WATCH": 2, "WAKING_MARKET_WATCH": 3, "BASELINE_DEEP_WATCH": 4}
    rows.sort(key=lambda x: (
        tier.get(str(x.get("discovery_tier") or ""), 9),
        -float(((x.get("adaptive_discovery") or {}).get("anomaly_score")) or 0),
        -float(((x.get("market") or {}).get("revival_score_verified")) or 0),
    ))
    return rows[:max(1, budget)]


def _merge_exact_social_events(scan_targets: list[dict], observed_at: str, data_dir: Path) -> int:
    ledger = _load(data_dir / LEDGER.name, {})
    old = ledger.get("events") if isinstance(ledger, dict) else []
    events = list(old) if isinstance(old, list) else []
    known = {str(x.get("fingerprint") or "") for x in events if isinstance(x, dict)}
    added = 0
    for target in scan_targets:
        token = str(target.get("token_address") or "")
        for event in target.get("events") or []:
            if not isinstance(event, dict) or str(event.get("source") or "") not in {"x", "youtube", "reddit", "telegram"}:
                continue
            attr = str(event.get("attribution") or "")
            if attr not in {"EXACT_CONTRACT", "OFFICIAL_CHANNEL_CONTEXT"}:
                continue
            raw = dict(event)
            raw.update({"contract": token, "chain": NETWORK})
            if attr == "OFFICIAL_CHANNEL_CONTEXT":
                raw["project_owned"] = True
                raw["author_role"] = "official"
            for row in _normalize(raw, observed_at):
                fp = str(row.get("fingerprint") or "")
                if not fp or fp in known:
                    continue
                events.append(row); known.add(fp); added += 1
    events = events[-10000:]
    _write(data_dir / LEDGER.name, {
        "version": 2,
        "updated_at": observed_at,
        "method": "IMMUTABLE_SOCIAL_EVENT_LEDGER_NO_CAUSALITY_ASSUMED",
        "events_count": len(events),
        "new_events_this_run": added,
        "quality_metadata_preserved": True,
        "events": events,
    })
    return added


def run(output_dir: str | Path = "data") -> dict:
    data = Path(output_dir)
    observed_at = datetime.now(timezone.utc).isoformat()
    envelope = _load(data / "candidate-evidence-envelope.json", {})
    revival = _load(data / "revival-1000-latest.json", {})
    coins = _coin_map(revival)
    budget = max(1, min(30, int(os.getenv("SOCIAL_SCAN_BUDGET", "12"))))
    selected = _select_targets(envelope, budget)
    targets = []
    provider_counts: dict[str, int] = {}

    for row in selected:
        token = str(row.get("token_address") or "")
        base = coins.get(token, {})
        coin = {
            "token_address": token,
            "dex_pair_address": row.get("pair_address"),
            "symbol": row.get("symbol") or base.get("symbol"),
            "name": base.get("name") or row.get("symbol"),
            "id": base.get("id") or base.get("coingecko_id"),
        }
        identity, identity_status = _identity(coin)
        scans = []
        for fn in (_scan_x, _scan_youtube, _scan_reddit, _scan_news):
            events, status = fn(identity)
            scans.append((events, status))
        events, status = _scan_public_telegram(identity)
        scans.append((events, status))
        all_events = []
        statuses = list(identity_status)
        for events, status in scans:
            statuses.append(status)
            key = f"{status.get('provider')}:{status.get('status')}"
            provider_counts[key] = provider_counts.get(key, 0) + 1
            for event in events or []:
                if not isinstance(event, dict):
                    continue
                e = dict(event)
                e["attribution"] = _attribution(e, identity)
                all_events.append(e)
        targets.append({
            "network": NETWORK,
            "token_address": token,
            "pair_address": row.get("pair_address"),
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "discovery_tier": row.get("discovery_tier"),
            "identity": identity,
            "provider_status": statuses,
            "events": all_events[:80],
        })

    merged = _merge_exact_social_events(targets, observed_at, data)
    payload = {
        "version": 1,
        "mode": MODE,
        "generated_at": observed_at,
        "network": NETWORK,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "no_hindsight": True,
        "scan_budget": budget,
        "targets_scanned": len(targets),
        "new_exact_social_events_merged": merged,
        "provider_status_counts": provider_counts,
        "rules": [
            "EXACT_CONTRACT_OR_OFFICIAL_CONTEXT_REQUIRED_BEFORE_SOCIAL_LEDGER_MERGE",
            "NAME_SYMBOL_CONTEXT_IS_VISIBLE_RESEARCH_CONTEXT_BUT_NOT_ORGANIC_PROOF",
            "OFFICIAL_PROJECT_POSTS_ARE_DISCOUNTED_BY_ORGANIC_ACCELERATION",
            "MISSING_PROVIDER_IS_UNKNOWN_NOT_ZERO",
        ],
        "targets": targets,
    }
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    p = run()
    print(json.dumps({"targets": p["targets_scanned"], "merged": p["new_exact_social_events_merged"], "providers": p["provider_status_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
