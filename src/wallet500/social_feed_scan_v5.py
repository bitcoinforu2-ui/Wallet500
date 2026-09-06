from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import social_direct_providers as direct
from . import social_feed_scan as base
from . import social_feed_scan_v2 as v2
from . import social_feed_scan_v4 as v4

MODE = base.MODE
CACHE_FILE = "social-identity-cache.json"
CACHE_TTL_HOURS = 24
STALE_CACHE_MAX_DAYS = 7
IDENTITY_FIELDS = (
    "coingecko_id",
    "official_x",
    "official_telegram",
    "official_discord",
    "official_website",
    "official_reddit",
    "github_repos",
)

_BASE_IDENTITY = v2._ORIGINAL_IDENTITY
_BASE_FALLBACK = v2._fallback
_BASE_REDDIT = direct.scan_reddit
_CACHE_ITEMS: dict[str, dict] = {}
_CACHE_STATS = {"seeded": 0, "hits": 0, "fresh_fetches": 0, "stale_fallbacks": 0}


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_ts(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _cache_key(coin: dict) -> str | None:
    coin_id = str(coin.get("id") or coin.get("coingecko_id") or "").strip()
    if coin_id:
        return "cg:" + coin_id
    token = str(coin.get("token_address") or "").strip()
    return "token:" + token if token else None


def _identity_snapshot(identity: dict) -> dict:
    return {key: identity.get(key) for key in IDENTITY_FIELDS if identity.get(key) not in (None, "", [])}


def _merge_cached_identity(identity: dict, cached: dict) -> dict:
    merged = dict(identity or {})
    for key in IDENTITY_FIELDS:
        value = cached.get(key)
        if value not in (None, "", []):
            merged[key] = value
    return merged


def _entry_age(entry: dict, now: datetime) -> timedelta | None:
    ts = _parse_ts(entry.get("fetched_at"))
    return None if ts is None else now - ts


def _seed_identity_cache(data_dir: Path) -> None:
    global _CACHE_ITEMS
    _CACHE_STATS.update({"seeded": 0, "hits": 0, "fresh_fetches": 0, "stale_fallbacks": 0})
    cached = _load(data_dir / CACHE_FILE, {})
    items = cached.get("items") if isinstance(cached, dict) else {}
    _CACHE_ITEMS = dict(items) if isinstance(items, dict) else {}

    previous = _load(data_dir / base.OUTPUT.name, {})
    observed_at = str(previous.get("generated_at") or datetime.now(timezone.utc).isoformat())
    for target in previous.get("targets") or []:
        if not isinstance(target, dict):
            continue
        identity = target.get("identity") if isinstance(target.get("identity"), dict) else {}
        ok = any(
            isinstance(status, dict)
            and status.get("provider") == "coingecko_identity"
            and str(status.get("status") or "").startswith("OK")
            for status in target.get("provider_status") or []
        )
        if not ok:
            continue
        key = _cache_key({
            "id": identity.get("coingecko_id"),
            "token_address": target.get("token_address"),
        })
        snapshot = _identity_snapshot(identity)
        if key and snapshot and key not in _CACHE_ITEMS:
            _CACHE_ITEMS[key] = {"fetched_at": observed_at, "identity": snapshot}
            _CACHE_STATS["seeded"] += 1


def _identity_cached(coin: dict):
    now = datetime.now(timezone.utc)
    key = _cache_key(coin)
    entry = _CACHE_ITEMS.get(key or "") if key else None
    age = _entry_age(entry, now) if isinstance(entry, dict) else None
    cached_identity = (entry or {}).get("identity") if isinstance(entry, dict) else None

    if isinstance(cached_identity, dict) and age is not None and age <= timedelta(hours=CACHE_TTL_HOURS):
        reduced = dict(coin)
        reduced["id"] = None
        reduced["coingecko_id"] = None
        identity, statuses = _BASE_IDENTITY(reduced)
        identity = _merge_cached_identity(identity, cached_identity)
        statuses = list(statuses or [])
        statuses.append({
            "provider": "coingecko_identity",
            "status": "OK_CACHE",
            "cache_age_minutes": round(age.total_seconds() / 60, 1),
            "cache_ttl_hours": CACHE_TTL_HOURS,
        })
        _CACHE_STATS["hits"] += 1
        return identity, statuses

    identity, statuses = _BASE_IDENTITY(coin)
    identity = dict(identity or {})
    statuses = [dict(x) for x in (statuses or []) if isinstance(x, dict)]
    cg_rows = [x for x in statuses if x.get("provider") == "coingecko_identity"]
    cg_ok = any(str(x.get("status") or "").startswith("OK") for x in cg_rows)
    cg_failed = any(
        str(x.get("status") or "").startswith(("HTTP_", "CIRCUIT_BREAKER_"))
        or "ERROR" in str(x.get("status") or "")
        for x in cg_rows
    )

    if cg_ok and key:
        snapshot = _identity_snapshot(identity)
        if snapshot:
            _CACHE_ITEMS[key] = {"fetched_at": now.isoformat(), "identity": snapshot}
            _CACHE_STATS["fresh_fetches"] += 1
    elif (
        cg_failed
        and isinstance(cached_identity, dict)
        and age is not None
        and age <= timedelta(days=STALE_CACHE_MAX_DAYS)
    ):
        identity = _merge_cached_identity(identity, cached_identity)
        rewritten = []
        for row in statuses:
            if row.get("provider") == "coingecko_identity":
                direct_status = str(row.get("status") or "UNKNOWN")
                if direct_status.startswith(("HTTP_", "CIRCUIT_BREAKER_")) or "ERROR" in direct_status:
                    row = {
                        "provider": "coingecko_identity",
                        "status": "DEGRADED_STALE_CACHE_FALLBACK",
                        "direct_status": direct_status,
                        "cache_age_hours": round(age.total_seconds() / 3600, 2),
                        "meaning": "OPTIONAL_METADATA_RECOVERED_FROM_PREVIOUS_VERIFIED_IDENTITY",
                    }
            rewritten.append(row)
        statuses = rewritten
        _CACHE_STATS["stale_fallbacks"] += 1
    return identity, statuses


def _strip_markup(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _reddit_rss(identity: dict):
    query = direct.direct_query(identity, "reddit")
    if not query:
        return [], {"provider": "reddit", "status": "NO_QUERY_IDENTITY"}
    params = urlencode({"q": query, "sort": "new", "t": "day"})
    user_agent = (os.getenv("REDDIT_USER_AGENT") or "Wallet500/5.0 by bitcoinforu2-ui").strip()
    endpoints = (
        "https://www.reddit.com/search.rss?" + params,
        "https://old.reddit.com/search.rss?" + params,
    )
    errors: list[str] = []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for endpoint in endpoints:
        try:
            req = Request(
                endpoint,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "application/atom+xml,application/rss+xml,text/xml;q=0.9,*/*;q=0.1",
                },
            )
            with urlopen(req, timeout=16) as response:
                raw = response.read()
            root = ET.fromstring(raw)
            rows = []
            entries = root.findall(".//a:entry", ns)
            for item in entries[:25]:
                title = str(item.findtext("a:title", default="", namespaces=ns) or "")
                content = str(item.findtext("a:content", default="", namespaces=ns) or "")
                author = str(item.findtext("a:author/a:name", default="", namespaces=ns) or "")
                published = str(
                    item.findtext("a:updated", default="", namespaces=ns)
                    or item.findtext("a:published", default="", namespaces=ns)
                    or ""
                ) or None
                link_el = item.find("a:link", ns)
                link = link_el.get("href") if link_el is not None else None
                entry_id = str(item.findtext("a:id", default="", namespaces=ns) or link or title)
                rows.append({
                    "source": "reddit",
                    "id": entry_id,
                    "author": author or "reddit",
                    "published_at": published,
                    "text": _strip_markup(f"{title} {content}")[:1500],
                    "url": link,
                    "direct_provider": True,
                    "transport": "PUBLIC_RSS",
                })
            return rows, {
                "provider": "reddit",
                "status": "OK_DIRECT_PUBLIC_RSS",
                "count": len(rows),
                "query_identity": "MINT_PAIR_BROAD",
            }
        except HTTPError as exc:
            errors.append(f"HTTP_{exc.code}")
        except URLError:
            errors.append("NETWORK_UNAVAILABLE")
        except Exception as exc:
            errors.append(type(exc).__name__)
    return [], {"provider": "reddit", "status": errors[0] if errors else "RSS_UNAVAILABLE", "rss_errors": errors[:2]}


def _scan_reddit_multi(identity: dict):
    rows, status = _BASE_REDDIT(identity)
    direct_status = str((status or {}).get("status") or "UNKNOWN")
    if direct_status.startswith("OK"):
        return rows, status
    rss_rows, rss_status = _reddit_rss(identity)
    if str((rss_status or {}).get("status") or "").startswith("OK"):
        rss_status = dict(rss_status or {})
        rss_status["json_status"] = direct_status
        return rss_rows, rss_status
    merged_status = dict(status or {})
    merged_status["rss_status"] = (rss_status or {}).get("status")
    return rows, merged_status


def _fallback_truthful(direct_fn, identity: dict, provider: str, source: str, sites: str):
    events, status = _BASE_FALLBACK(direct_fn, identity, provider, source, sites)
    status = dict(status or {})
    status_text = str(status.get("status") or "UNKNOWN")
    index_status = str(status.get("index_status") or "")
    if status_text == "FALLBACK_INDEX_OK_CONTEXT_ONLY":
        status["health_semantic"] = "AMBER_DEGRADED_RECOVERED"
        status["direct_evidence"] = False
        return events, status
    if index_status == "INDEX_OK" and not status_text.startswith("OK"):
        return [], {
            "provider": provider,
            "status": "DEGRADED_INDEX_OK_NO_MATCHES",
            "count": 0,
            "direct_status": status_text,
            "index_status": "INDEX_OK",
            "health_semantic": "AMBER_DEGRADED_RECOVERED",
            "meaning": "DIRECT_UNAVAILABLE_BUT_INDEX_REACHABLE_NO_MATCHES_UNKNOWN_NOT_ZERO",
        }
    return events, status


def _status_is_optional_or_partial(status: str) -> bool:
    value = status.upper()
    return any(term in value for term in (
        "NOT_CONFIGURED",
        "AUTH_REQUIRED",
        "PRIVATE_OR_INVITE",
        "NO_OFFICIAL_PUBLIC_CHANNEL",
        "SKIPPED_DIRECT_BUDGET",
        "FALLBACK_INDEX_OK",
        "DEGRADED_INDEX_OK",
        "INDEX_OK_CONTEXT_ONLY",
        "STALE_CACHE_FALLBACK",
        "CONTEXT_ONLY",
    ))


def _status_is_failure(status: str) -> bool:
    value = status.upper()
    return (
        value.startswith("HTTP_")
        or value.startswith("CIRCUIT_BREAKER_")
        or "NETWORK_UNAVAILABLE" in value
        or "ERROR" in value
    )


def _provider_light(provider: str, row: dict) -> tuple[str, str]:
    statuses = [str(x) for x in (row.get("statuses") or [])]
    state = str(row.get("state") or "UNKNOWN")
    configured = bool(row.get("configured"))
    if provider == "social_mesh_public_index":
        return "AMBER", "PUBLIC_INDEX_CONTEXT_ONLY_NOT_DIRECT_EVIDENCE"
    if state in {"ACTIVE_EXACT_EVIDENCE", "ACTIVE_OFFICIAL_CONTEXT"}:
        return "GREEN", "DIRECT_OR_VERIFIED_OFFICIAL_EVIDENCE_ACTIVE"
    direct_ok = any(s.startswith("OK_DIRECT") or s == "OK" or s.startswith("OK_CACHE") for s in statuses)
    partial = any(_status_is_optional_or_partial(s) for s in statuses)
    failure = any(_status_is_failure(s) for s in statuses)
    if direct_ok and not failure:
        return "GREEN", "SOURCE_REACHABLE_DIRECT"
    if state == "INDEX_CONTEXT_ONLY" or partial or not configured:
        return "AMBER", "PARTIAL_RECOVERED_OR_OPTIONAL_CONFIGURATION"
    if failure:
        return "RED", "EXPECTED_SOURCE_FAILED_WITHOUT_USABLE_RECOVERY"
    if state == "ACTIVE_NO_EXACT_EVIDENCE":
        return "GREEN", "SOURCE_REACHABLE_NO_EXACT_MATCH_THIS_RUN"
    return "AMBER", "UNKNOWN_NOT_ZERO"


def _apply_health_lights(payload: dict) -> dict:
    health = payload.get("source_health") if isinstance(payload.get("source_health"), dict) else {}
    providers = health.get("providers") if isinstance(health.get("providers"), dict) else {}
    lights = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for provider, row in providers.items():
        if not isinstance(row, dict):
            continue
        light, reason = _provider_light(str(provider), row)
        row["traffic_light"] = light
        row["traffic_reason"] = reason
        row["red_means_no_usable_fallback"] = True
        lights[light] = lights.get(light, 0) + 1
    health["traffic_light_summary"] = lights
    truth = health.get("truth") if isinstance(health.get("truth"), dict) else {}
    truth["traffic_light_is_observability_only"] = True
    truth["not_configured_is_amber_not_failure"] = True
    truth["fallback_recovered_is_amber_not_green"] = True
    truth["red_requires_expected_failure_without_usable_recovery"] = True
    health["truth"] = truth
    payload["source_health"] = health
    return lights


def _raw_status_semantics(payload: dict) -> dict:
    counts = payload.get("provider_status_counts") if isinstance(payload.get("provider_status_counts"), dict) else {}
    recovered = set()
    for key in counts:
        provider, _, status = str(key).partition(":")
        if any(term in status for term in ("FALLBACK_INDEX_OK", "DEGRADED_INDEX_OK", "INDEX_OK_CONTEXT_ONLY")):
            recovered.add(provider)
    rows = []
    summary = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for key, count in sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0]))):
        provider, _, status = str(key).partition(":")
        upper = status.upper()
        if _status_is_optional_or_partial(status):
            light = "AMBER"
            reason = "OPTIONAL_OR_DEGRADED_RECOVERED"
        elif status.startswith("OK"):
            light = "GREEN"
            reason = "DIRECT_OR_OFFICIAL_SOURCE_OK"
        elif _status_is_failure(status):
            if provider in recovered:
                light = "AMBER"
                reason = "DIRECT_FAILURE_WITH_INDEX_RECOVERY"
            else:
                light = "RED"
                reason = "FAILURE_WITHOUT_RECOVERY"
        elif "INDEX_OK" in upper:
            light = "AMBER"
            reason = "CONTEXT_ONLY"
        else:
            light = "AMBER"
            reason = "UNKNOWN_NOT_ZERO"
        summary[light] += int(count or 0)
        rows.append({"key": key, "provider": provider, "status": status, "targets": int(count or 0), "traffic_light": light, "reason": reason})
    return {"summary_by_target_status": summary, "rows": rows}


