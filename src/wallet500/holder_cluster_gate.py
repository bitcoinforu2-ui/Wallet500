from __future__ import annotations

import json
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .cluster_corroboration import corroborate_clusters, verified_native_funding_edges, verify_evm_deployer

DATA = Path("data")
TOP_N = 20
MAX_TOP1 = 20.0
MAX_TOP5 = 50.0
MAX_TOP10 = 65.0
CLUSTER_REVIEW_PCT = float(os.getenv("HOLDER_CLUSTER_REVIEW_PCT", "10"))
CLUSTER_BLOCK_PCT = float(os.getenv("HOLDER_CLUSTER_BLOCK_PCT", "20"))
ROLE_EXCLUSION_MIN_CONFIDENCE = float(os.getenv("HOLDER_ROLE_EXCLUSION_MIN_CONFIDENCE", "0.90"))
CEX_CUSTODY_MONITOR_PCT = float(os.getenv("HOLDER_CEX_CUSTODY_MONITOR_PCT", "30"))
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TOTAL_SUPPLY_SELECTOR = "0x18160ddd"
ZERO = "0x0000000000000000000000000000000000000000"
DEAD = "0x000000000000000000000000000000000000dead"
ROLE_REGISTRY_FILE = DATA / "holder-infrastructure-registry.json"
EXCLUDABLE_ROLES = {"DEX_LP_POOL", "CEX_CUSTODY", "BURN_LOCK", "LOCKED_VAULT", "BRIDGE_CUSTODY"}
DEFAULT_RPC = {
    "SOLANA": ["https://api.mainnet-beta.solana.com"],
    "ETHEREUM": ["https://ethereum-rpc.publicnode.com", "https://eth.llamarpc.com"],
    "BSC": ["https://bsc-rpc.publicnode.com", "https://bsc-dataseed.binance.org"],
}


def _urls(*values):
    out = []
    for value in values:
        for x in str(value or "").split(","):
            x = x.strip()
            if x and x not in out:
                out.append(x)
    return out


RPC = {
    "SOLANA": _urls(os.getenv("SOLANA_RPC_URL"), *DEFAULT_RPC["SOLANA"]),
    "ETHEREUM": _urls(os.getenv("ETHEREUM_RPC_URL"), os.getenv("ETH_RPC_URL"), os.getenv("ETH_RPC_FALLBACK_URLS"), *DEFAULT_RPC["ETHEREUM"]),
    "BSC": _urls(os.getenv("BSC_RPC_URL"), os.getenv("BNB_RPC_URL"), os.getenv("BSC_RPC_FALLBACK_URLS"), *DEFAULT_RPC["BSC"]),
}
RPC["SOL"] = RPC["SOLANA"]
RPC["ETH"] = RPC["ETHEREUM"]
RPC["BNB"] = RPC["BSC"]
INPUT_FILE = os.getenv("HOLDER_CLUSTER_INPUT", "active-qualified-candidates.json")
EVM_LOOKBACK = int(os.getenv("HOLDER_EVM_LOOKBACK_BLOCKS", "50000"))
EVM_CHUNK = max(100, int(os.getenv("HOLDER_EVM_LOG_CHUNK", "2000")))
EVM_MIN_LOG_SPAN = max(10, int(os.getenv("HOLDER_EVM_MIN_LOG_SPAN", "100")))
INFRA_EXCLUSIONS = {x.strip().lower() for x in os.getenv("HOLDER_CLUSTER_INFRA_EXCLUSIONS", "").split(",") if x.strip()}


def _load(p, d):
    try:
        return json.loads(p.read_text()) if p.exists() else d
    except Exception:
        return d


def _write(p, x):
    p.write_text(json.dumps(x, indent=2))


def _rpc_url(url, method, params):
    if not url:
        return None
    try:
        req = Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), headers={"Content-Type": "application/json", "User-Agent": "Wallet500/1.0"})
        with urlopen(req, timeout=25) as r:
            x = json.loads(r.read().decode())
            return None if x.get("error") else x.get("result")
    except Exception:
        return None


