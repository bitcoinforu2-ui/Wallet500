from __future__ import annotations

import json
import os
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
STATE = ROOT / "data/unified-watch-state.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_json(url: str):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "Wallet500-UnifiedWatch/1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def token_id_matches(value: str, contract: str) -> bool:
    value = str(value or "").lower()
    contract = contract.lower()
    return value == contract or value.endswith("_" + contract)


def live_exact_pair(token: dict, max_spread_pct: float) -> dict:
    network = token["network"]
    pair_address = token["pair"].lower()
    contract = token["contract"].lower()

    gt_raw = http_json(f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{pair_address}")
    obj = gt_raw.get("data") or {}
    attrs = obj.get("attributes") or {}
    rel = obj.get("relationships") or {}
    base = (((rel.get("base_token") or {}).get("data") or {}).get("id") or "")
    quote = (((rel.get("quote_token") or {}).get("data") or {}).get("id") or "")
    if token_id_matches(base, contract):
        gt_price = float(attrs.get("base_token_price_usd") or 0)
    elif token_id_matches(quote, contract):
        gt_price = float(attrs.get("quote_token_price_usd") or 0)
    else:
        raise RuntimeError("EXACT_PAIR_IDENTITY_MISMATCH_GT")
    if gt_price <= 0:
        raise RuntimeError("GT_PRICE_MISSING")

    volume = attrs.get("volume_usd") or {}
    txns = attrs.get("transactions") or {}
    h1 = txns.get("h1") or {}
    change = attrs.get("price_change_percentage") or {}
    gt = {
        "price": gt_price,
        "liquidity": float(attrs.get("reserve_in_usd") or 0),
        "volume_h1": float(volume.get("h1") or 0),
        "volume_h24": float(volume.get("h24") or 0),
        "buys_h1": int(h1.get("buys") or 0),
        "sells_h1": int(h1.get("sells") or 0),
        "change_h1": float(change.get("h1") or 0),
        "change_h24": float(change.get("h24") or 0),
    }
    if gt["liquidity"] <= 0:
        raise RuntimeError("GT_LIQUIDITY_MISSING")

    ds_raw = http_json(f"https://api.dexscreener.com/latest/dex/pairs/{'ethereum' if network == 'eth' else network}/{pair_address}")
    pairs = ds_raw.get("pairs") or []
    ds = next((p for p in pairs if str(p.get("pairAddress") or "").lower() == pair_address), None)
    if not ds:
        raise RuntimeError("EXACT_PAIR_MISSING_DS")
    base_ca = str(((ds.get("baseToken") or {}).get("address") or "")).lower()
    quote_ca = str(((ds.get("quoteToken") or {}).get("address") or "")).lower()
    if base_ca == contract:
        ds_price = float(ds.get("priceUsd") or 0)
    elif quote_ca == contract:
        quote_price_native = float(ds.get("priceNative") or 0)
        if quote_price_native <= 0:
            raise RuntimeError("DS_QUOTE_ORIENTATION_UNSUPPORTED")
        # DexScreener priceUsd is base-side. Do not invert an unverified USD quote.
        raise RuntimeError("DS_TOKEN_NOT_BASE_FAIL_CLOSED")
    else:
        raise RuntimeError("EXACT_PAIR_IDENTITY_MISMATCH_DS")
    if ds_price <= 0:
        raise RuntimeError("DS_PRICE_MISSING")

    median = statistics.median([gt_price, ds_price])
    spread_pct = ((max(gt_price, ds_price) - min(gt_price, ds_price)) / median) * 100 if median else 999
    if spread_pct > max_spread_pct:
        raise RuntimeError(f"SOURCE_DATA_MISMATCH:{spread_pct:.3f}%")

    return {**gt, "price": median, "gt_price": gt_price, "ds_price": ds_price, "spread_pct": spread_pct, "observed_at": now_iso()}


def crossed_up(previous: float, current: float, level: float) -> bool:
    return previous > 0 and previous < level <= current


def crossed_down(previous: float, current: float, level: float) -> bool:
    return previous > 0 and previous >= level > current


def money(value: float) -> str:
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.2f}"


