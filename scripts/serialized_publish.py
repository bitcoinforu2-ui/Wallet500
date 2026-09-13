#!/usr/bin/env python3
"""Repository-wide serialization wrapper for Wallet500 state publication.

The expensive research/scanning stages remain fully parallel. Only the final
main-ref mutation is serialized through a short-lived GitHub ref lease. The
wrapped publisher remains scripts/atomic_publish.py, so all existing freshness,
CAS, fail-on-newer, exact-pair and no-hindsight behavior stays unchanged.

The lease is fail-closed, owner-verified on release, and can recover a stale
lease left behind by a cancelled runner. It never force-updates main.
"""
from __future__ import annotations

import os
import random
import re
import sys
import time
import urllib.parse

import atomic_publish

LOCK_REF = "refs/heads/wallet500-publish-lock"
LOCK_API_REF = "/git/ref/heads/wallet500-publish-lock"
LOCK_API_DELETE = "/git/refs/heads/wallet500-publish-lock"
LOCK_TTL_SECONDS = 300
LOCK_WAIT_SECONDS = 210
_LOCK_RE = re.compile(r"\bcreated_epoch=(\d+)\b")


def _identity() -> tuple[str, str, str, str]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "local").strip() or "local"
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1").strip() or "1"
    if not token or not repo or "/" not in repo:
        raise RuntimeError("SERIALIZED_PUBLISH_REQUIRES_GITHUB_TOKEN_AND_REPOSITORY")
    return token, repo, run_id, run_attempt


def _new_lock_commit(token: str, repo: str, run_id: str, run_attempt: str) -> tuple[str, int]:
    parent = atomic_publish.api_ref_sha(token, repo)
    _, parent_commit = atomic_publish.api_request(
        token,
        repo,
        "GET",
        f"/git/commits/{urllib.parse.quote(parent, safe='')}",
    )
    tree_sha = str((parent_commit.get("tree") or {}).get("sha") or "")
    if not tree_sha:
        raise RuntimeError("SERIALIZED_PUBLISH_MAIN_TREE_MISSING")
    created = int(time.time())
    _, lock_commit = atomic_publish.api_request(
        token,
        repo,
        "POST",
        "/git/commits",
        {
            "message": (
                "WALLET500_PUBLISH_LOCK "
                f"run_id={run_id} run_attempt={run_attempt} created_epoch={created}"
            ),
            "tree": tree_sha,
            "parents": [parent],
        },
    )
    sha = str(lock_commit.get("sha") or "")
    if not sha:
        raise RuntimeError("SERIALIZED_PUBLISH_LOCK_COMMIT_MISSING")
    return sha, created


def _current_lock(token: str, repo: str) -> tuple[str, int | None] | None:
    status, ref = atomic_publish.api_request(
        token,
        repo,
        "GET",
        LOCK_API_REF,
        allowed=(200, 404),
    )
    if status == 404:
        return None
    sha = str((ref.get("object") or {}).get("sha") or "")
    if not sha:
        raise RuntimeError("SERIALIZED_PUBLISH_LOCK_REF_SHA_MISSING")
    _, commit = atomic_publish.api_request(
        token,
        repo,
        "GET",
        f"/git/commits/{urllib.parse.quote(sha, safe='')}",
    )
    message = str(commit.get("message") or "")
    if not message.startswith("WALLET500_PUBLISH_LOCK "):
        raise RuntimeError("SERIALIZED_PUBLISH_FOREIGN_LOCK_REF")
    match = _LOCK_RE.search(message)
    created = int(match.group(1)) if match else None
    return sha, created


def _delete_if_same(token: str, repo: str, expected_sha: str, label: str) -> bool:
    current = _current_lock(token, repo)
    if current is None:
        return True
    sha, _ = current
    if sha != expected_sha:
        print(
            f"SERIALIZED_PUBLISH_{label}_SKIP expected={expected_sha} actual={sha}",
            flush=True,
        )
        return False
    atomic_publish.api_request(
        token,
        repo,
        "DELETE",
        LOCK_API_DELETE,
        allowed=(204, 404),
    )
    print(f"SERIALIZED_PUBLISH_{label}_OK sha={expected_sha}", flush=True)
    return True


def acquire_lock() -> tuple[str, str, str]:
    token, repo, run_id, run_attempt = _identity()
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        lock_sha, created = _new_lock_commit(token, repo, run_id, run_attempt)
        status, _ = atomic_publish.api_request(
            token,
            repo,
            "POST",
            "/git/refs",
            {"ref": LOCK_REF, "sha": lock_sha},
            allowed=(201, 422),
        )
        if status == 201:
            print(
                f"SERIALIZED_PUBLISH_LOCK_ACQUIRED sha={lock_sha} attempt={attempt} "
                f"created_epoch={created}",
                flush=True,
            )
            return token, repo, lock_sha

        current = _current_lock(token, repo)
        if current is not None:
            current_sha, current_created = current
            if current_created is None:
                raise RuntimeError("SERIALIZED_PUBLISH_LOCK_TIMESTAMP_MISSING")
            age = max(0, int(time.time()) - current_created)
            if age > LOCK_TTL_SECONDS:
                print(
                    f"SERIALIZED_PUBLISH_STALE_LOCK age_seconds={age} sha={current_sha}",
                    flush=True,
                )
                _delete_if_same(token, repo, current_sha, "STALE_LOCK_DELETE")
                continue

        delay = min(2.0, 0.18 + attempt * 0.04) + random.uniform(0.03, 0.20)
        print(
            f"SERIALIZED_PUBLISH_LOCK_WAIT attempt={attempt} sleep={delay:.2f}",
            flush=True,
        )
        time.sleep(delay)

    raise RuntimeError(f"SERIALIZED_PUBLISH_LOCK_TIMEOUT wait_seconds={LOCK_WAIT_SECONDS}")


def main() -> int:
    token, repo, lock_sha = acquire_lock()
    try:
        # atomic_publish.main() consumes the original argv, preserving every
        # caller option (CAS transport, fail-on-newer, attempts, message, paths).
        return atomic_publish.main()
    finally:
        _delete_if_same(token, repo, lock_sha, "LOCK_RELEASE")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SERIALIZED_PUBLISH_FATAL {exc}", file=sys.stderr)
        raise SystemExit(1)