def _rpc_any(urls, method, params):
    for url in urls or []:
        result = _rpc_url(url, method, params)
        if result is not None:
            return result, url
    return None, None


def _rpc(method, params):
    return _rpc_any(RPC["SOL"], method, params)[0]


def _addr(topic):
    return ("0x" + str(topic)[-40:]).lower() if topic else ""


def _as_int_hex(x):
    try:
        return int(x, 16) if isinstance(x, str) else int(x)
    except Exception:
        return 0


def _norm(chain, address):
    value = str(address or "").strip()
    c = str(chain or "").upper()
    return value if c in ("SOL", "SOLANA") else value.lower()


def _role_registry():
    payload = _load(ROLE_REGISTRY_FILE, {})
    entries = payload.get("entries") if isinstance(payload, dict) else []
    return entries if isinstance(entries, list) else []


def _registered_role(chain, address, entries=None):
    target = _norm(chain, address)
    if not target:
        return None
    for row in entries if entries is not None else _role_registry():
        if not isinstance(row, dict):
            continue
        if str(row.get("chain") or "").upper() not in {str(chain or "").upper(), "*"}:
            continue
        if _norm(chain, row.get("address")) != target:
            continue
        try:
            confidence = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return {"role": str(row.get("role") or "UNKNOWN").upper(), "label": row.get("label"), "confidence": confidence, "source": "VERIFIED_ROLE_REGISTRY", "evidence": row.get("evidence")}
    return None


def _holder_role(chain, address, pair_address=None, registry=None):
    addr = _norm(chain, address)
    pair = _norm(chain, pair_address)
    if not addr:
        return {"role": "UNKNOWN", "label": None, "confidence": 0.0, "source": "NO_ADDRESS", "excluded_from_whale_concentration": False}
    if pair and addr == pair:
        return {"role": "DEX_LP_POOL", "label": "Exact execution pair", "confidence": 1.0, "source": "EXACT_PAIR_IDENTITY", "excluded_from_whale_concentration": True}
    if addr in {_norm(chain, ZERO), _norm(chain, DEAD)}:
        return {"role": "BURN_LOCK", "label": "Burn/dead address", "confidence": 1.0, "source": "CANONICAL_BURN_ADDRESS", "excluded_from_whale_concentration": True}
    registered = _registered_role(chain, address, registry)
    if registered:
        registered["excluded_from_whale_concentration"] = bool(registered["role"] in EXCLUDABLE_ROLES and registered["confidence"] >= ROLE_EXCLUSION_MIN_CONFIDENCE)
        return registered
    if addr in INFRA_EXCLUSIONS:
        return {"role": "KNOWN_INFRASTRUCTURE", "label": "Environment infrastructure exclusion", "confidence": 1.0, "source": "HOLDER_CLUSTER_INFRA_EXCLUSIONS", "excluded_from_whale_concentration": True}
    return {"role": "UNKNOWN", "label": None, "confidence": 0.0, "source": "UNCLASSIFIED_FAIL_CLOSED", "excluded_from_whale_concentration": False}


