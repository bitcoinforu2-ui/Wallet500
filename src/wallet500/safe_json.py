"""Strict and durable JSON primitives for truth-bearing Wallet500 paths.

Never turn corrupt truth/state data into a silent empty dataset. Readers choose
missing/degraded semantics explicitly, while state writers replace files atomically
so production never observes a partially written JSON document.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
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


def load_json_fail_closed(path: str | Path, default: Any) -> Any:
    """Allow an absent optional state, but never reinterpret corruption as empty.

    This is the correct semantic for persisted dedupe/lifecycle state: the first
    run may legitimately have no file, while a damaged existing file must stop the
    lane rather than re-arm alerts or erase lifecycle history.
    """
    result = load_json_state(path, default=default)
    if result.state == MISSING:
        return copy.deepcopy(default)
    if result.state != VALID:
        raise RuntimeError(f"STATE_DATA_{result.state}:{result.path}:{result.error}")
    return result.value


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """Durably replace a JSON document without exposing partial contents."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp, 0o644)
        except OSError:
            pass
        os.replace(tmp, p)
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        try:
            dir_fd = os.open(p.parent, os.O_RDONLY | directory_flag)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
