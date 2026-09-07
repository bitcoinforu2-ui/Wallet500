#!/usr/bin/env python3
"""Contention-safe publisher for Wallet500 generated files.

Publishes only the requested paths onto the newest origin/main using a temporary
Git index and commit-tree. It never rebases a generated-data commit and never
force-pushes. If a requested path changed on main after this run's base commit,
the default is to preserve the newer main copy. Coherent multi-file publishers
can opt into --fail-on-newer and recompute their whole snapshot instead.
"""
from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STALE_RECOMPUTE_EXIT = 75
DEFAULT_GIT_NAME = "wallet500-atomic-publisher"
DEFAULT_GIT_EMAIL = "wallet500-atomic-publisher@users.noreply.github.com"


def git(*args: str, env: dict[str, str] | None = None, input_text: str | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        ["git", *args],
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p


def ensure_git_identity() -> None:
    """Guarantee commit-tree can run even on a pristine GitHub runner."""
    name = git("config", "--get", "user.name", check=False).stdout.strip()
    email = git("config", "--get", "user.email", check=False).stdout.strip()
    if not name:
        git("config", "user.name", DEFAULT_GIT_NAME)
    if not email:
        git("config", "user.email", DEFAULT_GIT_EMAIL)


def changed_since(base: str, parent: str, rel: str) -> bool:
    p = git("diff", "--quiet", base, parent, "--", rel, check=False)
    if p.returncode not in (0, 1):
        raise RuntimeError(f"unable to compare freshness for {rel}: {p.stderr.strip()}")
    return p.returncode == 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="repository-relative paths to publish")
    ap.add_argument("--message", default="data: atomic generated-data publish")
    ap.add_argument("--attempts", type=int, default=80)
    ap.add_argument("--base", default=None, help="source/base SHA; defaults to current HEAD")
    ap.add_argument("--allow-newer-overwrite", action="store_true",
                    help="allow a local path to overwrite a path changed on main since base")
    ap.add_argument("--fail-on-newer", action="store_true",
                    help=f"return {STALE_RECOMPUTE_EXIT} if any requested path changed since base")
    args = ap.parse_args()

    if args.allow_newer_overwrite and args.fail_on_newer:
        raise RuntimeError("--allow-newer-overwrite and --fail-on-newer are mutually exclusive")

    paths: list[str] = []
    seen: set[str] = set()
    for raw in args.paths:
        rel = raw.strip().lstrip("./")
        if not rel or rel.startswith("../") or "/../" in rel or rel in seen:
            continue
        seen.add(rel)
        paths.append(rel)
    if not paths:
        print("ATOMIC_PUBLISH_NO_PATHS")
        return 0

    ensure_git_identity()
    base = args.base or git("rev-parse", "HEAD").stdout.strip()
    git("fetch", "--no-tags", "origin", base, check=False)

    blobs: dict[str, str | None] = {}
    for rel in paths:
        p = Path(rel)
        if p.is_file():
            blobs[rel] = git("hash-object", "-w", str(p)).stdout.strip()
        elif not p.exists():
            blobs[rel] = None
        else:
            raise RuntimeError(f"refusing non-file publish path: {rel}")

    for attempt in range(1, max(1, args.attempts) + 1):
        git("fetch", "origin", "main")
        parent = git("rev-parse", "origin/main").stdout.strip()

        newer = [rel for rel in paths if changed_since(base, parent, rel)]
        if newer and args.fail_on_newer:
            print("ATOMIC_PUBLISH_RECOMPUTE_REQUIRED " + ",".join(newer[:40]))
            return STALE_RECOMPUTE_EXIT

        index_path = Path(tempfile.gettempdir()) / f"wallet500-atomic-{os.getpid()}-{attempt}.index"
        applied: list[str] = []
        preserved: list[str] = []
        try:
            index_path.unlink(missing_ok=True)
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = str(index_path)
            git("read-tree", parent, env=env)
            for rel in paths:
                if not args.allow_newer_overwrite and rel in newer:
                    preserved.append(rel)
                    continue
                blob = blobs[rel]
                if blob is None:
                    git("update-index", "--force-remove", "--", rel, env=env, check=False)
                else:
                    git("update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}", env=env)
                applied.append(rel)
            tree = git("write-tree", env=env).stdout.strip()
        finally:
            index_path.unlink(missing_ok=True)

        if preserved:
            print("ATOMIC_PUBLISH_PRESERVED_NEWER " + ",".join(preserved[:40]))
        parent_tree = git("rev-parse", f"{parent}^{{tree}}").stdout.strip()
        if tree == parent_tree:
            print("ATOMIC_PUBLISH_NO_SAFE_CHANGE")
            return 0

        commit = git("commit-tree", tree, "-p", parent, input_text=args.message + "\n").stdout.strip()
        pushed = git("push", "origin", f"{commit}:refs/heads/main", check=False)
        if pushed.returncode == 0:
            print(f"ATOMIC_PUBLISH_OK commit={commit} applied={len(applied)} preserved={len(preserved)}")
            return 0

        sleep_s = min(2.0, 0.08 * attempt) + random.uniform(0.02, 0.18)
        print(f"ATOMIC_PUBLISH_RETRY attempt={attempt} sleep={sleep_s:.2f}", flush=True)
        time.sleep(sleep_s)

    print(f"ATOMIC_PUBLISH_EXHAUSTED attempts={args.attempts}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ATOMIC_PUBLISH_FATAL {exc}", file=sys.stderr)
        raise SystemExit(1)
