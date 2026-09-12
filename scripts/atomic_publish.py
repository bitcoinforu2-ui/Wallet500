#!/usr/bin/env python3
"""Contention-safe publisher for Wallet500 generated files.

Publishes only the requested paths onto the newest main revision. The default
Git transport uses a temporary index and commit-tree. High-contention GitHub
Actions writers can opt into --github-api-cas, which performs the same
non-force compare-and-swap through the GitHub Git Data API and avoids repeated
multi-second shallow fetches on this large repository.

It never rebases a generated-data commit and never force-pushes. If a requested
path changed on main after this run's base commit, the default is to preserve
the newer main copy. Coherent multi-file publishers can opt into
--fail-on-newer and recompute their whole snapshot instead.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

STALE_RECOMPUTE_EXIT = 75
DEFAULT_GIT_NAME = "wallet500-atomic-publisher"
DEFAULT_GIT_EMAIL = "wallet500-atomic-publisher@users.noreply.github.com"
API_VERSION = "2022-11-28"
TRANSIENT_API_STATUSES = {429, 500, 502, 503, 504}
API_REQUEST_ATTEMPTS = 5


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


def api_request(
    token: str,
    repo: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    allowed: tuple[int, ...] = (200, 201),
) -> tuple[int, dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}{path}"
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")

    for attempt in range(1, API_REQUEST_ATTEMPTS + 1):
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-GitHub-Api-Version", API_VERSION)
        req.add_header("User-Agent", "wallet500-atomic-publisher")
        if body is not None:
            req.add_header("Content-Type", "application/json")

        status = 0
        data: dict[str, Any] = {}
        retry_after: float | None = None
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8")) if raw else {}
                status = int(resp.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                data = {"message": raw.decode("utf-8", errors="replace")[:500]}
            status = int(exc.code)
            retry_header = exc.headers.get("Retry-After") if exc.headers else None
            if retry_header:
                try:
                    retry_after = max(0.0, min(float(retry_header), 30.0))
                except ValueError:
                    retry_after = None
        except (urllib.error.URLError, TimeoutError) as exc:
            data = {"message": str(exc)[:500]}
            status = 0

        if status in allowed:
            return status, data

        transient = status == 0 or status in TRANSIENT_API_STATUSES
        if transient and attempt < API_REQUEST_ATTEMPTS:
            delay = retry_after if retry_after is not None else min(4.0, 0.35 * (2 ** (attempt - 1)))
            delay += random.uniform(0.03, 0.20)
            label = status if status else "network"
            print(
                f"ATOMIC_API_RETRY method={method} path={path} status={label} "
                f"attempt={attempt}/{API_REQUEST_ATTEMPTS} sleep={delay:.2f}",
                flush=True,
            )
            time.sleep(delay)
            continue

        msg = str(data.get("message") or "unknown GitHub API error")[:500]
        raise RuntimeError(f"GitHub API {method} {path} failed status={status or 'network'}: {msg}")

    raise RuntimeError(f"GitHub API {method} {path} exhausted retries")


def api_ref_sha(token: str, repo: str) -> str:
    _, data = api_request(token, repo, "GET", "/git/ref/heads/main")
    sha = str((data.get("object") or {}).get("sha") or "")
    if not sha:
        raise RuntimeError("GitHub API main ref returned no SHA")
    return sha


def api_tree_state(token: str, repo: str, commit_sha: str, wanted: set[str]) -> tuple[str, dict[str, str | None]]:
    _, commit = api_request(token, repo, "GET", f"/git/commits/{urllib.parse.quote(commit_sha, safe='')}")
    tree_sha = str((commit.get("tree") or {}).get("sha") or "")
    if not tree_sha:
        raise RuntimeError(f"GitHub API commit {commit_sha} returned no tree SHA")
    _, tree = api_request(token, repo, "GET", f"/git/trees/{tree_sha}?recursive=1")
    if tree.get("truncated") is True:
        raise RuntimeError("GitHub API recursive tree is truncated; refusing unsafe freshness comparison")
    found: dict[str, str | None] = {p: None for p in wanted}
    for entry in tree.get("tree") or []:
        path = str(entry.get("path") or "")
        if path in wanted and entry.get("type") == "blob":
            found[path] = str(entry.get("sha") or "") or None
    return tree_sha, found


def github_api_publish(args: argparse.Namespace, paths: list[str], base: str) -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo or "/" not in repo:
        raise RuntimeError("--github-api-cas requires GITHUB_TOKEN and GITHUB_REPOSITORY")

    wanted = set(paths)
    _, base_state = api_tree_state(token, repo, base, wanted)

    blobs: dict[str, str | None] = {}
    for rel in paths:
        p = Path(rel)
        if p.is_file():
            _, blob = api_request(
                token,
                repo,
                "POST",
                "/git/blobs",
                {"content": p.read_text(encoding="utf-8"), "encoding": "utf-8"},
            )
            sha = str(blob.get("sha") or "")
            if not sha:
                raise RuntimeError(f"GitHub API blob upload returned no SHA for {rel}")
            blobs[rel] = sha
        elif not p.exists():
            blobs[rel] = None
        else:
            raise RuntimeError(f"refusing non-file publish path: {rel}")

    for attempt in range(1, max(1, args.attempts) + 1):
        parent = api_ref_sha(token, repo)
        parent_tree, parent_state = api_tree_state(token, repo, parent, wanted)
        newer = [rel for rel in paths if parent_state.get(rel) != base_state.get(rel)]
        if newer and args.fail_on_newer:
            print("ATOMIC_PUBLISH_RECOMPUTE_REQUIRED " + ",".join(newer[:40]))
            return STALE_RECOMPUTE_EXIT

        preserved: list[str] = []
        entries: list[dict[str, Any]] = []
        applied: list[str] = []
        for rel in paths:
            if not args.allow_newer_overwrite and rel in newer:
                preserved.append(rel)
                continue
            blob_sha = blobs[rel]
            entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob_sha})
            applied.append(rel)

        if preserved:
            print("ATOMIC_PUBLISH_PRESERVED_NEWER " + ",".join(preserved[:40]))
        if not entries:
            print("ATOMIC_PUBLISH_NO_SAFE_CHANGE")
            return 0

        _, tree = api_request(token, repo, "POST", "/git/trees", {"base_tree": parent_tree, "tree": entries})
        new_tree = str(tree.get("sha") or "")
        if not new_tree:
            raise RuntimeError("GitHub API tree creation returned no SHA")
        if new_tree == parent_tree:
            print("ATOMIC_PUBLISH_NO_SAFE_CHANGE")
            return 0

        _, commit = api_request(
            token,
            repo,
            "POST",
            "/git/commits",
            {"message": args.message, "tree": new_tree, "parents": [parent]},
        )
        commit_sha = str(commit.get("sha") or "")
        if not commit_sha:
            raise RuntimeError("GitHub API commit creation returned no SHA")

        status, _ = api_request(
            token,
            repo,
            "PATCH",
            "/git/refs/heads/main",
            {"sha": commit_sha, "force": False},
            allowed=(200, 422),
        )
        if status == 200:
            print(f"ATOMIC_PUBLISH_OK commit={commit_sha} applied={len(applied)} preserved={len(preserved)} transport=github-api-cas")
            return 0

        sleep_s = min(0.55, 0.035 * attempt) + random.uniform(0.01, 0.06)
        print(f"ATOMIC_PUBLISH_RETRY attempt={attempt} sleep={sleep_s:.2f} transport=github-api-cas", flush=True)
        time.sleep(sleep_s)

    print(f"ATOMIC_PUBLISH_EXHAUSTED attempts={args.attempts} transport=github-api-cas", file=sys.stderr)
    return 1


def git_publish(args: argparse.Namespace, paths: list[str], base: str) -> int:
    ensure_git_identity()
    git("fetch", "--no-tags", "--depth=1", "origin", base, check=False)

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
        git("fetch", "--no-tags", "--depth=1", "origin", "main")
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
    ap.add_argument("--github-api-cas", action="store_true",
                    help="use fast non-force GitHub Git Data API CAS instead of repeated git fetch/push")
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

    base = args.base or git("rev-parse", "HEAD").stdout.strip()
    if args.github_api_cas:
        return github_api_publish(args, paths, base)
    return git_publish(args, paths, base)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ATOMIC_PUBLISH_FATAL {exc}", file=sys.stderr)
        raise SystemExit(1)
