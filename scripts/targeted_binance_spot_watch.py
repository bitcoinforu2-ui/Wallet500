from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = DATA / "unified-watch-config.json"
STATE = DATA / "targeted-binance-spot-watch-state.json"
REPORT = DATA / "targeted-binance-spot-watch-report.json"
CMS_URLS = (
    "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query?catalogId=48&pageNo=1&pageSize=50",
    "https://www.binance.com/bapi/apex/v1/public/apex/cms/article/list/query?type=1&catalogId=48&pageNo=1&pageSize=50",
)
SPOT_API_BASES = ("https://api.binance.com", "https://api1.binance.com", "https://api2.binance.com", "https://api3.binance.com")
UA = {"User-Agent": "Wallet500-TargetedBinanceSpotWatch/1.0", "Accept": "application/json,text/html,*/*"}
NEGATIVE = ("FUTURES", "FUTURE", "PERPETUAL", "MARGIN", "DELIST", "REMOVE", "SUSPEND")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _http_json(url: str, timeout: int = 18) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(getattr(r, "status", 200) or 200), json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw[:500]}
        return int(exc.code), payload


def announcement_title_matches(title: object, target: dict) -> bool:
    text = re.sub(r"\s+", " ", str(title or "")).strip().upper()
    symbol = str(target.get("symbol") or "").strip().upper()
    projects = [str(x).strip().upper() for x in target.get("project_names") or [] if str(x).strip()]
    if not text or not symbol or not projects:
        return False
    if not any(re.search(rf"(?<![A-Z0-9]){re.escape(p)}(?![A-Z0-9])", text) for p in projects):
        return False
    symbol_ok = bool(re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", text))
    symbol_ok = symbol_ok or any(str(m).upper() in text for m in target.get("spot_symbols") or [])
    if not symbol_ok or any(x in text for x in NEGATIVE):
        return False
    if "BINANCE WILL LIST" in text:
        return True
    return "SPOT" in text and bool(re.search(r"\bLIST(?:S|ED|ING)?\b", text) or ("TRADING" in text and any(x in text for x in ("OPEN", "START", "COMMENCE", "AVAILABLE"))))


def _article_rows(value: Any) -> list[dict]:
    out: list[dict] = []
    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if isinstance(x.get("title"), str):
                out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(value)
    return out


def cms_listing_signals(payload: Any, target: dict, source_url: str) -> list[dict]:
    out, seen = [], set()
    for row in _article_rows(payload):
        title = str(row.get("title") or "").strip()
        if not announcement_title_matches(title, target):
            continue
        code = str(row.get("code") or row.get("articleCode") or row.get("id") or "").strip()
        fp = code or hashlib.sha256(title.encode()).hexdigest()[:24]
        if fp in seen:
            continue
        seen.add(fp)
        url = f"https://www.binance.com/en/support/announcement/detail/{code}" if code and re.fullmatch(r"[A-Za-z0-9_-]{8,128}", code) else source_url
        out.append({"kind": "OFFICIAL_SPOT_ANNOUNCEMENT", "fingerprint": fp, "title": title, "source": "BINANCE_OFFICIAL_ANNOUNCEMENTS", "source_url": url})
    return out


def _announcement_probe(target: dict) -> tuple[list[dict], list[dict]]:
    health: list[dict] = []
    for url in CMS_URLS:
        try:
            status, payload = _http_json(url)
            rows = _article_rows(payload) if status == 200 else []
            if status == 200 and rows:
                signals = cms_listing_signals(payload, target, url)
                health.append({"source": url, "ok": True, "http_status": status, "article_rows": len(rows), "matches": len(signals)})
                return signals, health
            health.append({"source": url, "ok": False, "http_status": status, "error": "NO_ARTICLE_ROWS" if status == 200 else "HTTP_ERROR"})
        except Exception as exc:
            health.append({"source": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:240]})
    return [], health


def _spot_probe(market: str) -> tuple[dict | None, list[dict]]:
    market = str(market or "").upper().strip()
    health: list[dict] = []
    for base in SPOT_API_BASES:
        url = f"{base}/api/v3/exchangeInfo?symbol={urllib.parse.quote(market, safe='')}"
        try:
            status, payload = _http_json(url)
            if status in (400, 404) and isinstance(payload, dict) and int(payload.get("code") or 0) == -1121:
                health.append({"source": base, "ok": True, "present": False, "http_status": status})
                return None, health
            if status == 200 and isinstance(payload, dict):
                exact = next((x for x in payload.get("symbols") or [] if isinstance(x, dict) and str(x.get("symbol") or "").upper() == market), None)
                health.append({"source": base, "ok": True, "present": bool(exact), "http_status": status})
                return exact, health
            health.append({"source": base, "ok": False, "http_status": status, "error": "UNEXPECTED_RESPONSE"})
        except Exception as exc:
            health.append({"source": base, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:240]})
    return None, health


def _signal_id(target: dict, signal: dict) -> str:
    raw = f"{str(target.get('symbol') or '').upper()}|{signal.get('kind')}|{signal.get('fingerprint')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _send(text: str) -> tuple[bool, object]:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return False, "TELEGRAM_SECRETS_MISSING"
    body = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode())
        return (True, (payload.get("result") or {}).get("message_id")) if payload.get("ok") is True else (False, "TELEGRAM_API_OK_FALSE")
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:240]


