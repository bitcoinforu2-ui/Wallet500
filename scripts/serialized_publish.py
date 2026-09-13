#!/usr/bin/env python3
"""Repository-wide serialization wrapper for Wallet500 state publication.

The expensive research/scanning stages remain fully parallel. Only the final
main-ref mutation is serialized through a short-lived GitHub ref lease. The
wrapped publisher remains scripts/atomic_publish.py, so all existing freshness,
CAS, fail-on-newer, exact-pair and no-hindsight behavior stays unchanged.

The lease is fail-closed, owner-verified on release, and can recover a stale
lease left behind by a cancelled runner. It never force-updates main.

GitHub's Git Data API can reject large blob request bodies even when the file is
valid for the repository. Callers may keep requesting --github-api-cas; this
wrapper transparently upgrades only large local payloads to --hybrid-cas, which
uploads blob objects once through git and still performs the final main update
with the same non-force CAS semantics.
"""
from __future__ import annotations

import os
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path

import atomic_publish

LOCK_REF = "refs/heads/wallet500-publish-lock"
LOCK_API_REF = "/git/ref/heads/wallet500-publish-lock"
LOCK_API_DELETE = "/git/refs/heads/wallet500-publish-lock"
LOCK_TTL_SECONDS = 300
LOCK_WAIT_SECONDS = 210
# Keep comfortably below request-body limits. Hybrid CAS is also cheaper than
# JSON/base64 Git Data API upload for state files of this size.
GITHUB_API_BLOB_SOFT_LIMIT = 8 * 1024 * 1024
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


def _route_large_payload_to_hybrid() -> None:
    """Upgrade GitHub-API CAS to hybrid CAS when a local payload is large.

    We intentionally inspect only argv entries that resolve to regular files;
    values belonging to --message/--base/--attempts therefore cannot be mistaken
    for payloads. Explicit --hybrid-cas callers are left untouched.
    """
    if "--github-api-cas" not in sys.argv or "--hybrid-cas" in sys.argv:
        return
    large: list[tuple[str, int]] = []
    for raw in sys.argv[1:]:
        if raw.startswith("-"):
            continue
        p = Path(raw)
        try:
            if p.is_file():
                size = p.stat().st_size
                if size >= GITHUB_API_BLOB_SOFT_LIMIT:
                    large.append((raw, size))
        except OSError:
            continue
    if not large:
        return
    idx = sys.argv.index("--github-api-cas")
    sys.argv[idx] = "--hybrid-cas"
    summary = ",".join(f"{path}:{size}" for path, size in large[:8])
    print(
        "SERIALIZED_PUBLISH_TRANSPORT_UPGRADE "
        f"github-api-cas->hybrid-cas reason=large-payload files={summary}",
        flush=True,
    )


def main() -> int:
    _route_large_payload_to_hybrid()
    token, repo, lock_sha = acquire_lock()
    try:
        # atomic_publish.main() consumes the (possibly transport-upgraded) argv,
        # preserving caller freshness, fail-on-newer, message and path options.
        return atomic_publish.main()
    finally:
        _delete_if_same(token, repo, lock_sha, "LOCK_RELEASE")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SERIALIZED_PUBLISH_FATAL {exc}", file=sys.stderr)
        raise SystemExit(1)
