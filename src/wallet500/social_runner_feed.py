from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

MODE = "RESEARCH_ONLY_SOCIAL_RUNNER_NATIVE_FEED_V1"
WINDOWS = {"3h": 3, "24h": 24, "3d": 72, "7d": 168, "21d": 504}


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        out = datetime.fromisoformat(text)
    except ValueError:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def _event_time(row: Mapping[str, Any]) -> datetime | None:
    return _dt(row.get("published_at")) or _dt(row.get("first_seen_by_wallet500"))


def _community(row: Mapping[str, Any]) -> str:
    source = str(row.get("source") or "unknown").strip().lower()
    author = str(row.get("author") or "unknown").strip().lower()
    return f"{source}:{author}"


def _platform(row: Mapping[str, Any]) -> str | None:
    source = str(row.get("source") or "").strip().lower()
    if source in {"twitter", "x", "x.com"}:
        return "x"
    if "telegram" in source:
        return "telegram"
    if "reddit" in source:
        return "reddit"
    return None


def _is_organic(row: Mapping[str, Any]) -> bool:
    # Fail conservative: explicit project ownership or paid/incentivized evidence
    # removes organic credit. Unknown flags do not become positive evidence by
    # themselves; the event still needs exact-token attribution from the ledger.
    return not any(
        row.get(key) is True
        for key in ("project_owned", "paid", "sponsored", "incentivized")
    )


