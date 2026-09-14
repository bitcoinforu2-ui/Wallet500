from __future__ import annotations

import json
from pathlib import Path

from . import cex_early_revival_pending as base


def _base_symbol_fixed(value) -> str:
    text = str(value or "").split(":", 1)[0].upper().strip()
    text = text.replace("-", "").replace("_", "").replace("/", "")
    if text.endswith("USDTM"):
        return text[:-5]
    if text.endswith("USDT"):
        return text[:-4]
    return text


def run(data_dir: Path = base.DATA) -> dict:
    original = base._base_symbol
    base._base_symbol = _base_symbol_fixed
    try:
        payload = base.run(data_dir)
    finally:
        base._base_symbol = original

    # Canonicalize persisted rows so legacy aliases such as
    # MLPUSDT:MLP_USDT cannot consume independent identity-queue slots.
    for row in payload.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        symbol = _base_symbol_fixed(row.get("symbol"))
        if symbol:
            row["symbol"] = f"{symbol}USDT"
    payload["canonical_symbol_alias_collapse"] = True
    path = data_dir / "cex-early-revival-pending.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