def _persist_cache(data_dir: Path, generated_at: str) -> None:
    _write(data_dir / CACHE_FILE, {
        "version": 1,
        "updated_at": generated_at,
        "ttl_hours": CACHE_TTL_HOURS,
        "stale_fallback_max_days": STALE_CACHE_MAX_DAYS,
        "secret_values_stored": False,
        "items": _CACHE_ITEMS,
    })


def run(output_dir: str | Path = "data") -> dict:
    data_dir = Path(output_dir)
    _seed_identity_cache(data_dir)
    original_identity = v2._ORIGINAL_IDENTITY
    original_fallback = v2._fallback
    original_reddit = direct.scan_reddit
    v2._ORIGINAL_IDENTITY = _identity_cached
    v2._fallback = _fallback_truthful
    direct.scan_reddit = _scan_reddit_multi
    try:
        payload = v4.run(data_dir)
    finally:
        v2._ORIGINAL_IDENTITY = original_identity
        v2._fallback = original_fallback
        direct.scan_reddit = original_reddit

    generated_at = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())
    lights = _apply_health_lights(payload)
    payload["provider_status_semantics"] = _raw_status_semantics(payload)
    payload["provider_resilience"] = {
        "version": 1,
        "mode": "OBSERVABILITY_AND_TRANSPORT_RESILIENCE_ONLY",
        "production_effect": False,
        "automatic_buy": False,
        "traffic_light_summary": lights,
        "identity_cache": {
            "enabled": True,
            "ttl_hours": CACHE_TTL_HOURS,
            "stale_fallback_max_days": STALE_CACHE_MAX_DAYS,
            "items": len(_CACHE_ITEMS),
            **dict(_CACHE_STATS),
        },
        "reddit_transport_order": ["OAUTH", "PUBLIC_JSON", "PUBLIC_RSS", "PUBLIC_SEARCH_INDEX_CONTEXT_ONLY"],
        "truth": {
            "cache_never_overrides_exact_pair_identity": True,
            "stale_cache_is_optional_metadata_only": True,
            "index_recovery_never_counts_as_direct_organic_evidence": True,
            "not_configured_is_unknown_not_zero": True,
            "red_requires_failure_without_usable_recovery": True,
            "provider_health_never_modifies_token_scores": True,
            "provider_health_never_modifies_alert_gate": True,
        },
    }
    rules = list(payload.get("rules") or [])
    for rule in (
        "COINGECKO_OPTIONAL_IDENTITY_METADATA_USES_24H_VERIFIED_CACHE_BEFORE_NEW_API_CALL",
        "COINGECKO_STALE_CACHE_FALLBACK_NEVER_OVERRIDES_EXACT_DEX_PAIR_IDENTITY",
        "REDDIT_DIRECT_TRANSPORT_TRIES_OAUTH_PUBLIC_JSON_THEN_PUBLIC_RSS",
        "DIRECT_FAILURE_WITH_REACHABLE_INDEX_NO_MATCHES_IS_DEGRADED_UNKNOWN_NOT_RED_ZERO",
        "NOT_CONFIGURED_OPTIONAL_ENRICHMENT_IS_AMBER_UNKNOWN_NOT_ZERO",
        "RED_PROVIDER_HEALTH_REQUIRES_EXPECTED_FAILURE_WITHOUT_USABLE_RECOVERY",
    ):
        if rule not in rules:
            rules.append(rule)
    payload["rules"] = rules
    _persist_cache(data_dir, generated_at)
    base._write(data_dir / base.OUTPUT.name, payload)
    return payload


