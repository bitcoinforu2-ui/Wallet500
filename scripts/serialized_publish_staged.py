#!/usr/bin/env python3
"""Publish exactly the files already staged by a legacy workflow.

This is the compatibility bridge for Wallet500 workflows that historically did:
  git add ...; git commit ...; git fetch/rebase; git push origin HEAD:main

The workflow keeps its existing, explicit staging selection, while this helper
hands the staged paths to the repository-wide serialized/atomic publisher. That
removes main-ref races without widening what the workflow is allowed to publish.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TRANSIENT_PREFIXES = (
    "src/wallet500.egg-info/",
    ".pytest_cache/",
)
TRANSIENT_PARTS = {"__pycache__"}


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def staged_paths() -> list[str]:
    p = git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRD")
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", errors="replace")[:800])
    out: list[str] = []
    seen: set[str] = set()
    for raw in p.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="strict").strip().lstrip("./")
        if not rel or rel.startswith("../") or "/../" in rel:
            raise RuntimeError(f"unsafe staged path: {rel!r}")
        if rel.startswith(TRANSIENT_PREFIXES) or any(part in TRANSIENT_PARTS for part in Path(rel).parts):
            print(f"SERIALIZED_STAGED_SKIP_TRANSIENT {rel}", flush=True)
            continue
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--attempts", type=int, default=80)
    ap.add_argument("--github-api-cas", action="store_true")
    args = ap.parse_args()

    paths = staged_paths()
    if not paths:
        print("SERIALIZED_STAGED_NO_CHANGE")
        return 0

    cmd = [
        sys.executable,
        "scripts/serialized_publish.py",
        "--message",
        args.message,
        "--attempts",
        str(max(1, args.attempts)),
    ]
    if args.github_api_cas:
        cmd.append("--github-api-cas")
    cmd.extend(paths)

    print(
        "SERIALIZED_STAGED_PUBLISH "
        f"files={len(paths)} paths={','.join(paths[:30])}",
        flush=True,
    )
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SERIALIZED_STAGED_FATAL {type(exc).__name__}:{exc}", file=sys.stderr)
        raise SystemExit(1)
