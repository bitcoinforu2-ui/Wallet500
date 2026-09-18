#!/usr/bin/env python3
"""Repository-wide serialization wrapper for Wallet500 state publication.

The expensive research/scanning stages remain fully parallel. Only the final
main-ref mutation is serialized through a short-lived GitHub ref lease. The
wrapped publisher remains scripts/atomic_publish.py, so all existing freshness,
CAS, fail-on-newer, exact-pair and no-hindsight behavior stays unchanged.

The lease is fail-closed, owner-verified on release, and can recover a stale
lease left behind by a cancelled runner. It never force-updates main.

GitHub's Git Data API can reject large blob request bodies even when the file is
valid for the repository. Temporary staging refs can also be rejected by the
GitHub Actions token when their ancestry contains workflow changes. Under the
repository-wide lease, large or explicitly hybrid publications therefore use
the atomic publisher's direct git CAS path: it rebuilds the generated-data tree
on the newest origin/main and performs a normal non-force push to main. This
keeps large blobs out of the Git Data API and avoids staging refs while retaining
freshness checks and fast-forward-only publication.

Directory payloads are expanded deterministically into regular files before the
underlying atomic publisher runs. This preserves archive shards without asking
the lower-level publisher to guess directory semantics.
"""
from __future__ import annotations

import base64
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
GITHUB_API_BLOB_SOFT_LIMIT = 8 * 1024 * 1024
_LOCK_RE = re.compile(r"\bcreated_epoch=(\d+)\b")
_VALUE_OPTIONS = {"--base", "--message", "--attempts"}


def _checkout_token() -> str:
    """Read checkout's persisted credential without ever printing it."""
    extra = atomic_publish.git(
        "config", "--get", "http.https://github.com/.extraheader", check=False
    ).stdout.strip()
    prefix = "AUTHORIZATION: basic "
    if not extra.lower().startswith(prefix.lower()):
        return ""
    encoded = extra[len(prefix):].strip()
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return ""
    if ":" not in decoded:
        return ""
    return decoded.split(":", 1)[1].strip()


def _identity() -> tuple[str, str, str, str]:
    token = os.environ.get("GITHUB_TOKEN", "").strip() or _checkout_token()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "local").strip() or "local"
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1").strip() or "1"
    if not token or not repo or "/" not in repo:
        raise RuntimeError("SERIALIZED_PUBLISH_REQUIRES_GITHUB_CREDENTIAL_AND_REPOSITORY")
    return token, repo, run_id, run_attempt


def _new_lock_commit(token: str, repo: str, run_id: str, run_attempt: str) -> tuple[str, int]:
    parent = atomic_publish.api_ref_sha(token, repo)
    _, parent_commit = atomic_publish.api_request(
        token, repo, "GET", f"/git/commits/{urllib.parse.quote(parent, safe='')}"
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
        token, repo, "GET", LOCK_API_REF, allowed=(200, 404)
    )
    if status == 404:
        return None
    sha = str((ref.get("object") or {}).get("sha") or "")
    if not sha:
        raise RuntimeError("SERIALIZED_PUBLISH_LOCK_REF_SHA_MISSING")
    _, commit = atomic_publish.api_request(
        token, repo, "GET", f"/git/commits/{urllib.parse.quote(sha, safe='')}"
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
        token, repo, "DELETE", LOCK_API_DELETE, allowed=(204, 404)
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


def _payload_indexes(argv: list[str]) -> list[int]:
    indexes: list[int] = []
    skip_value = False
    for i in range(1, len(argv)):
        raw = argv[i]
        if skip_value:
            skip_value = False
            continue
        if raw in _VALUE_OPTIONS:
            skip_value = True
            continue
        if raw.startswith("-"):
            continue
        indexes.append(i)
    return indexes


def _expand_directory_payloads() -> None:
    original = list(sys.argv)
    payload_indexes = set(_payload_indexes(original))
    expanded: list[str] = [original[0]]
    total_expanded = 0
    for i, raw in enumerate(original[1:], start=1):
        if i not in payload_indexes:
            expanded.append(raw)
            continue
        p = Path(raw)
        if not p.is_dir():
            expanded.append(raw)
            continue
        files = sorted(
            str(child.as_posix())
            for child in p.rglob("*")
            if child.is_file()
        )
        if not files:
            raise RuntimeError(f"SERIALIZED_PUBLISH_EMPTY_DIRECTORY {raw}")
        expanded.extend(files)
        total_expanded += len(files)
        print(
            f"SERIALIZED_PUBLISH_DIRECTORY_EXPANDED path={raw} files={len(files)}",
            flush=True,
        )
    if total_expanded:
        sys.argv[:] = expanded


def _route_unsafe_large_transports_to_direct_git() -> None:
    large: list[tuple[str, int]] = []
    for i in _payload_indexes(sys.argv):
        raw = sys.argv[i]
        p = Path(raw)
        try:
            if p.is_file():
                size = p.stat().st_size
                if size >= GITHUB_API_BLOB_SOFT_LIMIT:
                    large.append((raw, size))
        except OSError:
            continue

    if "--hybrid-cas" in sys.argv:
        sys.argv.remove("--hybrid-cas")
        print(
            "SERIALIZED_PUBLISH_TRANSPORT_ROUTE hybrid-cas->direct-git-cas "
            "reason=staging-ref-workflow-permission-risk",
            flush=True,
        )
        return

    if "--github-api-cas" not in sys.argv or not large:
        return

    sys.argv.remove("--github-api-cas")
    summary = ",".join(f"{path}:{size}" for path, size in large[:8])
    print(
        "SERIALIZED_PUBLISH_TRANSPORT_ROUTE "
        f"github-api-cas->direct-git-cas reason=large-payload files={summary}",
        flush=True,
    )


def main() -> int:
    _expand_directory_payloads()
    _route_unsafe_large_transports_to_direct_git()
    token, repo, lock_sha = acquire_lock()
    try:
        return atomic_publish.main()
    finally:
        _delete_if_same(token, repo, lock_sha, "LOCK_RELEASE")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SERIALIZED_PUBLISH_FATAL {exc}", file=sys.stderr)
        raise SystemExit(1)
