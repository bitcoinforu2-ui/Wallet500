from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wallet500.social_telegram_truth_hardening import parse_public_telegram_html
CFG = ROOT / "data/alpha-caller-sources.json"
STATE = ROOT / "data/alpha-caller-source-state.json"
INBOX = ROOT / "data/alpha-caller-inbox.json"
UA = "Wallet500-PublicAlphaCollector/1.2"

SOL_LINK = re.compile(r"(?:/terminal/solana/|/t/)([1-9A-HJ-NP-Za-km-z]{32,44})")
EVM_LINK = re.compile(
    r"/terminal/(ethereum|eth|base|arbitrum|bsc|optimism|polygon|arc)/(0x[a-fA-F0-9]{40})"
)
EVM_GENERIC_LINK = re.compile(r"/t/(0x[a-fA-F0-9]{40})")
SOL_RAW = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])([1-9A-HJ-NP-Za-km-z]{32,44})(?![1-9A-HJ-NP-Za-km-z])")
EVM_RAW = re.compile(r"(?<![0-9a-fA-F])(0x[a-fA-F0-9]{40})(?![0-9a-fA-F])")
TAG = re.compile(r"<[^>]+>")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def text(url: str, timeout: int = 15) -> str | None:
    try:
        with urlopen(
            Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}),
            timeout=timeout,
        ) as r:
            return r.read().decode("utf-8", "ignore")
    except (HTTPError, URLError, TimeoutError, OSError):
        return None


def plain_text(body: str) -> str:
    return html.unescape(TAG.sub(" ", body))


