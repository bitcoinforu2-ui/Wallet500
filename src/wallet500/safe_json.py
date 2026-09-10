"""Strict JSON loading for truth-bearing Wallet500 paths.

Never turn corrupt/missing truth data into a silent empty dataset. Callers may
choose fail-closed or degraded behavior explicitly from the returned state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VALID = "VALID"
MISSING = "MISSING"
CORRUPT = "CORRUPT"


@dataclass(frozen=True)
class JsonLoad:
    state: str
    value: Any
    path: str
    error: str | None = None

    @property
    def valid(self) -> bool:
        return self.state == VALID


def load_json_state(path: str | Path, *, default: Any = None) -> JsonLoad:
    p = Path(path)
    if not p.exists():
        return JsonLoad(MISSING, default, str(p), "FILE_NOT_FOUND")
    try:
        raw = p.read_text(encoding="utf-8")
        if not raw.strip():
            return JsonLoad(CORRUPT, default, str(p), "EMPTY_FILE")
        return JsonLoad(VALID, json.loads(raw), str(p), None)
    except Exception as exc:
        return JsonLoad(CORRUPT, default, str(p), f"{type(exc).__name__}:{exc}")


def require_json(path: str | Path) -> Any:
    result = load_json_state(path)
    if not result.valid:
        raise RuntimeError(f"TRUTH_DATA_{result.state}:{result.path}:{result.error}")
    return result.value