def _role_aware_distribution(chain, holders, pair_address=None, registry=None):
    classified = []
    for rank, holder in enumerate(holders, 1):
        row = dict(holder)
        role = _holder_role(chain, row.get("owner"), pair_address, registry)
        row.update({"gross_rank": rank, "holder_role": role["role"], "holder_role_label": role.get("label"), "holder_role_confidence": round(float(role.get("confidence") or 0), 4), "holder_role_source": role.get("source"), "excluded_from_whale_concentration": bool(role.get("excluded_from_whale_concentration"))})
        classified.append(row)
    gross = sorted((float(x.get("pct") or 0) for x in classified), reverse=True)
    real_holders = [x for x in classified if not x["excluded_from_whale_concentration"]]
    real_pcts = sorted((float(x.get("pct") or 0) for x in real_holders), reverse=True)
    excluded = [x for x in classified if x["excluded_from_whale_concentration"]]

    def role_pct(role):
        return sum(float(x.get("pct") or 0) for x in classified if x.get("holder_role") == role)

    return {"holders": classified, "real_holders": real_holders, "gross_top1_pct": sum(gross[:1]), "gross_top5_pct": sum(gross[:5]), "gross_top10_pct": sum(gross[:10]), "adjusted_top1_pct": sum(real_pcts[:1]), "adjusted_top5_pct": sum(real_pcts[:5]), "adjusted_top10_pct": sum(real_pcts[:10]), "adjusted_top10_complete": len(real_holders) >= 10, "known_infrastructure_pct": sum(float(x.get("pct") or 0) for x in excluded), "dex_lp_pct": role_pct("DEX_LP_POOL"), "cex_custody_pct": role_pct("CEX_CUSTODY"), "burn_lock_pct": role_pct("BURN_LOCK"), "excluded_holder_count": len(excluded), "unknown_holder_pct_observed": sum(float(x.get("pct") or 0) for x in classified if x.get("holder_role") == "UNKNOWN")}


def _evm_logs_resilient(urls, token, a, b):
    logs, url = _rpc_any(urls, "eth_getLogs", [{"fromBlock": hex(a), "toBlock": hex(b), "address": token, "topics": [TRANSFER_TOPIC]}])
    if logs is not None:
        return logs, {"queries": 1, "splits": 0, "failed_range": None, "rpc_endpoints_used": 1 if url else 0}
    if b - a + 1 <= EVM_MIN_LOG_SPAN:
        return None, {"queries": 1, "splits": 0, "failed_range": [a, b], "rpc_endpoints_used": 0}
    mid = (a + b) // 2
    left, lm = _evm_logs_resilient(urls, token, a, mid)
    right, rm = _evm_logs_resilient(urls, token, mid + 1, b)
    meta = {"queries": 1 + lm["queries"] + rm["queries"], "splits": 1 + lm["splits"] + rm["splits"], "failed_range": lm.get("failed_range") or rm.get("failed_range"), "rpc_endpoints_used": max(lm["rpc_endpoints_used"], rm["rpc_endpoints_used"])}
    if left is None or right is None:
        return None, meta
    return left + right, meta


def _sol_holders(token):
    supply = _rpc("getTokenSupply", [token, {"commitment": "confirmed"}]) or {}
    total = float((supply.get("value") or {}).get("uiAmount") or 0)
    largest = _rpc("getTokenLargestAccounts", [token, {"commitment": "confirmed"}])
    if not isinstance(largest, dict):
        return [], [], {"supply": total, "largest_accounts_returned": 0, "owners_resolved": 0, "owner_resolution_complete": False, "reason": "SOLANA_LARGEST_ACCOUNTS_RPC_UNAVAILABLE"}
    token_accounts = []
    for x in (largest.get("value") or [])[:TOP_N]:
        amt = float(x.get("uiAmount") or 0)
        addr = x.get("address")
        if addr and amt > 0:
            token_accounts.append({"token_account": addr, "amount": amt, "pct_of_supply": amt / total * 100 if total else 0})
    if not token_accounts:
        return [], [], {"supply": total, "largest_accounts_returned": 0, "owners_resolved": 0, "owner_resolution_complete": False, "reason": "SOLANA_LARGEST_ACCOUNTS_EMPTY"}
    infos = _rpc("getMultipleAccounts", [[x["token_account"] for x in token_accounts], {"encoding": "jsonParsed", "commitment": "confirmed"}]) or {}
    values = (infos.get("value") or []) if isinstance(infos, dict) else []
    by_owner = defaultdict(float)
    resolved = []
    for row, info in zip(token_accounts, values):
        try:
            owner = ((((info or {}).get("data") or {}).get("parsed") or {}).get("info") or {}).get("owner")
        except Exception:
            owner = None
        resolved.append({**row, "owner": owner})
        if owner:
            by_owner[owner] += row["amount"]
    owners = [{"owner": o, "amount": a, "pct": a / total * 100 if total else 0} for o, a in by_owner.items()]
    owners.sort(key=lambda x: x["amount"], reverse=True)
    rc = sum(1 for x in resolved if x.get("owner"))
    return owners, resolved, {"supply": total, "largest_accounts_returned": len(token_accounts), "owners_resolved": rc, "owner_resolution_complete": rc == len(token_accounts) and rc > 0, "reason": "SOLANA_OWNER_RESOLUTION_COMPLETE" if rc == len(token_accounts) and rc > 0 else "SOLANA_OWNER_RESOLUTION_INCOMPLETE"}


