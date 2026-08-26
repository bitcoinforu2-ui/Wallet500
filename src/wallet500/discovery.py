from collections import Counter, defaultdict


def _account_keys(tx: dict) -> list[dict]:
    msg = (((tx or {}).get("transaction") or {}).get("message") or {})
    keys = msg.get("accountKeys") or []
    out = []
    for key in keys:
        if isinstance(key, str):
            out.append({"pubkey": key, "signer": False, "writable": False})
        elif isinstance(key, dict):
            out.append(key)
    return out


def _token_owners(tx: dict) -> set[str]:
    owners = set()
    meta = (tx or {}).get("meta") or {}
    for side in ("preTokenBalances", "postTokenBalances"):
        for bal in meta.get(side, []) or []:
            owner = bal.get("owner")
            if owner:
                owners.add(owner)
    return owners


def discover_wallet_candidates(adapter, token_mints: list[str], signatures_per_token: int = 40, max_transactions: int = 160) -> list[dict]:
    score = Counter()
    evidence = defaultdict(lambda: {"tokens": set(), "signer_hits": 0, "owner_hits": 0, "writable_hits": 0})
    tx_seen = 0
    for mint in token_mints:
        for sig in adapter.signatures_for_address(mint, limit=signatures_per_token):
            if tx_seen >= max_transactions:
                break
            if sig.get("err") is not None or not sig.get("signature"):
                continue
            tx = adapter.transaction(sig["signature"])
            if not tx:
                continue
            tx_seen += 1
            for key in _account_keys(tx):
                address = key.get("pubkey")
                if not address:
                    continue
                if key.get("signer"):
                    score[address] += 5.0
                    evidence[address]["signer_hits"] += 1
                    evidence[address]["tokens"].add(mint)
                elif key.get("writable"):
                    score[address] += 0.5
                    evidence[address]["writable_hits"] += 1
            for owner in _token_owners(tx):
                score[owner] += 3.0
                evidence[owner]["owner_hits"] += 1
                evidence[owner]["tokens"].add(mint)
        if tx_seen >= max_transactions:
            break
    rows = []
    for address, raw in score.most_common():
        ev = evidence[address]
        token_count = len(ev["tokens"])
        final = min(100.0, raw + max(0, token_count - 1) * 8.0)
        rows.append({"address": address, "score": round(final, 2), "token_count": token_count, "tokens": sorted(ev["tokens"]), "signer_hits": ev["signer_hits"], "owner_hits": ev["owner_hits"], "writable_hits": ev["writable_hits"]})
    return rows
