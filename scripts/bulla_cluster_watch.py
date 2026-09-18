#!/usr/bin/env python3
"""Wallet500 BULLA cluster / large-holder watch.

Fail-closed principles:
- exact BNB token + exact DEX pair only
- on-chain Transfer logs are read from BNB JSON-RPC, never inferred from ticker
- CEX labels are only used when BscScan returns a matching exchange label
- an exchange withdrawal is never treated as a buy by itself
- first run bootstraps state without sending retrospective Telegram noise
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CA = "0x595e21b20e78674f8a64c1566a20b2b316bc3511"
PAIR = "0x9950c1f3754fb8a3ebbaf24b8573cafc7474c00f"
CHAIN_ID_HEX = "0x38"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO = "0x0000000000000000000000000000000000000000"
STATE_PATH = Path("data/bulla-cluster-watch-state.json")
DEX_URL = f"https://dexscreener.com/bsc/{PAIR}"
KNOWN_WHALE = "0x560a46d427f623c29855a1724807a3c0a624c1a3"

# Materiality rules. BULLA has a fixed 1B supply.
CLUSTER_LOW = 35_000_000
CLUSTER_HIGH = 45_000_000
MATERIAL_ANY = 5_000_000       # 0.5% supply
MATERIAL_CLUSTER = 1_000_000   # 0.1% supply from/to a tracked ~40M cluster wallet
BOOTSTRAP_BLOCKS = 8_000        # discovery only; first run is silent
MAX_BACKLOG_BLOCKS = 40_000
FINALITY_BLOCKS = 20
LOG_CHUNK = 1_500
MAX_EVENTS_IN_MESSAGE = 5

RPC_ENDPOINTS = [
    x.strip()
    for x in os.getenv(
        "BSC_RPC_URLS",
        "https://bsc-dataseed.binance.org/,"
        "https://bsc-dataseed1.bnbchain.org,"
        "https://bsc-rpc.publicnode.com",
    ).split(",")
    if x.strip()
]

EXCHANGE_PATTERNS = {
    "BINANCE": re.compile(r"\bbinance\b", re.I),
    "MEXC": re.compile(r"\bmexc\b", re.I),
    "KUCOIN": re.compile(r"\bkucoin\b", re.I),
    "GATE": re.compile(r"\bgate(?:\.io)?\b", re.I),
    "BYBIT": re.compile(r"\bbybit\b", re.I),
    "OKX": re.compile(r"\bokx\b", re.I),
    "BITGET": re.compile(r"\bbitget\b", re.I),
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def http_json(url, *, data=None, headers=None, timeout=20):
    h = {"accept": "application/json", "user-agent": "Wallet500-BULLA-Cluster-Watch/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    errors = []
    for url in RPC_ENDPOINTS:
        try:
            out = http_json(url, data=body, headers={"content-type": "application/json"}, timeout=25)
            if out.get("error"):
                raise RuntimeError(str(out["error"]))
            if "result" not in out:
                raise RuntimeError("missing result")
            return out["result"]
        except Exception as e:
            errors.append(f"{url}:{type(e).__name__}:{str(e)[:100]}")
    raise RuntimeError("BSC_RPC_ALL_FAILED | " + " | ".join(errors))


def block_number():
    return int(rpc("eth_blockNumber", []), 16)


def decode_topic_address(topic):
    raw = str(topic).lower().replace("0x", "")
    if len(raw) != 64:
        raise ValueError("bad address topic")
    return "0x" + raw[-40:]


def block_time(block_hex):
    b = rpc("eth_getBlockByNumber", [block_hex, False])
    if not b:
        return None
    return datetime.fromtimestamp(int(b["timestamp"], 16), tz=timezone.utc).isoformat()


def token_balance(addr):
    selector = "70a08231"  # balanceOf(address)
    data = "0x" + selector + ("0" * 24) + addr.lower().replace("0x", "")
    raw = rpc("eth_call", [{"to": CA, "data": data}, "latest"])
    return int(raw, 16) / 1e18


def get_logs(start_block, end_block):
    rows = []
    for a in range(start_block, end_block + 1, LOG_CHUNK):
        b = min(end_block, a + LOG_CHUNK - 1)
        part = rpc(
            "eth_getLogs",
            [{
                "fromBlock": hex(a),
                "toBlock": hex(b),
                "address": CA,
                "topics": [TRANSFER_TOPIC],
            }],
        )
        rows.extend(part or [])
    rows.sort(key=lambda x: (int(x.get("blockNumber", "0x0"), 16), int(x.get("logIndex", "0x0"), 16)))
    return rows


def market_snapshot():
    raw = http_json(f"https://api.dexscreener.com/latest/dex/pairs/bsc/{PAIR}")
    pairs = raw.get("pairs") or []
    row = next((x for x in pairs if str(x.get("pairAddress") or "").lower() == PAIR), None)
    if not row:
        raise RuntimeError("BULLA_EXACT_PAIR_MISSING_DEXSCREENER")
    base = str(((row.get("baseToken") or {}).get("address") or "")).lower()
    if base != CA:
        raise RuntimeError(f"BULLA_BASE_TOKEN_MISMATCH:{base}")
    price = float(row.get("priceUsd") or 0)
    liq = float(((row.get("liquidity") or {}).get("usd") or 0))
    vol = row.get("volume") or {}
    tx = row.get("txns") or {}
    h1 = tx.get("h1") or {}
    if price <= 0 or liq <= 0:
        raise RuntimeError("BULLA_EXACT_PAIR_NONPOSITIVE_MARKET")
    return {
        "source": "DexScreener exact pair",
        "price_usd": price,
        "liquidity_usd": liq,
        "volume_h1": float(vol.get("h1") or 0),
        "volume_h24": float(vol.get("h24") or 0),
        "buys_h1": int(h1.get("buys") or 0),
        "sells_h1": int(h1.get("sells") or 0),
    }


def bscscan_exchange_label(addr):
    """Return an exchange label only if BscScan's address-page title names it."""
    try:
        req = urllib.request.Request(
            f"https://bscscan.com/address/{addr}",
            headers={"user-agent": "Mozilla/5.0 Wallet500/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read(350_000).decode("utf-8", errors="ignore")
        lowered = text.lower()
        if addr.lower() not in lowered:
            return None
        # Fail closed: the page body can contain exchange ads. Only accept a label
        # from BscScan's title / og:title metadata.
        title_parts = re.findall(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
        title_parts += re.findall(
            r"<meta[^>]+(?:property|name)=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)",
            text,
            flags=re.I | re.S,
        )
        label_surface = " | ".join(title_parts)
        for label, pat in EXCHANGE_PATTERNS.items():
            if pat.search(label_surface):
                return label
    except Exception as e:
        print("BULLA_LABEL_LOOKUP_UNAVAILABLE", addr, type(e).__name__)
    return None


def load_state():
    if not STATE_PATH.exists():
        return {
            "version": 1,
            "token": {"symbol": "BULLA", "chain": "BNB", "contract_address": CA},
            "exact_pair": PAIR,
            "last_scanned_block": None,
            "cluster_wallets": [KNOWN_WHALE],
            "wallet_cex_history": {},
            "sent_event_ids": [],
            "last_market": None,
            "updated_at": None,
        }
    d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if str(((d.get("token") or {}).get("contract_address") or "")).lower() != CA:
        raise SystemExit("BULLA_STATE_CA_MISMATCH")
    if str(d.get("exact_pair") or "").lower() != PAIR:
        raise SystemExit("BULLA_STATE_PAIR_MISMATCH")
    return d


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utcnow()
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def money(n):
    n = float(n)
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:.6f}".rstrip("0").rstrip(".")


def amount_text(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.3f}M BULLA"
    if n >= 1_000:
        return f"{n/1_000:.1f}K BULLA"
    return f"{n:.2f} BULLA"


def send_telegram(message):
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        print("BULLA_TELEGRAM_SUPPRESSED_FINAL_BUY_ONLY")
        return False
    payload = urllib.parse.urlencode({
        "chat_id": chat,
        "text": message[:3900],
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.load(r)
        if not (200 <= r.status < 300 and body.get("ok") is True):
            raise SystemExit(f"BULLA_TELEGRAM_SEND_FAILED status={r.status} ok={body.get('ok')}")
    print("BULLA_MATERIAL_EVENT_DELIVERED_TO_TELEGRAM")
    return True


def classify_event(src, dst, amount, cluster, src_label, dst_label, state):
    src_cluster = src in cluster
    dst_cluster = dst in cluster
    equal_block = CLUSTER_LOW <= amount <= CLUSTER_HIGH

    hist = state.setdefault("wallet_cex_history", {})
    round_trip = False
    if src_cluster and dst_label:
        old = hist.get(src) or {}
        round_trip = bool(old.get("last_cex_out"))
        old["last_cex_in"] = utcnow()
        old["last_cex_in_label"] = dst_label
        hist[src] = old
    if dst_cluster and src_label:
        old = hist.get(dst) or {}
        round_trip = round_trip or bool(old.get("last_cex_in"))
        old["last_cex_out"] = utcnow()
        old["last_cex_out_label"] = src_label
        hist[dst] = old

    if src_cluster and dst_label:
        return ("DISTRIBUTION_RISK", "Tracked cluster wallet sent BULLA to a verified CEX address.", round_trip)
    if src_label and dst_cluster:
        return ("REDISTRIBUTION", "Verified CEX outflow into a tracked cluster wallet; not treated as a buy by itself.", round_trip)
    if src_cluster and dst_cluster:
        return ("REDISTRIBUTION", "Transfer occurred between tracked cluster wallets.", round_trip)
    if equal_block:
        return ("REDISTRIBUTION", "Near-40M equal-size block movement detected; coordinated-size cluster candidate.", round_trip)
    if src_cluster or dst_cluster:
        return ("CLUSTER_FLOW", "Material transfer touched a tracked cluster wallet.", round_trip)
    return ("WHALE_FLOW_UNCLASSIFIED", "Large BULLA transfer detected; counterparty identity remains unverified.", round_trip)


def main():
    state = load_state()
    first_run = state.get("last_scanned_block") is None

    chain_id = str(rpc("eth_chainId", [])).lower()
    if chain_id != CHAIN_ID_HEX:
        raise SystemExit(f"BULLA_FAIL_CLOSED_CHAIN_ID={chain_id}")

    safe_head = block_number() - FINALITY_BLOCKS
    if safe_head <= 0:
        raise SystemExit("BULLA_FAIL_CLOSED_BAD_HEAD")

    if first_run:
        start = max(1, safe_head - BOOTSTRAP_BLOCKS)
    else:
        start = int(state["last_scanned_block"]) + 1
        if start > safe_head:
            print("BULLA_NO_NEW_FINALIZED_BLOCKS")
            return
        backlog = safe_head - start + 1
        if backlog > MAX_BACKLOG_BLOCKS:
            raise SystemExit(f"BULLA_FAIL_CLOSED_BACKLOG_TOO_LARGE blocks={backlog}")

    logs = get_logs(start, safe_head)
    cluster = {str(x).lower() for x in state.get("cluster_wallets") or []}
    cluster.add(KNOWN_WHALE)
    sent = set(state.get("sent_event_ids") or [])
    candidates = []
    label_cache = {}
    balance_cache = {}

    def label(addr):
        if addr not in label_cache:
            label_cache[addr] = bscscan_exchange_label(addr)
        return label_cache[addr]

    def balance(addr):
        if addr not in balance_cache:
            balance_cache[addr] = token_balance(addr)
        return balance_cache[addr]

    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        src = decode_topic_address(topics[1])
        dst = decode_topic_address(topics[2])
        if src == ZERO or dst == ZERO:
            continue
        amount = int(log.get("data") or "0x0", 16) / 1e18
        if amount <= 0:
            continue

        # Swaps/LP movements are market activity, not wallet-cluster evidence.
        if src == PAIR or dst == PAIR:
            continue

        event_id = f"{str(log.get('transactionHash') or '').lower()}:{str(log.get('logIndex') or '').lower()}"
        if event_id in sent:
            continue

        equal_block = CLUSTER_LOW <= amount <= CLUSTER_HIGH

        # Learn a ~40M destination only when its live on-chain balance independently
        # confirms that it sits inside the cluster-size band.
        if equal_block:
            try:
                if CLUSTER_LOW <= balance(dst) <= CLUSTER_HIGH:
                    cluster.add(dst)
            except Exception as e:
                print("BULLA_BALANCE_CHECK_FAILED", dst, type(e).__name__)

        src_cluster = src in cluster
        dst_cluster = dst in cluster
        material = (
            amount >= MATERIAL_ANY
            or (amount >= MATERIAL_CLUSTER and (src_cluster or dst_cluster))
            or equal_block
        )
        if not material:
            continue

        src_label = label(src)
        dst_label = label(dst)
        kind, why, round_trip = classify_event(
            src, dst, amount, cluster, src_label, dst_label, state
        )
        if round_trip:
            kind = "CEX_ROUND_TRIP"
            why = "A tracked cluster wallet shows a CEX outflow/deposit lifecycle; do not interpret a withdrawal as standalone accumulation."
        if src in cluster and dst_label:
            kind = "DISTRIBUTION_RISK"

        candidates.append({
            "event_id": event_id,
            "kind": kind,
            "why": why,
            "amount": amount,
            "src": src,
            "dst": dst,
            "src_label": src_label or "UNKNOWN",
            "dst_label": dst_label or "UNKNOWN",
            "tx": str(log.get("transactionHash") or ""),
            "block": int(log.get("blockNumber", "0x0"), 16),
        })

    state["cluster_wallets"] = sorted(cluster)
    state["last_scanned_block"] = safe_head

    market = None
    try:
        market = market_snapshot()
        state["last_market"] = market
    except Exception as e:
        print("BULLA_MARKET_SNAPSHOT_UNAVAILABLE", type(e).__name__, str(e)[:180])

    # The activation run establishes a forward-only boundary and does not send old
    # transfers to Telegram as if they had just happened.
    if first_run:
        for x in candidates:
            sent.add(x["event_id"])
        state["sent_event_ids"] = list(sent)[-500:]
        save_state(state)
        print(
            "BULLA_BOOTSTRAP_COMPLETE_NO_TELEGRAM",
            {"from_block": start, "to_block": safe_head, "logs": len(logs), "cluster_wallets": len(cluster)},
        )
        return

    if not candidates:
        state["sent_event_ids"] = list(sent)[-500:]
        save_state(state)
        print(
            "BULLA_NO_MATERIAL_EVENT",
            {"from_block": start, "to_block": safe_head, "logs": len(logs), "cluster_wallets": len(cluster)},
        )
        return

    for x in candidates[:MAX_EVENTS_IN_MESSAGE]:
        try:
            x["observed_at"] = block_time(hex(x["block"]))
        except Exception:
            x["observed_at"] = None

    headline = candidates[0]["kind"] if len(candidates) == 1 else "MULTI_EVENT"
    lines = [
        "🚨 BULLA CLUSTER ALERT — WALLET500",
        "⚠️ MANUAL DECISION ONLY — NO AUTOMATIC TRADE",
        f"Event: {headline}",
        "Token: BULLA | Chain: BNB",
        f"CA: {CA}",
        f"Pair: {PAIR}",
    ]
    if market:
        lines += [
            f"💰 Exact-pair price: ${market['price_usd']:.6f}",
            f"💧 Liquidity: {money(market['liquidity_usd'])} | Vol 1H: {money(market['volume_h1'])}",
            f"🟢/🔴 1H buys/sells: {market['buys_h1']}/{market['sells_h1']}",
        ]
    else:
        lines.append("⚠️ Exact-pair market snapshot unavailable; holder-flow alert is on-chain only.")

    for i, x in enumerate(candidates[:MAX_EVENTS_IN_MESSAGE], 1):
        when = x.get("observed_at") or f"block {x['block']}"
        lines += [
            "",
            f"{i}) {x['kind']} | {amount_text(x['amount'])}",
            f"From: {x['src']} [{x['src_label']}]",
            f"To:   {x['dst']} [{x['dst_label']}]",
            f"Time: {when}",
            f"Why: {x['why']}",
            f"Tx: https://bscscan.com/tx/{x['tx']}",
        ]
    extra = len(candidates) - MAX_EVENTS_IN_MESSAGE
    if extra > 0:
        lines += ["", f"+{extra} additional material on-chain event(s) in this scan."]
    lines += [
        "",
        "CEX labels are shown only when verified from the address page; otherwise UNKNOWN.",
        "A CEX withdrawal alone is NOT counted as smart-money accumulation.",
        f"🔗 {DEX_URL}",
        f"🕒 scan {utcnow()}",
    ]
    send_telegram("\n".join(lines))

    # Mark only after Telegram acknowledgement, minimizing silent loss.
    for x in candidates:
        sent.add(x["event_id"])
    state["sent_event_ids"] = list(sent)[-500:]
    save_state(state)
    print("BULLA_STATE_UPDATED_AFTER_TELEGRAM", {"events": len(candidates), "to_block": safe_head})


if __name__ == "__main__":
    main()