def _evm_total_supply(urls, token):
    x, url = _rpc_any(urls, "eth_call", [{"to": token, "data": TOTAL_SUPPLY_SELECTOR}, "latest"])
    return (_as_int_hex(x) if x else 0), url


def _evm_start_block(row, latest_i):
    for k in ("deployment_block", "contract_creation_block", "token_creation_block", "start_block"):
        v = row.get(k)
        if v is not None:
            try:
                n = int(v, 16) if isinstance(v, str) and v.startswith("0x") else int(v)
                if 0 <= n <= latest_i:
                    return n, k, True
            except Exception:
                pass
    return max(0, latest_i - EVM_LOOKBACK), "bounded_lookback", False


def _components(holders, graph, exclusions):
    pct = {str(h.get("owner") or "").lower(): float(h.get("pct") or 0) for h in holders if h.get("owner")}
    nodes = set(pct) - set(exclusions)
    adj = defaultdict(set)
    edge_counts = defaultdict(int)
    for e in graph:
        a = str(e.get("from") or "").lower(); b = str(e.get("to") or "").lower(); n = int(e.get("transfer_count") or 0)
        if not a or not b or a == b or a not in nodes or b not in nodes:
            continue
        adj[a].add(b); adj[b].add(a); edge_counts[tuple(sorted((a, b)))] += n
    seen = set(); out = []
    for root in sorted(nodes):
        if root in seen or not adj.get(root):
            continue
        q = deque([root]); seen.add(root); comp = []
        while q:
            cur = q.popleft(); comp.append(cur)
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt); q.append(nxt)
        if len(comp) < 2:
            continue
        cs = set(comp)
        transfers = sum(n for (a, b), n in edge_counts.items() if a in cs and b in cs)
        out.append({"wallets": sorted(comp), "wallet_count": len(comp), "combined_pct": round(sum(pct.get(x, 0) for x in comp), 4), "direct_transfer_count": transfers, "evidence": "DIRECT_TOKEN_TRANSFERS_AMONG_CURRENT_TOP_HOLDERS", "ownership_claim": False})
    out.sort(key=lambda x: (x["combined_pct"], x["direct_transfer_count"]), reverse=True)
    return out


