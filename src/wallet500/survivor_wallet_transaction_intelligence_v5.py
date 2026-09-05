from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
OBS = DATA / "wallet-transaction-observations.json"
OUT = DATA / "survivor-wallet-transaction-intelligence-v5.json"


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def f(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def norm(value) -> str:
    return str(value or "").strip().lower()


def clamp(value, lo=0, hi=100):
    return max(lo, min(hi, int(round(value))))


def token_key(chain, token, pair):
    return f"{norm(chain)}:{norm(token)}:{norm(pair)}"


def fetch_optional_remote_feed() -> dict:
    """Fetch an optional normalized transaction feed.

    The feed is intentionally opt-in. Wallet500 does not scrape or infer swap
    direction from weak evidence. A configured endpoint must return the same
    contract accepted by data/wallet-transaction-observations.json.
    """
    url = os.getenv("WALLET500_TX_FEED_URL", "").strip()
    if not url:
        return {}
    headers = {"Accept": "application/json", "User-Agent": "Wallet500/transaction-intelligence-v5"}
    token = os.getenv("WALLET500_TX_FEED_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def merge_observations(local: dict, remote: dict) -> dict:
    rows = []
    for source, payload in (("LOCAL", local), ("REMOTE", remote)):
        for row in payload.get("tokens") or []:
            if not isinstance(row, dict):
                continue
            rows.append({**row, "_feed_source": source})
    return {
        "version": 1,
        "observed_at": remote.get("observed_at") or local.get("observed_at"),
        "tokens": rows,
    }


def observation_index(feed: dict) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for row in feed.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        chain = row.get("chain")
        token = row.get("token") or row.get("token_address") or row.get("mint")
        pair = row.get("pair_address")
        if not chain or not token or not pair:
            continue
        out[token_key(chain, token, pair)].append(row)
    return out


def verified_transactions(rows: list[dict], watch_row: dict) -> tuple[list[dict], list[str]]:
    accepted = []
    rejected = []
    expected_pair = norm(watch_row.get("pair_address"))
    expected_token = norm(watch_row.get("token"))
    expected_chain = norm(watch_row.get("chain"))

    for block in rows:
        if norm(block.get("pair_address")) != expected_pair or norm(block.get("chain")) != expected_chain:
            rejected.append("OBSERVATION_IDENTITY_MISMATCH")
            continue
        block_token = norm(block.get("token") or block.get("token_address") or block.get("mint"))
        if block_token != expected_token:
            rejected.append("OBSERVATION_TOKEN_MISMATCH")
            continue
        for tx in block.get("transactions") or []:
            if not isinstance(tx, dict):
                continue
            if tx.get("verified_swap") is not True:
                rejected.append("UNVERIFIED_SWAP_DISCARDED")
                continue
            if norm(tx.get("pair_address") or block.get("pair_address")) != expected_pair:
                rejected.append("TX_PAIR_MISMATCH")
                continue
            if norm(tx.get("token") or block_token) not in ("", expected_token):
                rejected.append("TX_TOKEN_MISMATCH")
                continue
            side = str(tx.get("side") or "").upper()
            usd = f(tx.get("usd_value"))
            wallet = str(tx.get("wallet") or tx.get("trader") or "").strip()
            tx_hash = str(tx.get("tx_hash") or tx.get("signature") or "").strip()
            if side not in {"BUY", "SELL"} or usd is None or usd < 0 or not wallet or not tx_hash:
                rejected.append("TX_REQUIRED_FIELDS_MISSING")
                continue
            accepted.append({
                "side": side,
                "usd_value": usd,
                "wallet": wallet,
                "wallet_norm": norm(wallet),
                "tx_hash": tx_hash,
                "timestamp": tx.get("timestamp"),
                "cluster_id": str(tx.get("cluster_id") or "").strip() or None,
                "wallet_label": tx.get("wallet_label"),
                "wallet_label_verified": tx.get("wallet_label_verified") is True,
                "wallet_quality_score": f(tx.get("wallet_quality_score")),
                "source": block.get("source") or block.get("_feed_source"),
            })
    # A transaction hash can appear in overlapping provider windows. Deduplicate.
    dedup = {}
    for tx in accepted:
        dedup[tx["tx_hash"]] = tx
    return list(dedup.values()), rejected


def flow_metrics(txs: list[dict], liquidity_usd) -> dict:
    if not txs:
        return {
            "coverage": "INSUFFICIENT_COVERAGE",
            "verified_swap_n": 0,
            "buy_usd": None,
            "sell_usd": None,
            "net_buy_usd": None,
            "buy_sell_usd_ratio": None,
            "unique_buyers": None,
            "unique_sellers": None,
            "median_buy_usd": None,
            "median_sell_usd": None,
            "top_buy_wallet_share_pct": None,
            "top_sell_wallet_share_pct": None,
            "large_trades": [],
        }

    buys = [x for x in txs if x["side"] == "BUY"]
    sells = [x for x in txs if x["side"] == "SELL"]
    buy_usd = sum(x["usd_value"] for x in buys)
    sell_usd = sum(x["usd_value"] for x in sells)
    unique_buyers = {x["wallet_norm"] for x in buys}
    unique_sellers = {x["wallet_norm"] for x in sells}
    by_buy_wallet = defaultdict(float)
    by_sell_wallet = defaultdict(float)
    for x in buys:
        by_buy_wallet[x["wallet_norm"]] += x["usd_value"]
    for x in sells:
        by_sell_wallet[x["wallet_norm"]] += x["usd_value"]

    liq = f(liquidity_usd) or 0
    large_threshold = max(5000.0, liq * 0.01)
    large = [
        {"tx_hash": x["tx_hash"], "side": x["side"], "usd_value": round(x["usd_value"], 2), "wallet": x["wallet"]}
        for x in txs if x["usd_value"] >= large_threshold
    ]
    ratio = buy_usd / sell_usd if sell_usd > 0 else (None if buy_usd == 0 else float("inf"))
    return {
        "coverage": "VERIFIED_EXACT_PAIR_SWAPS",
        "verified_swap_n": len(txs),
        "buy_usd": round(buy_usd, 2),
        "sell_usd": round(sell_usd, 2),
        "net_buy_usd": round(buy_usd - sell_usd, 2),
        "buy_sell_usd_ratio": round(ratio, 4) if ratio is not None and math.isfinite(ratio) else None,
        "unique_buyers": len(unique_buyers),
        "unique_sellers": len(unique_sellers),
        "median_buy_usd": round(median([x["usd_value"] for x in buys]), 2) if buys else None,
        "median_sell_usd": round(median([x["usd_value"] for x in sells]), 2) if sells else None,
        "top_buy_wallet_share_pct": round(max(by_buy_wallet.values()) / buy_usd * 100, 2) if buy_usd > 0 else None,
        "top_sell_wallet_share_pct": round(max(by_sell_wallet.values()) / sell_usd * 100, 2) if sell_usd > 0 else None,
        "large_trade_threshold_usd": round(large_threshold, 2),
        "large_trades": sorted(large, key=lambda x: x["usd_value"], reverse=True)[:20],
    }


def cluster_metrics(txs: list[dict]) -> dict:
    if not txs:
        return {"coverage": "INSUFFICIENT_COVERAGE", "independent_buyer_clusters": None, "largest_buyer_cluster_share_pct": None, "cluster_concentration_risk": "INSUFFICIENT_COVERAGE"}
    buy = [x for x in txs if x["side"] == "BUY"]
    with_cluster = [x for x in buy if x.get("cluster_id")]
    if not with_cluster:
        return {"coverage": "INSUFFICIENT_CLUSTER_LABELS", "independent_buyer_clusters": None, "largest_buyer_cluster_share_pct": None, "cluster_concentration_risk": "INSUFFICIENT_COVERAGE"}
    total = sum(x["usd_value"] for x in with_cluster)
    buckets = defaultdict(float)
    for x in with_cluster:
        buckets[x["cluster_id"]] += x["usd_value"]
    share = max(buckets.values()) / total * 100 if total else None
    return {
        "coverage": "VERIFIED_FEED_CLUSTER_LABELS",
        "independent_buyer_clusters": len(buckets),
        "largest_buyer_cluster_share_pct": round(share, 2) if share is not None else None,
        "cluster_concentration_risk": "HIGH" if share is not None and share >= 55 else "MEDIUM" if share is not None and share >= 35 else "LOW",
    }


def smart_money_metrics(txs: list[dict]) -> dict:
    verified = [x for x in txs if x.get("wallet_label_verified") and x.get("wallet_label")]
    if not verified:
        return {"coverage": "INSUFFICIENT_COVERAGE", "verified_labeled_wallet_n": 0, "smart_money_buy_usd": None, "smart_money_sell_usd": None, "smart_money_net_usd": None, "labels": []}
    buys = sum(x["usd_value"] for x in verified if x["side"] == "BUY")
    sells = sum(x["usd_value"] for x in verified if x["side"] == "SELL")
    labels = sorted({str(x["wallet_label"]) for x in verified})
    return {
        "coverage": "VERIFIED_WALLET_LABELS_ONLY",
        "verified_labeled_wallet_n": len({x["wallet_norm"] for x in verified}),
        "smart_money_buy_usd": round(buys, 2),
        "smart_money_sell_usd": round(sells, 2),
        "smart_money_net_usd": round(buys - sells, 2),
        "labels": labels[:20],
    }


def wash_risk(txs: list[dict]) -> dict:
    if len(txs) < 8:
        return {"status": "INSUFFICIENT_SAMPLE", "score": None, "reasons": []}
    reasons = []
    score = 0
    by_wallet = defaultdict(list)
    rounded_sizes = defaultdict(int)
    for x in txs:
        by_wallet[x["wallet_norm"]].append(x)
        rounded_sizes[round(x["usd_value"], 0)] += 1
    flips = 0
    for rows in by_wallet.values():
        sides = {x["side"] for x in rows}
        if len(sides) > 1:
            flips += 1
    if flips / max(1, len(by_wallet)) >= 0.4:
        score += 35
        reasons.append("MANY_SAME_WINDOW_BUY_SELL_WALLETS")
    repeated = max(rounded_sizes.values()) / len(txs)
    if repeated >= 0.35:
        score += 35
        reasons.append("REPEATED_ROUNDED_TRADE_SIZES")
    if len(by_wallet) <= max(2, len(txs) // 8):
        score += 25
        reasons.append("LOW_WALLET_DIVERSITY")
    return {"status": "HIGH_RISK" if score >= 60 else "REVIEW" if score >= 30 else "LOW_SIGNAL", "score": clamp(score), "reasons": reasons, "warning": "Heuristic research signal only; not proof of wash trading."}


def wallet_flow_score(flow: dict, clusters: dict, smart: dict, wash: dict) -> dict:
    if flow.get("coverage") != "VERIFIED_EXACT_PAIR_SWAPS":
        return {"score": 0, "stage": "INSUFFICIENT_COVERAGE", "reasons": []}
    score = 0
    reasons = []
    net = f(flow.get("net_buy_usd")) or 0
    buy = f(flow.get("buy_usd")) or 0
    sell = f(flow.get("sell_usd")) or 0
    unique_buyers = int(flow.get("unique_buyers") or 0)
    if net > 0 and buy >= max(10000, sell * 1.25):
        score += 30
        reasons.append("NET_CAPITAL_INFLOW")
    if unique_buyers >= 20:
        score += 20
        reasons.append("BROAD_UNIQUE_BUYER_BASE")
    elif unique_buyers >= 8:
        score += 10
        reasons.append("MULTI_BUYER_BASE")
    top_share = f(flow.get("top_buy_wallet_share_pct"))
    if top_share is not None and top_share <= 30:
        score += 15
        reasons.append("BUY_FLOW_NOT_SINGLE_WALLET_DOMINATED")
    if clusters.get("coverage") == "VERIFIED_FEED_CLUSTER_LABELS" and (clusters.get("independent_buyer_clusters") or 0) >= 3:
        score += 15
        reasons.append("MULTI_CLUSTER_ACCUMULATION")
    if smart.get("coverage") == "VERIFIED_WALLET_LABELS_ONLY" and (f(smart.get("smart_money_net_usd")) or 0) > 0:
        score += 20
        reasons.append("VERIFIED_LABELED_WALLET_NET_BUY")
    if wash.get("status") == "HIGH_RISK":
        score -= 35
        reasons.append("WASH_RISK_PENALTY")
    return {"score": clamp(score), "stage": "STRONG" if score >= 70 else "CONFIRMING" if score >= 45 else "WEAK", "reasons": reasons}


def analyse_row(watch_row: dict, blocks: list[dict]) -> dict:
    txs, rejected = verified_transactions(blocks, watch_row)
    flow = flow_metrics(txs, watch_row.get("liquidity_usd"))
    clusters = cluster_metrics(txs)
    smart = smart_money_metrics(txs)
    wash = wash_risk(txs)
    score = wallet_flow_score(flow, clusters, smart, wash)
    coverage = {
        "exact_pair_swap_flow": flow.get("coverage"),
        "cluster_labels": clusters.get("coverage"),
        "wallet_labels": smart.get("coverage"),
        "rejected_evidence_n": len(rejected),
    }
    return {
        "coverage": coverage,
        "flow": flow,
        "buyer_clusters": clusters,
        "smart_money": smart,
        "wash_risk": wash,
        "wallet_flow_score": score,
        "rejected_evidence_reasons": sorted(set(rejected)),
        "production_effect": False,
    }


def main():
    watch = load(WATCH, {})
    if not watch:
        raise SystemExit("SURVIVOR_WATCH_OUTPUT_MISSING")
    local = load(OBS, {})
    remote = fetch_optional_remote_feed()
    feed = merge_observations(local, remote)
    idx = observation_index(feed)
    summary = []
    verified_tokens = 0

    for row in watch.get("tokens") or []:
        key = token_key(row.get("chain"), row.get("token"), row.get("pair_address"))
        layer = analyse_row(row, idx.get(key, []))
        row["wallet_transaction_intelligence_v5"] = layer
        if layer["flow"].get("coverage") == "VERIFIED_EXACT_PAIR_SWAPS":
            verified_tokens += 1
        summary.append({
            "chain": row.get("chain"),
            "token": row.get("token"),
            "pair_address": row.get("pair_address"),
            "wallet_flow_score": layer["wallet_flow_score"],
            "coverage": layer["coverage"],
        })

    watch["wallet_transaction_intelligence_v5"] = {
        "version": "WALLET_TRANSACTION_INTELLIGENCE_V5",
        "research_only": True,
        "production_gates_changed": False,
        "exact_pair_only": True,
        "verified_flow_token_n": verified_tokens,
        "survivor_n": len(watch.get("tokens") or []),
        "input_contract": {
            "path": str(OBS),
            "optional_remote_env": "WALLET500_TX_FEED_URL",
            "required_transaction_fields": ["tx_hash", "wallet", "side", "usd_value", "verified_swap", "pair_address"],
            "verified_swap_required": True,
        },
        "policy": "No transaction is counted as buy/sell unless verified_swap=true and exact token+pair identity matches the survivor row. Wallet/cluster labels affect research scores only when explicitly verified by the upstream feed.",
    }
    dump(WATCH, watch)
    dump(OUT, {
        "version": 5,
        "generated_at": watch.get("generated_at"),
        "research_only": True,
        "production_gates_changed": False,
        "exact_pair_only": True,
        "verified_flow_token_n": verified_tokens,
        "tokens": summary,
    })
    print(json.dumps({"wallet_tx_v5_tokens": len(summary), "verified_flow_token_n": verified_tokens, "production_gates_changed": False}))


if __name__ == "__main__":
    main()