def self_test() -> None:
    assert _status_is_optional_or_partial("NOT_CONFIGURED") is True
    assert _status_is_optional_or_partial("FALLBACK_INDEX_OK_CONTEXT_ONLY") is True
    assert _status_is_failure("HTTP_429") is True
    assert _status_is_failure("CIRCUIT_BREAKER_HTTP_403") is True
    assert _provider_light("discord", {"state": "NOT_CONFIGURED", "configured": False, "statuses": ["NOT_CONFIGURED"]})[0] == "AMBER"
    assert _provider_light("youtube", {"state": "DEGRADED_UNKNOWN", "configured": True, "statuses": ["HTTP_429"]})[0] == "RED"
    assert _provider_light("youtube", {"state": "INDEX_CONTEXT_ONLY", "configured": True, "statuses": ["DEGRADED_INDEX_OK_NO_MATCHES"]})[0] == "AMBER"
    sample = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>x</id><title>AOBS token</title><updated>2026-09-06T17:00:00Z</updated><author><name>u/test</name></author><link href="https://www.reddit.com/r/test/comments/x"/><content type="html">hello</content></entry></feed>'''
    root = ET.fromstring(sample)
    assert len(root.findall(".//a:entry", {"a": "http://www.w3.org/2005/Atom"})) == 1
    print("social_feed_scan_v5 resilience self-test: OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    payload = run()
    print(json.dumps({
        "targets": payload.get("targets_scanned"),
        "provider_resilience": payload.get("provider_resilience"),
        "source_health_lights": ((payload.get("source_health") or {}).get("traffic_light_summary")),
        "direct_breakers": payload.get("direct_provider_circuit_breakers"),
        "mesh_breakers": payload.get("mesh_provider_circuit_breakers"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