def _evm_holders(chain, token, row):
    urls = RPC.get(chain, [])
    latest, latest_url = _rpc_any(urls, "eth_blockNumber", [])
    if not latest:
        return [], [], [], {"complete": False, "reason": "EVM_RPC_UNAVAILABLE", "rpc_candidates": len(urls)}
    latest_i = int(latest, 16); start, start_source, start_verified = _evm_start_block(row, latest_i)
    balances = defaultdict(int); edges = defaultdict(int); logs_seen = chunks = queries = splits = 0; used = {latest_url} if latest_url else set()
    for a in range(start, latest_i + 1, EVM_CHUNK):
        b = min(latest_i, a + EVM_CHUNK - 1); chunks += 1
        logs, qmeta = _evm_logs_resilient(urls, token, a, b); queries += qmeta["queries"]; splits += qmeta["splits"]
        if logs is None:
            return [], [], [], {"complete": False, "reason": "EVM_LOG_RANGE_UNAVAILABLE", "from_block": start, "to_block": latest_i, "failed_chunk": qmeta.get("failed_range") or [a, b], "chunks_completed": chunks - 1, "adaptive_log_queries": queries, "adaptive_splits": splits, "start_block_verified": start_verified, "start_block_source": start_source, "rpc_candidates": len(urls), "rpc_endpoints_used": len(used)}
        for log in logs:
            topics = log.get("topics") or []
            if len(topics) < 3:
                continue
            f = _addr(topics[1]); t = _addr(topics[2]); value = _as_int_hex(log.get("data") or "0x0"); logs_seen += 1
            if f and f != ZERO: balances[f] -= value
            if t and t != ZERO: balances[t] += value
            if f and t and f != ZERO and t != ZERO: edges[(f, t)] += 1
    total_supply, supply_url = _evm_total_supply(urls, token)
    if supply_url: used.add(supply_url)
    positive = [(o, a) for o, a in balances.items() if a > 0]; denom = total_supply if total_supply > 0 else 0
    holders = [{"owner": o, "raw_amount": str(a), "pct": a / denom * 100 if denom else 0} for o, a in positive]
    holders.sort(key=lambda x: int(x["raw_amount"]), reverse=True); holders = holders[:TOP_N]
    graph = [{"from": f, "to": t, "transfer_count": n} for (f, t), n in sorted(edges.items(), key=lambda x: x[1], reverse=True)[:500]]
    exclusions = set(INFRA_EXCLUSIONS) | {ZERO, token.lower(), str(row.get("pair_address") or row.get("locked_pair_address") or "").lower()}
    clusters = _components(holders, graph, exclusions); complete = bool(start_verified and total_supply > 0)
    reason = "FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK" if complete else ("FULL_START_BLOCK_BUT_TOTAL_SUPPLY_UNVERIFIED" if start_verified else "BOUNDED_LOOKBACK_RECONSTRUCTION")
    return holders, graph, clusters, {"complete": complete, "reason": reason, "from_block": start, "to_block": latest_i, "logs_seen": logs_seen, "chunks": chunks, "adaptive_log_queries": queries, "adaptive_splits": splits, "lookback_blocks": latest_i - start, "observed_positive_holders": len(positive), "total_supply_raw": str(total_supply) if total_supply else None, "pct_authoritative": bool(total_supply > 0), "start_block_verified": start_verified, "start_block_source": start_source, "infrastructure_exclusions": sorted(x for x in exclusions if x), "rpc_candidates": len(urls), "rpc_endpoints_used": len(used)}


