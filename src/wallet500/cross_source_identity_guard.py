from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA = Path("data")
CORRELATION = DATA / "cross-source-correlation.json"
WATCHLIST = DATA / "manual-watchlist.json"
EVM_CHAINS = {"ethereum", "bsc", "arbitrum", "base"}
EVM_ZERO = "0x0000000000000000000000000000000000000000"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _invalid_exact_identity(chain: object, token: object) -> bool:
    c = str(chain or "").strip().lower()
    t = str(token or "").strip().lower()
    return c in EVM_CHAINS and t == EVM_ZERO


def _strip_cross_source_enrichment(row: dict) -> dict:
    clean = dict(row)
    for key in list(clean):
        if key.startswith("cross_source_"):
            clean.pop(key, None)
    return clean


def sanitize(correlation: dict, watchlist: list) -> tuple[dict, list, dict]:
    corr = dict(correlation or {})
    assets_raw = corr.get("assets") if isinstance(corr.get("assets"), dict) else {}
    assets: dict[str, dict] = {}
    dropped_keys: list[str] = []

    for key, raw in assets_raw.items():
        if not isinstance(raw, dict):
            continue
        if _invalid_exact_identity(raw.get("chain"), raw.get("token")):
            dropped_keys.append(str(key))
            continue
        assets[str(key)] = raw

    corr["assets"] = assets
    counts = dict(corr.get("counts") or {})
    counts["correlated_assets"] = len(assets)
    counts["exact_identity_assets"] = sum(
        1 for row in assets.values() if row.get("identity_confidence") == "EXACT_CHAIN_CONTRACT"
    )
    counts["multi_source_assets"] = sum(
        1 for row in assets.values() if int(row.get("source_confirmation_count") or 0) >= 2
    )
    counts["double_or_better_exchange_assets"] = sum(
        1 for row in assets.values() if int(row.get("exchange_confirmation_count") or 0) >= 2
    )
    counts["invalid_exact_identity_dropped"] = len(dropped_keys)
    corr["counts"] = counts
    policy = dict(corr.get("policy") or {})
    policy["invalid_identity"] = (
        "EVM zero/native sentinel is never an exact token contract; generated correlation/watchlist surfaces fail closed while source ledgers remain immutable"
    )
    corr["policy"] = policy
    corr["identity_guard"] = {
        "fail_closed": True,
        "source_ledgers_modified": False,
        "invalid_exact_identity_dropped": len(dropped_keys),
        "dropped_asset_keys": dropped_keys,
    }

    out_watch: list[dict] = []
    removed_generated = 0
    stripped_enrichment = 0
    for raw in watchlist if isinstance(watchlist, list) else []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        invalid = _invalid_exact_identity(row.get("chain"), row.get("token") or row.get("contract") or row.get("mint"))
        invalid_cross_key = str(row.get("cross_source_asset_key") or "").lower() in {x.lower() for x in dropped_keys}
        if invalid and row.get("source") == "CROSS_SOURCE_CORRELATION":
            removed_generated += 1
            continue
        if invalid_cross_key or invalid:
            cleaned = _strip_cross_source_enrichment(row)
            if cleaned != row:
                stripped_enrichment += 1
            row = cleaned
        out_watch.append(row)

    stats = {
        "invalid_exact_identity_dropped": len(dropped_keys),
        "generated_watch_rows_removed": removed_generated,
        "non_generated_rows_enrichment_stripped": stripped_enrichment,
    }
    return corr, out_watch, stats


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    corr_path = data / CORRELATION.name
    watch_path = data / WATCHLIST.name
    corr = _load(corr_path, {})
    watch = _load(watch_path, [])
    out_corr, out_watch, stats = sanitize(corr, watch)
    _write(corr_path, out_corr)
    _write(watch_path, out_watch)
    return stats


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
