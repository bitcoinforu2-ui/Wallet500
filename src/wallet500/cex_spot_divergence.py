from __future__ import annotations

import json
import urllib.request
from pathlib import Path

DATA = Path("data")
UA = {"User-Agent": "Wallet500/2.1", "Accept": "application/json"}
DEX_PAIR_URL = "https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair}"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _f(value):
    try:
        return float(value)
    except Exception:
        return None


def _get_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def classify(cex_move: float | None, dex_move: float | None) -> str:
    if cex_move is None or dex_move is None:
        return "INSUFFICIENT_COVERAGE"
    if cex_move >= 8 and dex_move <= -8:
        return "CEX_UP_DEX_DOWN_STRONG_DIVERGENCE"
    if cex_move <= -8 and dex_move >= 8:
        return "CEX_DOWN_DEX_UP_STRONG_DIVERGENCE"
    if cex_move * dex_move < 0 and abs(cex_move - dex_move) >= 10:
        return "CEX_DEX_DIRECTIONAL_DIVERGENCE"
    if abs(cex_move - dex_move) >= 20:
        return "CEX_DEX_MAGNITUDE_DIVERGENCE"
    return "CEX_DEX_BROADLY_ALIGNED"


def run(data_dir: Path = DATA) -> dict:
    path = data_dir / "cex-spot-identity-radar.json"
    payload = _load(path, {})
    rows = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    enriched = 0
    errors = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        chain = str(row.get("chain") or "").strip().lower()
        pair = str(row.get("pair_address") or "").strip()
        if row.get("identity_status") != "DEX_VERIFIED" or not chain or not pair:
            row["cex_dex_divergence"] = {"status": "INSUFFICIENT_COVERAGE"}
            continue
        cex_move = _f(row.get("change_24h_max_pct"))
        try:
            data = _get_json(DEX_PAIR_URL.format(chain=chain, pair=pair))
            pairs = data.get("pairs") if isinstance(data, dict) else []
            exact = None
            for p in pairs or []:
                if str(p.get("pairAddress") or "").lower() == pair.lower():
                    exact = p
                    break
            if not exact:
                row["cex_dex_divergence"] = {"status": "INSUFFICIENT_COVERAGE", "reason": "EXACT_PAIR_NOT_RETURNED"}
                continue
            dex_move = _f((exact.get("priceChange") or {}).get("h24"))
            status = classify(cex_move, dex_move)
            row["cex_dex_divergence"] = {
                "status": status,
                "cex_move_24h_pct": cex_move,
                "dex_move_24h_pct": dex_move,
                "delta_pct_points": None if cex_move is None or dex_move is None else round(cex_move - dex_move, 4),
                "exact_pair_verified": True,
                "source": "DEXSCREENER_EXACT_PAIR_H24",
                "research_only": True,
            }
            enriched += 1
        except Exception as exc:
            row["cex_dex_divergence"] = {"status": "INSUFFICIENT_COVERAGE", "reason": f"{type(exc).__name__}: {exc}"[:200]}
            errors.append({"symbol": row.get("symbol"), "error": f"{type(exc).__name__}: {exc}"[:200]})
    payload["cex_dex_divergence_enrichment"] = {
        "status": "OK" if not errors else "DEGRADED_PARTIAL",
        "enriched_count": enriched,
        "error_count": len(errors),
        "truth_contract": {
            "exact_pair_only": True,
            "research_only": True,
            "production_gates_unchanged": True,
            "missing_data_never_scored_as_zero": True,
        },
    }
    _write(path, payload)
    return payload["cex_dex_divergence_enrichment"]


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