def analyze(row):
    chain = row.get("chain"); token = row.get("token") or row.get("token_address") or row.get("mint"); pair = row.get("pair_address") or row.get("locked_pair_address"); c = str(chain or "").upper()
    reasons = []; token_accounts = []; graph = []; clusters = []; meta = {}; deployer_evidence = {"verified": False, "reason": "NOT_APPLICABLE"}; funding = []
    if c in ("SOL", "SOLANA"):
        holders, token_accounts, meta = _sol_holders(token)
        if meta.get("reason") not in (None, "SOLANA_OWNER_RESOLUTION_COMPLETE"): reasons.append(meta["reason"])
    elif c in ("ETH", "ETHEREUM", "BSC", "BNB"):
        holders, graph, clusters, meta = _evm_holders(c, str(token).lower(), row); urls = RPC.get(c, []); deployer_evidence = {"verified": False, "reason": "RPC_FALLBACK_SET_USED"}
        for url in urls:
            deployer_evidence = verify_evm_deployer(lambda method, params, u=url: _rpc_url(u, method, params), str(token).lower(), row)
            if deployer_evidence.get("verified"): break
        funding = verified_native_funding_edges(row); meta = {**meta, "deployer_evidence": deployer_evidence, "verified_native_funding_edges": len(funding)}
        if not meta.get("complete"): reasons.append(meta.get("reason", "EVM_EVIDENCE_INCOMPLETE"))
    else:
        holders = []; reasons.append("UNSUPPORTED_CHAIN")

    distribution = _role_aware_distribution(c, holders, pair, _role_registry()); holders = distribution["holders"]
    role_exclusions = {str(x.get("owner") or "").lower() for x in holders if x.get("excluded_from_whale_concentration")}
    if c in ("ETH", "ETHEREUM", "BSC", "BNB"):
        clusters = _components(holders, graph, role_exclusions | INFRA_EXCLUSIONS | {ZERO, str(token or "").lower(), str(pair or "").lower()}); clusters = corroborate_clusters(clusters, graph, deployer_evidence, funding)
    top1 = distribution["adjusted_top1_pct"]; top5 = distribution["adjusted_top5_pct"]; top10 = distribution["adjusted_top10_pct"]
    if not holders: reasons.append("HOLDER_DATA_UNAVAILABLE")
    sol_complete = c in ("SOL", "SOLANA") and bool(meta.get("owner_resolution_complete")); evm_complete = c in ("ETH", "ETHEREUM", "BSC", "BNB") and bool(meta.get("complete")); verification_complete = bool((sol_complete or evm_complete) and holders)
    if c in ("SOL", "SOLANA") and not sol_complete: reasons.append("SOME_TOKEN_ACCOUNT_OWNERS_UNRESOLVED")
    if verification_complete and not distribution["adjusted_top10_complete"]: reasons.append("ADJUSTED_TOP10_REPLACEMENT_INCOMPLETE_REVIEW_ONLY")
    if top1 > MAX_TOP1: reasons.append("TOP1_OWNER_CONCENTRATION_HIGH" if verification_complete else "TOP1_CONCENTRATION_HIGH_REVIEW_ONLY")
    if top5 > MAX_TOP5: reasons.append("TOP5_OWNER_CONCENTRATION_HIGH" if verification_complete else "TOP5_CONCENTRATION_HIGH_REVIEW_ONLY")
    if top10 > MAX_TOP10: reasons.append("TOP10_OWNER_CONCENTRATION_HIGH" if verification_complete else "TOP10_CONCENTRATION_HIGH_REVIEW_ONLY")
    if distribution["cex_custody_pct"] >= CEX_CUSTODY_MONITOR_PCT: reasons.append("CEX_CUSTODY_SUPPLY_GE_30PCT_MONITOR_FLOW")
    linked = [x for x in clusters if x.get("combined_pct", 0) >= CLUSTER_REVIEW_PCT]; corroborated = [x for x in linked if x.get("risk_corroborated") and x.get("combined_pct", 0) >= CLUSTER_BLOCK_PCT]; blockable = corroborated if evm_complete else []
    if linked: reasons.append("LINKED_TOP_HOLDER_COMPONENT_REQUIRES_CORROBORATION")
    if corroborated: reasons.append("CORROBORATED_LINKED_HOLDER_CLUSTER_GE_20PCT" if evm_complete else "CORROBORATED_LINKED_HOLDER_CLUSTER_REVIEW_ONLY_INCOMPLETE_LEDGER")
    hard_block = (verification_complete and any(x in reasons for x in ("TOP1_OWNER_CONCENTRATION_HIGH", "TOP5_OWNER_CONCENTRATION_HIGH", "TOP10_OWNER_CONCENTRATION_HIGH"))) or bool(blockable)
    needs_review = bool(linked) or not verification_complete or any(x.endswith("REVIEW_ONLY") for x in reasons); status = "BLOCK" if hard_block else ("REVIEW" if needs_review else "PASS")
    level = "ONCHAIN_OWNER_CONCENTRATION_RESOLVED" if sol_complete and holders else ("FULL_EVM_TRANSFER_LEDGER" if evm_complete and holders else ("BOUNDED_ONCHAIN_TRANSFER_LEDGER" if holders else "INSUFFICIENT_EVIDENCE"))
    return {"chain": chain, "token": token, "pair_address": pair, "checked_at": datetime.now(timezone.utc).isoformat(), "status": status, "verification_complete": verification_complete, "top_holders_count": len(holders), "top1_pct": round(top1, 4), "top5_pct": round(top5, 4), "top10_pct": round(top10, 4), "gross_top1_pct": round(distribution["gross_top1_pct"], 4), "gross_top5_pct": round(distribution["gross_top5_pct"], 4), "gross_top10_pct": round(distribution["gross_top10_pct"], 4), "adjusted_real_top1_pct": round(top1, 4), "adjusted_real_top5_pct": round(top5, 4), "adjusted_real_top10_pct": round(top10, 4), "adjusted_top10_complete": distribution["adjusted_top10_complete"], "known_infrastructure_pct": round(distribution["known_infrastructure_pct"], 4), "dex_lp_pct": round(distribution["dex_lp_pct"], 4), "cex_custody_pct": round(distribution["cex_custody_pct"], 4), "burn_lock_pct": round(distribution["burn_lock_pct"], 4), "unknown_holder_pct_observed": round(distribution["unknown_holder_pct_observed"], 4), "holder_role_policy": "ONLY_EXACT_HIGH_CONFIDENCE_INFRASTRUCTURE_ROLES_ARE_EXCLUDED;UNKNOWN_FAILS_CLOSED;CEX_CUSTODY_MONITORED_SEPARATELY", "cluster_verified": bool(corroborated), "linked_cluster_candidates": linked, "corroborated_cluster_risks": corroborated, "blockable_cluster_risks": blockable, "deployer_evidence": deployer_evidence, "verified_native_funding_edges": funding, "reasons": list(dict.fromkeys(reasons)), "evidence_level": level, "metadata": meta, "holders": holders, "token_accounts": token_accounts, "transfer_graph": graph}


