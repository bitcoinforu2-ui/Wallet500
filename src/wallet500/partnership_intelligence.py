"""Bounded partnership research inside the existing unified watch engine.

A mascot mention, ticker match, paid sponsorship or news article is NEVER a
verified token partnership. Even an official page explicitly containing a
contract produces only an analyst-review event, not a trading signal.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
CONFIG = DATA / "partnership-watch-targets.json"
STATE = DATA / "partnership-intelligence-state.json"
REPORT = DATA / "partnership-intelligence-latest.json"
INBOX = DATA / "partnership-evidence-inbox.json"
CATALYST = DATA / "catalyst-wire-live.json"
SOCIAL = DATA / "social-catalyst-ledger.json"
USER_AGENT = "Wallet500-PartnershipIntelligence/1.0"
MAX_FETCH_BYTES = 512_000
MAX_EVENTS = 400
SCAN_HOURS = 6


def utcnow():
    return datetime.now(timezone.utc)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (ValueError, OSError):
        return default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_date(raw):
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def host_allowed(url, allowed):
    """Check actual HTTPS hostname, never a string prefix or substring."""
    try:
        u = urllib.parse.urlsplit(url)
        hostname = (u.hostname or "").lower().rstrip(".")
        return (
            u.scheme == "https" and u.username is None and u.password is None
            and u.port in (None, 443)
            and any(hostname == d or hostname.endswith("." + d) for d in allowed)
        )
    except ValueError:
        return False


def fetch(url, allowed):
    if not host_allowed(url, allowed):
        raise ValueError("SOURCE_HOST_NOT_ALLOWLISTED")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,text/html,*/*"})
    with urllib.request.urlopen(req, timeout=8) as response:
        # Validate final URL too; do not follow redirects to arbitrary hosts.
        if not host_allowed(response.geturl(), allowed):
            raise ValueError("REDIRECT_OUTSIDE_SOURCE_ALLOWLIST")
        return response.read(MAX_FETCH_BYTES + 1)[:MAX_FETCH_BYTES].decode("utf-8", errors="replace")


def normalize_contract(chain, contract):
    value = str(contract or "").strip()
    return value.lower() if chain in ("ethereum", "bsc", "base", "arbitrum") else value


def exact_match(record, target):
    chain = str(record.get("chain") or record.get("network") or "").lower()
    chain = {"eth": "ethereum", "bnb": "bsc"}.get(chain, chain)
    contract = normalize_contract(chain, record.get("contract") or record.get("token_address") or record.get("mint"))
    return bool(chain == target["chain"] and contract == normalize_contract(chain, target["contract"]))


def fingerprint(target, url, title, published):
    raw = "|".join([target["chain"], target["contract"], url or "", title or "", published or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def evidence(target, title, url, published, source, classification, note):
    return {
        "event_id": fingerprint(target, url, title, published),
        "symbol": target["symbol"], "chain": target["chain"], "contract": target["contract"],
        "title": title[:350], "url": url[:1100], "published_at": published,
        "source": source, "classification": classification, "explanation": note,
        "trading_signal": False, "telegram_eligible": False,
        "contract_identity_verified_by_primary_source": classification == "PRIMARY_EXACT_CONTRACT_REVIEW",
        "partnership_confirmed": False,
    }


def rss_entries(xml_body):
    root = ET.fromstring(xml_body)
    rows = []
    for item in root.findall(".//item")[:50]:
        def value(tag):
            node = item.find(tag)
            return "".join(node.itertext()).strip() if node is not None else ""
        rows.append({"title": html.unescape(value("title")), "url": value("link"),
                     "published": value("pubDate"), "summary": html.unescape(value("description"))})
    return rows


def search_news(target, errors):
    # Google News is discovery only; even an apparently official headline
    # never authenticates a deal or an association with this contract.
    result = []
    for query in (target.get("queries") or [])[:3]:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            for row in rss_entries(fetch(url, {"news.google.com"})):
                body = (row["title"] + " " + row["summary"]).lower()
                if not any(str(alias).lower() in body for alias in target.get("aliases", [])):
                    continue
                result.append(evidence(target, row["title"], row["url"], row["published"],
                    "GOOGLE_NEWS_DISCOVERY", "UNVERIFIED_DISCOVERY",
                    "Aggregator headline: cannot establish token identity or business agreement."))
        except Exception as exc:
            errors.append({"target": target["symbol"], "source": "GOOGLE_NEWS", "error": type(exc).__name__})
    return result


def ingest_existing(target):
    result = []
    wire = load(CATALYST, {})
    for row in (wire.get("events") or [])[-200:] if isinstance(wire, dict) else []:
        if not isinstance(row, dict) or not exact_match(row, target):
            continue
        url = str(row.get("source_url") or row.get("url") or "")
        if url:
            result.append(evidence(target, str(row.get("headline") or row.get("title") or row.get("event_type") or "Catalyst mention"),
                url, str(row.get("published_at") or row.get("observed_at") or ""),
                "EXISTING_CATALYST_WIRE", "EXACT_IDENTITY_SECONDARY",
                "Existing catalyst feed matched exact chain and contract; primary claim still unverified."))
    social = load(SOCIAL, {})
    for row in (social.get("events") or [])[-200:] if isinstance(social, dict) else []:
        if not isinstance(row, dict) or not exact_match(row, target):
            continue
        url = str(row.get("url") or "")
        if url:
            result.append(evidence(target, str(row.get("text") or "Social mention"), url,
                str(row.get("published_at") or ""), "EXISTING_SOCIAL_LEDGER",
                "EXACT_IDENTITY_SECONDARY",
                "Exact-contract social mention; author ownership and partnership unverified."))
    return result


def verify_primary(target, raw, errors):
    """Fetch exact official HTTPS page. No website or author self-attestation."""
    url = str(raw.get("url") or "")
    allowed = set(target.get("verified_primary_hosts") or [])
    if not host_allowed(url, allowed):
        return None
    try:
        page = html.unescape(re.sub(r"<[^>]+>", " ", fetch(url, allowed)))
        contract = target["contract"]
        explicit = contract in page if target["chain"] == "solana" else contract.lower() in page.lower()
        title = str(raw.get("title") or "Primary-source document")
        return evidence(target, title, url, str(raw.get("published_at") or ""), "VERIFIED_PRIMARY_DOMAIN",
            "PRIMARY_EXACT_CONTRACT_REVIEW" if explicit else "PRIMARY_CONTEXT_ONLY",
            "Exact mint appears on fetched primary site; analyst must verify claim meaning." if explicit
            else "Primary page contains no exact mint; brand or mascot is not the token.")
    except Exception as exc:
        errors.append({"target": target["symbol"], "source": "PRIMARY_PAGE", "error": type(exc).__name__})
        return None


def run(data_dir=None, now=None, news_fetcher=search_news):
    global DATA, CONFIG, STATE, REPORT, INBOX, CATALYST, SOCIAL
    # Paths are local to this run to make CI fixtures deterministic.
    data = Path(data_dir) if data_dir is not None else DATA
    cfg = load(data / "partnership-watch-targets.json", {})
    previous = load(data / "partnership-intelligence-state.json", {})
    first_run = not (data / "partnership-intelligence-state.json").exists()
    now = now or utcnow()
    prev_scan = parse_date(previous.get("last_scan")) if isinstance(previous, dict) else None
    due = prev_scan is None or now - prev_scan >= timedelta(hours=SCAN_HOURS)
    if not due:
        return {"status": "SKIPPED_COOLDOWN", "last_scan": previous.get("last_scan")}
    errors, incoming = [], []
    inbox = load(data / "partnership-evidence-inbox.json", [])
    if not isinstance(inbox, list):
        inbox = []
    old_catalyst, old_social = CATALYST, SOCIAL
    CATALYST, SOCIAL = data / CATALYST.name, data / SOCIAL.name
    try:
        for target in (cfg.get("targets") or [])[:30]:
            if not isinstance(target, dict) or not target.get("chain") or not target.get("contract"):
                continue
            incoming.extend(ingest_existing(target))
            incoming.extend(news_fetcher(target, errors))
            for raw in inbox[-100:]:
                if isinstance(raw, dict):
                    # Official context can be inspected even when inbox omits a
                    # chain/contract, but NEVER assigned to a token as a partnership.
                    explicit = exact_match(raw, target)
                    tagged = raw.get("target_contract") == target["contract"] and raw.get("target_chain") == target["chain"]
                    if not explicit and not tagged:
                        continue
                    proof = verify_primary(target, raw, errors)
                    if proof:
                        incoming.append(proof)
    finally:
        CATALYST, SOCIAL = old_catalyst, old_social
    seen = set(previous.get("seen_ids") or [])
    fresh = []
    for ev in incoming:
        if ev["event_id"] not in seen:
            fresh.append(ev)
            seen.add(ev["event_id"])
    history = (previous.get("recent_events") or []) + fresh
    history = history[-MAX_EVENTS:]
    state = {
        "version": 1, "last_scan": now.isoformat(), "status": "RESEARCH_ONLY",
        "first_run_historical_baseline": first_run, "seen_ids": list(seen)[-10000:],
        "recent_events": history, "errors": errors[-30:],
    }
    report = {
        "version": 1, "updated_at": now.isoformat(), "policy": "NO_TELEGRAM_NO_AUTO_BUY",
        "targets": [{"chain": x.get("chain"), "contract": x.get("contract"), "symbol": x.get("symbol")}
                    for x in (cfg.get("targets") or []) if isinstance(x, dict)],
        "new_events": 0 if first_run else len(fresh),
        "initial_baseline_events": len(fresh) if first_run else 0,
        "manual_review": [] if first_run else [x for x in fresh if x["classification"] == "PRIMARY_EXACT_CONTRACT_REVIEW"],
        "discovery": [] if first_run else fresh[-35:],
        "errors": errors[-30:],
        "telegram_sent": 0, "auto_trade": False,
    }
    save(data / "partnership-intelligence-state.json", state)
    save(data / "partnership-intelligence-latest.json", report)
    return {"status": "BASELINE" if first_run else "RESEARCH_ONLY",
            "new_events": report["new_events"], "manual_review": len(report["manual_review"]),
            "errors": len(errors)}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