def _normalized_text(row: Mapping[str, Any]) -> str:
    text = str(row.get("text") or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _coordination_ratio(rows: Iterable[Mapping[str, Any]]) -> float:
    texts = [_normalized_text(r) for r in rows]
    texts = [t for t in texts if len(t) >= 12]
    if not texts:
        return 0.0
    counts = Counter(texts)
    coordinated = sum(max(0, count - 1) for count in counts.values())
    return coordinated / len(texts)


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _identity_map(social_intelligence: Mapping[str, Any]) -> dict[tuple[str, str], dict]:
    network_default = str(social_intelligence.get("network") or "").lower()
    out: dict[tuple[str, str], dict] = {}
    for row in social_intelligence.get("tokens") or []:
        if not isinstance(row, Mapping):
            continue
        contract = str(row.get("token_address") or row.get("contract") or "").strip()
        if not contract:
            continue
        chain = str(row.get("chain") or network_default or "unknown").lower()
        out[(chain, contract.lower())] = dict(row)
    return out


def _organic_map(organic_acceleration: Mapping[str, Any]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for row in organic_acceleration.get("tokens") or []:
        if not isinstance(row, Mapping):
            continue
        chain = str(row.get("chain") or "unknown").lower()
        contract = str(row.get("contract") or "").strip().lower()
        if contract:
            out[(chain, contract)] = dict(row)
    return out


def build_native_snapshots(
    ledger: Mapping[str, Any],
    social_intelligence: Mapping[str, Any] | None = None,
    organic_acceleration: Mapping[str, Any] | None = None,
    active_within_hours: float = 3.0,
) -> list[dict]:
    """Convert the immutable exact-token social ledger into no-hindsight t0 snapshots.

    Each token's t0 is its latest observed social event. Window counts are rebuilt
    strictly from events at-or-before that t0. This keeps later ledger observations
    from leaking into earlier snapshots.
    """
    social_intelligence = social_intelligence or {}
    organic_acceleration = organic_acceleration or {}
    identities = _identity_map(social_intelligence)
    organic_rows = _organic_map(organic_acceleration)

    ledger_now = _dt(ledger.get("updated_at")) or datetime.now(timezone.utc)
    grouped: dict[tuple[str, str], list[tuple[datetime, Mapping[str, Any]]]] = defaultdict(list)
    for row in ledger.get("events") or []:
        if not isinstance(row, Mapping):
            continue
        chain = str(row.get("chain") or "unknown").strip().lower()
        contract = str(row.get("contract") or row.get("token_address") or "").strip()
        ts = _event_time(row)
        if not contract or ts is None or ts > ledger_now:
            continue
        grouped[(chain, contract.lower())].append((ts, row))

    snapshots: list[dict] = []
    for key, all_events in grouped.items():
        all_events.sort(key=lambda item: item[0])
        t0 = all_events[-1][0]
        if ledger_now - t0 > timedelta(hours=active_within_hours):
            continue

        eligible = [(ts, row) for ts, row in all_events if ts <= t0]
        windows: dict[str, dict] = {}
        window_rows: dict[str, list[Mapping[str, Any]]] = {}
        for label, hours in WINDOWS.items():
            start = t0 - timedelta(hours=hours)
            rows = [row for ts, row in eligible if ts >= start]
            window_rows[label] = rows
            # Native Wallet500 sources do not claim a stable indexed-community
            # universe. Leave indexed_communities absent rather than fabricating
            # TGMetrics-style coverage.
            windows[label] = {"mentions": len(rows), "indexed_communities": None}

        current_3h = window_rows["3h"]
        if not current_3h:
            continue
        current_24h = window_rows["24h"]
        organic_24h = [row for row in current_24h if _is_organic(row)]
        communities_24h = {_community(row) for row in current_24h}

        first_seen_by_community: dict[str, datetime] = {}
        for ts, row in eligible:
            community = _community(row)
            if community not in first_seen_by_community or ts < first_seen_by_community[community]:
                first_seen_by_community[community] = ts
        first_time_communities = sum(
            1
            for community in communities_24h
            if first_seen_by_community.get(community) is not None
            and first_seen_by_community[community] >= t0 - timedelta(hours=24)
        )

        platforms = Counter()
        for row in current_24h:
            platform = _platform(row)
            if platform:
                platforms[platform] += 1

        organic_meta = organic_rows.get(key) or {}
        contamination = organic_meta.get("contamination_ratio_24h")
        try:
            contamination_ratio = max(0.0, min(1.0, float(contamination)))
        except (TypeError, ValueError):
            contamination_ratio = 0.0
        coordination_ratio = max(_coordination_ratio(current_24h), contamination_ratio)

        identity = identities.get(key) or {}
        coverage = identity.get("coverage") if isinstance(identity.get("coverage"), Mapping) else {}
        catalysts = identity.get("catalysts") if isinstance(identity.get("catalysts"), Mapping) else {}
        positive_catalysts = catalysts.get("positive") if isinstance(catalysts.get("positive"), list) else []
        catalyst_confirmed = bool(positive_catalysts and int(coverage.get("news_events") or 0) > 0)

        followers = []
        for row in current_24h:
            try:
                value = float(row.get("followers"))
            except (TypeError, ValueError):
                continue
            if value >= 0:
                followers.append(value)

        snapshots.append(
            {
                "observed_at": t0.isoformat(),
                "chain": key[0],
                "contract": str(all_events[-1][1].get("contract") or all_events[-1][1].get("token_address") or ""),
                "symbol": identity.get("symbol"),
                "windows": windows,
                "raw_mentions_24h": len(current_24h),
                "organic_mentions_24h": len(organic_24h),
                "organic_share": (len(organic_24h) / len(current_24h)) if current_24h else None,
                "unique_communities": len(communities_24h),
                "first_time_communities": first_time_communities,
                "platform_mentions": {
                    "telegram": platforms.get("telegram", 0),
                    "x": platforms.get("x", 0),
                    "reddit": platforms.get("reddit", 0),
                },
                "coordination_ratio": coordination_ratio,
                "reach_current": sum(followers) if followers else None,
                "reach_baseline": None,
                "catalyst_confirmed": catalyst_confirmed,
                "market": {},
                "onchain": {},
                "source": "WALLET500_IMMUTABLE_SOCIAL_LEDGER",
                "native_feed_truth": {
                    "exact_token_ledger": True,
                    "no_hindsight": True,
                    "indexed_community_universe_known": False,
                    "missing_market_confirmation_is_unknown_not_zero": True,
                    "missing_onchain_confirmation_is_unknown_not_zero": True,
                },
            }
        )

    snapshots.sort(key=lambda row: str(row.get("observed_at") or ""), reverse=True)
    return snapshots


def build_feed(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    ledger = _load(data / "social-catalyst-ledger.json", {})
    intelligence = _load(data / "social-intelligence-v2.json", {})
    organic = _load(data / "social-organic-acceleration.json", {})
    existing = _load(data / "social-runner-research-feed.json", {})

    native = build_native_snapshots(ledger, intelligence, organic)
    external_snapshots = []
    historical_events = []
    if isinstance(existing, Mapping):
        historical_events = existing.get("historical_events") if isinstance(existing.get("historical_events"), list) else []
        for row in existing.get("snapshots") or []:
            if isinstance(row, Mapping) and str(row.get("source") or "") != "WALLET500_IMMUTABLE_SOCIAL_LEDGER":
                external_snapshots.append(dict(row))

    deduped: dict[str, dict] = {}
    for row in [*external_snapshots, *native]:
        key = ":".join(
            [
                str(row.get("chain") or "").lower(),
                str(row.get("contract") or row.get("token_address") or "").lower(),
                str(row.get("observed_at") or ""),
                str(row.get("source") or ""),
            ]
        )
        deduped[key] = row

    payload = {
        "version": 1,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "sources": {
            "wallet500_native_ledger": len(native),
            "external_supplied_snapshots": len(external_snapshots),
            "historical_events": len(historical_events),
        },
        "snapshots": list(deduped.values()),
        "historical_events": historical_events,
        "truth_contract": {
            "native_events_are_exact_token_ledger_evidence": True,
            "raw_mentions_are_not_buy_signals": True,
            "project_owned_paid_sponsored_incentivized_get_no_organic_credit": True,
            "missing_indexed_community_universe_is_not_fabricated": True,
            "tgmetrics_private_beta_must_be_supplied_through_licensed_external_feed": True,
            "no_undocumented_tgmetrics_scraping": True,
        },
    }
    path = data / "social-runner-research-feed.json"
    _write(path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_feed(), indent=2))