def _rows_from_source(src):
    if isinstance(src, list): return src
    if isinstance(src, dict):
        rows = src.get("rows", []); return rows if isinstance(rows, list) else []
    return []


def run():
    src = _load(DATA / INPUT_FILE, {}); rows = _rows_from_source(src); out = []; seen = set()
    for r in rows:
        if not isinstance(r, dict): continue
        chain = r.get("chain"); token = r.get("token") or r.get("token_address") or r.get("mint"); pair = r.get("pair_address") or r.get("locked_pair_address"); key = (str(chain), str(token), str(pair))
        if not chain or not token or key in seen: continue
        seen.add(key); out.append(analyze(r))
    now = datetime.now(timezone.utc).isoformat()
    payload = {"updated_at": now, "method": "WALLET500_HOLDER_CLUSTER_PRETRADE_GATE_V2_ROLE_AWARE", "input_file": INPUT_FILE, "truth_note": "Gross concentration is diagnostic only. Hard concentration gates use adjusted non-infrastructure holders after exact high-confidence role classification. Unknown addresses remain counted. CEX custody is excluded from whale concentration but monitored as a separate flow/concentration risk.", "role_exclusion_min_confidence": ROLE_EXCLUSION_MIN_CONFIDENCE, "rows": out}
    _write(DATA / "holder-cluster-gate.json", payload)
    _write(DATA / "holder-cluster-gate-summary.json", {"updated_at": now, "input_file": INPUT_FILE, "checked": len(out), "block": sum(x["status"] == "BLOCK" for x in out), "review": sum(x["status"] == "REVIEW" for x in out), "pass": sum(x["status"] == "PASS" for x in out), "verification_complete": sum(x["verification_complete"] for x in out), "method": payload["method"]})
    print(json.dumps({"checked": len(out), "pass": sum(x["status"] == "PASS" for x in out), "review": sum(x["status"] == "REVIEW" for x in out), "block": sum(x["status"] == "BLOCK" for x in out)}, indent=2)); return payload


if __name__ == "__main__":
    run()
