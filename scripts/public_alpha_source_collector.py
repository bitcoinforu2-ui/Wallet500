from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data/alpha-caller-sources.json"
STATE = ROOT / "data/alpha-caller-source-state.json"
INBOX = ROOT / "data/alpha-caller-inbox.json"
UA = "Wallet500-PublicAlphaCollector/1.2"

SOL_LINK = re.compile(r"(?:/terminal/solana/|/t/)([1-9A-HJ-NP-Za-km-z]{32,44})")
EVM_LINK = re.compile(
    r"(?:/terminal/(?:ethereum|eth|base|arbitrum|bsc|optimism|polygon)/|/t/)(0x[a-fA-F0-9]{40})"
)
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
    rows.extend(("eth", m.group(1)) for m in EVM_LINK.finditer(body))
    rows.extend(("solana", m.group(1)) for m in SOL_LINK.finditer(body))
    if source.get("extract_raw_contracts"):
        visible = plain_text(body)
        rows.extend(("evm", m.group(1)) for m in EVM_RAW.finditer(visible))
        rows.extend(("solana", m.group(1)) for m in SOL_RAW.finditer(visible))
    return dedupe_preserve(rows)


def main() -> None:
    cfg = json.loads(CFG.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {"sources": {}, "seen_contracts": {}}
    inbox = json.loads(INBOX.read_text()) if INBOX.exists() else {"version": 1, "calls": []}
    calls = inbox.setdefault("calls", [])
    existing = {
        (str(x.get("source")), str(x.get("network")), str(x.get("contract")).lower())
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

        candidates = extract_candidates(body, source)
        unseen = [
            (network, contract)
            for network, contract in candidates
            if f"{sid}:{network}:{contract.lower()}" not in seen
        ]
        max_new = max(1, int(source.get("max_new_per_scan") or 250))
        selected = unseen[-max_new:]
        selected_keys = {(n, c.lower()) for n, c in selected}

        # Mark the entire visible page as seen so the first scan does not create a stale backlog.
        for network, contract in unseen:
            key = f"{sid}:{network}:{contract.lower()}"
            seen[key] = {
                "first_seen_at": observed,
                "source_url": source["url"],
                "ingested": (network, contract.lower()) in selected_keys,
            }

        accepted = 0
        caller = str(source.get("caller_name") or source.get("name") or sid)
        source_name = str(source.get("name") or sid)
        role = str(source.get("signal_role") or "candidate_discovery")
        for network, contract in selected:
            row = {
                "caller": caller,
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
            }
            ek = (row["source"], network, contract.lower())
            if ek in existing:
                continue
            calls.append(row)
            existing.add(ek)
            added += 1
            accepted += 1

        health[sid] = {
            "status": "OK",
            "observed_at": observed,
            "raw_candidates": len(candidates),
            "unseen_contracts": len(unseen),
            "new_discoveries": accepted,
            "backfill_suppressed": max(0, len(unseen) - len(selected)),
            "timestamp_semantics": "wallet500_first_seen",
            "signal_role": role,
            "first_scan": sid not in prior_source_state,
        }

    if len(calls) > 3000:
        inbox["calls"] = calls[-3000:]
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
            }
        )
    )


if __name__ == "__main__":
    main()