def send_telegram(message: str) -> None:
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        raise RuntimeError("TELEGRAM_SECRETS_NOT_CONFIGURED")
    payload = urllib.parse.urlencode({"chat_id": chat, "text": message[:4000], "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{bot}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        body = json.load(response)
        if not body.get("ok"):
            raise RuntimeError("TELEGRAM_SEND_FAILED")


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"version": 1, "tokens": {}}
    token_state = state.setdefault("tokens", {})
    max_spread = float((config.get("data_integrity") or {}).get("max_price_source_spread_pct", 2.0))

    for token in config.get("tokens") or []:
        symbol = token["symbol"].upper()
        previous = token_state.get(symbol) or {}
        try:
            live = live_exact_pair(token, max_spread)
        except Exception as exc:
            # Fail closed: bad/stale/conflicting market data never becomes a trading alert.
            print(symbol, "UNVERIFIED", str(exc))
            continue

        prev_price = float(previous.get("price") or 0)
        prev_liq = float(previous.get("liquidity") or 0)
        prev_vol = float(previous.get("volume_h1") or 0)
        triggers: list[str] = []

        if prev_price > 0:
            for level in token.get("up_levels") or []:
                level = float(level)
                if crossed_up(prev_price, live["price"], level):
                    triggers.append(f"BREAK_ABOVE_{level:g}")
            for level in token.get("down_levels") or []:
                level = float(level)
                if crossed_down(prev_price, live["price"], level):
                    triggers.append(f"LOSS_BELOW_{level:g}")

            liq_drop = float(token.get("liquidity_drop_pct") or 25)
            if prev_liq > 0 and live["liquidity"] < prev_liq * (1 - liq_drop / 100):
                triggers.append(f"LIQUIDITY_DROP_GT_{liq_drop:g}PCT")

            min_vol = float(token.get("min_volume_h1_for_momentum") or 0)
            multiple = float(token.get("volume_acceleration_multiple") or 2)
            if prev_vol > 0 and live["volume_h1"] >= max(min_vol, prev_vol * multiple) and live["price"] > prev_price:
                triggers.append("PRICE_PLUS_VOLUME_ACCELERATION")

        # First observation establishes a verified baseline; it never fabricates a crossing.
        token_state[symbol] = {
            "price": live["price"],
            "liquidity": live["liquidity"],
            "volume_h1": live["volume_h1"],
            "volume_h24": live["volume_h24"],
            "buys_h1": live["buys_h1"],
            "sells_h1": live["sells_h1"],
            "spread_pct": live["spread_pct"],
            "observed_at": live["observed_at"],
        }

        print(symbol, "VERIFIED", token_state[symbol], "TRIGGERS", triggers)
        if triggers:
            risk = any(t.startswith("LOSS_") or "LIQUIDITY_DROP" in t for t in triggers)
            label = "RISK" if risk else "REVIVAL_BUILDING"
            if symbol == "SOPH" and live["price"] >= 0.006 and live["volume_h1"] >= float(token.get("min_volume_h1_for_momentum") or 0):
                label = "SECOND_WAVE_CONFIRMED"
            icon = "⚠️" if risk else "🔥"
            msg = "\n".join([
                f"{icon} {symbol} | WALLET500 UNIFIED WATCH | {label}",
                f"CURRENT VERIFIED PRICE: ${live['price']:.8f}",
                f"VENUE/SOURCE: GeckoTerminal exact pair + DexScreener exact pair | spread {live['spread_pct']:.2f}%",
                f"OBSERVED: {live['observed_at']}",
                f"Previous verified: ${prev_price:.8f}",
                f"1H {live['change_h1']:+.2f}% | 24H {live['change_h24']:+.2f}%",
                f"Liquidity {money(live['liquidity'])} | Vol 1H {money(live['volume_h1'])} | Vol 24H {money(live['volume_h24'])}",
                f"Buys/Sells 1H: {live['buys_h1']}/{live['sells_h1']}",
                "TRIGGERS: " + ", ".join(triggers),
                "Research/position watch only — not an automatic trade or Wallet500 REAL_ALERT.",
                f"CA: {token['contract']}",
                f"Pair: {token['pair']}",
                token["dex_url"],
            ])
            send_telegram(msg)

    state["updated_at"] = now_iso()
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