def _message(target: dict, signals: list[dict], at: str) -> str:
    symbol = str(target.get("symbol") or "UNKNOWN").upper()
    project = str((target.get("project_names") or [symbol])[0])
    lines = [f"🔥🔥🔥 BINANCE SPOT CATALYST — {symbol}", f"{project} ({symbol})", "✅ Official Binance Spot evidence confirmed", f"Detected UTC: {at}"]
    for s in signals:
        lines.append(f"• Spot market: {s.get('market')} · status={s.get('status') or 'present'}" if s.get("kind") == "BINANCE_SPOT_MARKET_PRESENT" else f"• Official announcement: {s.get('title')}")
    if target.get("contract"):
        lines.append(f"Contract: {target.get('contract')}")
    if target.get("pair"):
        lines.append(f"DEX pair: {target.get('pair')}")
    if target.get("dex_url"):
        lines.append(f"🔗 DEX: {target.get('dex_url')}")
    urls = list(dict.fromkeys(str(s.get("source_url") or "") for s in signals if s.get("source_url")))
    lines.extend(f"🔗 Binance source: {u}" for u in urls[:3])
    lines += ["⚠️ Catalyst alert only — not a BUY signal.", "No automatic trade. Existing Wallet500 safety/entry gates remain unchanged.", "Verified Intelligence. The Pure Truth."]
    return "\n".join(lines)


def run() -> int:
    cfg = _load(CONFIG, {})
    targets = [x for x in cfg.get("targeted_binance_spot_watches") or [] if isinstance(x, dict) and x.get("enabled") is True]
    state = _load(STATE, {"version": 1, "sent": {}})
    if not isinstance(state, dict):
        state = {"version": 1, "sent": {}}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}
    at, target_reports, errors = _now(), [], []
    delivered = confirmed = announcement_sources_ok = 0

    for target in targets:
        symbol = str(target.get("symbol") or "").upper().strip()
        announcements, ann_health = _announcement_probe(target)
        announcement_sources_ok += sum(bool(x.get("ok")) for x in ann_health)
        market_signals, market_health = [], []
        for market in target.get("spot_symbols") or []:
            exact, h = _spot_probe(str(market)); market_health.extend(h)
            if exact:
                market_signals.append({"kind": "BINANCE_SPOT_MARKET_PRESENT", "fingerprint": f"{str(market).upper()}:{str(exact.get('status') or 'PRESENT').upper()}", "market": str(market).upper(), "status": exact.get("status"), "source": "BINANCE_SPOT_EXCHANGE_INFO", "source_url": f"https://www.binance.com/en/trade/{symbol}_USDT?type=spot"})
        signals = announcements + market_signals
        confirmed += len(signals)
        fresh = [s for s in signals if _signal_id(target, s) not in sent]
        delivered_ids = []
        if fresh:
            ok, message_id = _send(_message(target, fresh, at))
            if ok:
                delivered += 1
                for s in fresh:
                    sid = _signal_id(target, s); delivered_ids.append(sid)
                    sent[sid] = {"symbol": symbol, "kind": s.get("kind"), "fingerprint": s.get("fingerprint"), "sent_at": at, "telegram_message_id": message_id, "source": s.get("source"), "source_url": s.get("source_url")}
            else:
                errors.append({"symbol": symbol, "error": str(message_id), "fresh_signal_count": len(fresh)})
        target_reports.append({"symbol": symbol, "project_names": target.get("project_names") or [], "spot_symbols": target.get("spot_symbols") or [], "contract": target.get("contract"), "pair": target.get("pair"), "announcement_health": ann_health, "spot_market_health": market_health, "confirmed_signals": signals, "fresh_signal_count": len(fresh), "delivered_signal_ids": delivered_ids})

    coverage_ok = (not targets) or announcement_sources_ok > 0
    status = "DELIVERY_ERROR" if errors else ("DEGRADED_ANNOUNCEMENT_COVERAGE" if not coverage_ok else ("CONFIRMED_SIGNAL_ACTIVE" if confirmed else "WATCHING"))
    state.update({"version": 1, "updated_at": at, "sent": sent})
    report = {"version": 1, "updated_at": at, "mode": "TARGETED_BINANCE_SPOT_OFFICIAL_ONLY", "status": status, "target_count": len(targets), "confirmed_signal_count": confirmed, "delivered_count": delivered, "delivery_error_count": len(errors), "announcement_coverage_ok": coverage_ok, "targets": target_reports, "delivery_errors": errors, "truth_contract": {"binance_official_sources_only": True, "project_name_plus_exact_ticker_required_for_announcement": True, "futures_perpetual_margin_delisting_rejected": True, "spot_exchange_info_exact_market_is_definitive_market_presence": True, "alpha_or_futures_presence_alone_never_means_spot_listing": True, "automatic_trade": False, "listing_signal_is_not_buy_signal": True}}
    _write(STATE, state); _write(REPORT, report); print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if errors else (3 if not coverage_ok else 0)


if __name__ == "__main__":
    raise SystemExit(run())