def dedupe_preserve(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for network, contract in rows:
        key = (network, contract.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((network, contract))
    return out


def extract_candidates(body: str, source: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for m in EVM_LINK.finditer(body):
        network = "eth" if m.group(1) in {"eth", "ethereum"} else m.group(1)
        rows.append((network, m.group(2)))
    rows.extend(("evm", m.group(1)) for m in EVM_GENERIC_LINK.finditer(body))
    rows.extend(("solana", m.group(1)) for m in SOL_LINK.finditer(body))
    if source.get("extract_raw_contracts"):
        visible = plain_text(body)
        rows.extend(("evm", m.group(1)) for m in EVM_RAW.finditer(visible))
        # EVM hex addresses contain long Base58-compatible substrings beginning at
        # the "x" in "0x...". Remove exact EVM addresses before scanning for raw
        # Solana mints so one post cannot fabricate a second cross-chain identity.
        visible_without_evm = EVM_RAW.sub(" ", visible)
        rows.extend(("solana", m.group(1)) for m in SOL_RAW.finditer(visible_without_evm))
    return dedupe_preserve(rows)



def parse_time(value: object) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def telegram_handle(url: object) -> str | None:
    try:
        parsed = urlparse(str(url or ""))
        if parsed.netloc.lower() not in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
            return None
        parts = [x for x in parsed.path.split("/") if x]
        if parts and parts[0].lower() == "s":
            parts = parts[1:]
        if not parts or parts[0].startswith("+"):
            return None
        return parts[0].lstrip("@")
    except Exception:
        return None


def normalize_caller(value: object) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"\s+", " ", raw).strip(" \t\r\n-|:")
    return raw[:120]


def caller_from_message(message_text: str, source: dict) -> str:
    fallback = str(source.get("caller_name") or source.get("name") or source.get("id") or "UNKNOWN")
    if not source.get("parse_caller_from_text"):
        return normalize_caller(fallback)
    text_value = html.unescape(str(message_text or ""))
    patterns = (
        r"(?:^|\n)\s*(?:⚡\s*)?Caller\s*:\s*([^\n|]{2,120})",
        r"(?:first\s+call|called)\s+from\s*:\s*\n?\s*([^\n|]{2,120})",
        r"\bfrom\s*:\s*\n?\s*(?:⚡\s*Caller\s*:\s*)?([^\n|]{2,120})",
    )
    for pattern in patterns:
        match = re.search(pattern, text_value, flags=re.I)
        if match:
            candidate = normalize_caller(match.group(1))
            candidate = re.split(r"\s+(?:Avg\s+CPW|CPW|Score|at\s+\$|MC|MCap)\s*[:=]?", candidate, maxsplit=1, flags=re.I)[0].strip()
            if 2 <= len(candidate) <= 120:
                return candidate
    return normalize_caller(fallback)


def source_metadata(source: dict) -> dict:
    return {
        "source_class": str(source.get("source_class") or "direct_source"),
        "independence_group": str(source.get("independence_group") or "caller_identity"),
        "historical_evidence_grade": str(source.get("historical_evidence_grade") or "UNVERIFIED_FORWARD_LEARNING"),
        "discovery_priority": str(source.get("priority") or "NORMAL"),
    }


def telegram_discoveries(body: str, source: dict, observed_at: str) -> tuple[list[dict], dict]:
    handle = telegram_handle(source.get("url"))
    if not handle:
        return [], {"status": "NOT_PUBLIC_TELEGRAM"}
    posts, dropped_untimestamped = parse_public_telegram_html(body, handle, limit=int(source.get("telegram_post_limit") or 100))
    observed_dt = parse_time(observed_at) or datetime.now(timezone.utc)
    max_age = max(1, int(source.get("max_live_age_minutes") or 180))
    rows: list[dict] = []
    stale = 0
    for post in posts:
        published = parse_time(post.get("published_at"))
        if published is None:
            continue
        age_minutes = max(0.0, (observed_dt - published).total_seconds() / 60.0)
        caller = caller_from_message(str(post.get("text") or ""), source)
        for network, contract in extract_candidates(str(post.get("text") or ""), source):
            rows.append(
                {
                    "network": network,
                    "contract": contract,
                    "caller": caller,
                    "called_at": published.isoformat(),
                    "source_post_id": post.get("id"),
                    "source_post_url": post.get("url"),
                    "age_minutes": age_minutes,
                    "live_eligible": age_minutes <= max_age,
                    "timestamp_semantics": "TELEGRAM_ORIGINAL_DATETIME",
                }
            )
            if age_minutes > max_age:
                stale += 1
    return rows, {
        "status": "OK",
        "posts": len(posts),
        "candidate_rows": len(rows),
        "stale_candidate_rows": stale,
        "dropped_untimestamped": dropped_untimestamped,
        "max_live_age_minutes": max_age,
        "timestamp_semantics": "TELEGRAM_ORIGINAL_DATETIME",
    }

def main() -> None:
    cfg = json.loads(CFG.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {"sources": {}, "seen_contracts": {}}
    inbox = json.loads(INBOX.read_text()) if INBOX.exists() else {"version": 1, "calls": []}
    calls = inbox.setdefault("calls", [])
    existing = {
        (
            str(x.get("source_id") or x.get("source")),
            str(x.get("caller") or "").lower(),
            str(x.get("network")),
            str(x.get("contract")).lower(),
        )
        for x in calls
    }
    seen = state.setdefault("seen_contracts", {})
    prior_source_state = state.setdefault("sources", {})
    added = 0
    health: dict[str, dict] = {}

    for source in cfg.get("sources") or []:
        if not source.get("enabled"):
            continue

        sid = str(source["id"])
        observed = now()
        body = text(str(source["url"]))
        if body is None:
            health[sid] = {"status": "ERROR", "observed_at": observed}
            continue

        handle = telegram_handle(source.get("url"))
        accepted = 0
        historical_suppressed = 0
        backfill_suppressed = 0
        source_name = str(source.get("name") or sid)
        role = str(source.get("signal_role") or "candidate_discovery")
        metadata = source_metadata(source)

        if handle:
            discoveries, telegram_health = telegram_discoveries(body, source, observed)
            max_new = max(1, int(source.get("max_new_per_scan") or 25))
            unseen: list[dict] = []
            for item in discoveries:
                caller = str(item["caller"])
                key = f"{sid}:{caller.lower()}:{item['network']}:{item['contract'].lower()}"
                if key in seen:
                    continue
                seen[key] = {
                    "first_seen_at": observed,
                    "original_published_at": item["called_at"],
                    "source_url": item.get("source_post_url") or source["url"],
                    "caller": caller,
                    "live_eligible": bool(item["live_eligible"]),
                }
                if item["live_eligible"]:
                    unseen.append(item)
                else:
                    historical_suppressed += 1

            selected = unseen[-max_new:]
            backfill_suppressed = max(0, len(unseen) - len(selected))
            for item in selected:
                caller = str(item["caller"])
                ek = (sid, caller.lower(), str(item["network"]), str(item["contract"]).lower())
                if ek in existing:
                    continue
                independence_key = (
                    f"alpha-origin:{item['network']}:{str(item['contract']).lower()}:{caller.lower()}"
                )
                row = {
                    "caller": caller,
                    "origin_caller": caller,
                    "source": source_name,
                    "contract": item["contract"],
                    "network": item["network"],
                    "called_at": item["called_at"],
                    "source_url": item.get("source_post_url") or source["url"],
                    "source_post_id": item.get("source_post_id"),
                    "caller_strength": float(source.get("initial_strength") or 25),
                    "caller_confidence": min(
                        45.0, float(source.get("confidence_cap") or 45)
                    ),
                    "timestamp_semantics": item["timestamp_semantics"],
                    "discovery_only": True,
                    "signal_role": role,
                    "source_id": sid,
                    "independence_key": independence_key,
                    **metadata,
                }
                calls.append(row)
                existing.add(ek)
                added += 1
                accepted += 1

            health[sid] = {
                "status": telegram_health["status"],
                "observed_at": observed,
                "raw_candidates": telegram_health["candidate_rows"],
                "new_discoveries": accepted,
                "historical_suppressed": historical_suppressed,
                "backfill_suppressed": backfill_suppressed,
                "timestamp_semantics": telegram_health["timestamp_semantics"],
                "dropped_untimestamped": telegram_health["dropped_untimestamped"],
                "max_live_age_minutes": telegram_health["max_live_age_minutes"],
                "signal_role": role,
                "source_class": metadata["source_class"],
                "first_scan": sid not in prior_source_state,
            }
            continue

        candidates = extract_candidates(body, source)
        unseen_pairs = [
            (network, contract)
            for network, contract in candidates
            if f"{sid}:{network}:{contract.lower()}" not in seen
        ]
        max_new = max(1, int(source.get("max_new_per_scan") or 250))
        selected_pairs = unseen_pairs[-max_new:]
        selected_keys = {(n, c.lower()) for n, c in selected_pairs}

        for network, contract in unseen_pairs:
            key = f"{sid}:{network}:{contract.lower()}"
            seen[key] = {
                "first_seen_at": observed,
                "source_url": source["url"],
                "ingested": (network, contract.lower()) in selected_keys,
            }

        caller = normalize_caller(source.get("caller_name") or source_name)
        for network, contract in selected_pairs:
            ek = (sid, caller.lower(), network, contract.lower())
            if ek in existing:
                continue
            row = {
                "caller": caller,
                "origin_caller": caller,
                "source": source_name,
                "contract": contract,
                "network": network,
                "called_at": observed,
                "source_url": source["url"],
                "caller_strength": float(source.get("initial_strength") or 25),
                "caller_confidence": min(45.0, float(source.get("confidence_cap") or 45)),
                "timestamp_semantics": "WALLET500_FIRST_SEEN_NOT_ORIGINAL_CALL",
                "discovery_only": True,
                "signal_role": role,
                "source_id": sid,
                "independence_key": f"alpha-origin:{network}:{contract.lower()}:{caller.lower()}",
                **metadata,
            }
            calls.append(row)
            existing.add(ek)
            added += 1
            accepted += 1

        health[sid] = {
            "status": "OK",
            "observed_at": observed,
            "raw_candidates": len(candidates),
            "unseen_contracts": len(unseen_pairs),
            "new_discoveries": accepted,
            "backfill_suppressed": max(0, len(unseen_pairs) - len(selected_pairs)),
            "timestamp_semantics": "wallet500_first_seen",
            "signal_role": role,
            "source_class": metadata["source_class"],
            "first_scan": sid not in prior_source_state,
        }

    if len(calls) > 4000:
        inbox["calls"] = calls[-4000:]
    inbox["updated_at"] = now()
    INBOX.write_text(json.dumps(inbox, indent=2, ensure_ascii=False) + "\n")
    state["updated_at"] = now()
    state["sources"] = health
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "status": "OK",
                "new_public_discoveries": added,
                "sources": health,
                "free_only": True,
                "telegram_original_timestamps_required": True,
                "historical_messages_never_promoted_as_fresh": True,
            }
        )
    )


if __name__ == "__main__":
    main()
