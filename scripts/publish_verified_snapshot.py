#!/usr/bin/env python3
"""Publish an immutable verified Live Scan snapshot safely onto main.

Rules:
- validate manifest identity, hashes, and strict validation before publishing;
- never overwrite a path that changed on main after the source scan;
- bind publication proof to the exact real-alerts.json digest;
- if real-alerts changed after the source scan, treat this snapshot as superseded
  (successful no-op) instead of a false infrastructure failure;
- use commit-tree compare-and-swap retries, never force-push.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def git(*args: str, env: dict[str, str] | None = None, input_text: str | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        ["git", *args], text=True, input=input_text,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False
    )
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p


def validate_manifest(root: Path, source_run: int, source_sha: str) -> tuple[dict, bytes]:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Missing verified snapshot manifest")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("version") != 1:
        raise RuntimeError("Unsupported verified snapshot manifest version")
    if str(manifest.get("source_run_id")) != str(source_run):
        raise RuntimeError("Snapshot source run mismatch")
    if str(manifest.get("source_sha")) != source_sha:
        raise RuntimeError("Snapshot source SHA mismatch")
    if manifest.get("strict_validation") != "PASS":
        raise RuntimeError("Snapshot strict validation is not PASS")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("Verified snapshot contains no data paths")

    files_root = (root / "files").resolve()
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("Malformed snapshot item")
        rel = str(item.get("path") or "")
        kind = item.get("kind")
        pp = PurePosixPath(rel)
        if not rel.startswith("data/") or pp.is_absolute() or ".." in pp.parts:
            raise RuntimeError(f"Unsafe snapshot path: {rel!r}")
        if rel in seen:
            raise RuntimeError(f"Duplicate snapshot path: {rel}")
        seen.add(rel)
        target = (files_root / rel).resolve()
        if files_root not in target.parents:
            raise RuntimeError(f"Path escaped snapshot root: {rel}")
        if kind == "file":
            if not target.is_file():
                raise RuntimeError(f"Missing snapshot file: {rel}")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest != item.get("sha256"):
                raise RuntimeError(f"SHA256 mismatch: {rel}")
        elif kind == "delete":
            if target.exists():
                raise RuntimeError(f"Delete item unexpectedly contains file: {rel}")
        else:
            raise RuntimeError(f"Invalid snapshot item kind for {rel}: {kind!r}")

    real_item = next((x for x in items if x.get("path") == "data/real-alerts.json" and x.get("kind") == "file"), None)
    if not real_item or not real_item.get("sha256"):
        raise RuntimeError("Verified snapshot missing immutable real-alerts.json digest")
    return manifest, manifest_bytes


def changed_since(source_sha: str, parent: str, rel: str) -> bool:
    p = git("diff", "--quiet", source_sha, parent, "--", rel, check=False)
    if p.returncode not in (0, 1):
        raise RuntimeError(f"Unable to compare freshness for {rel}: {p.stderr.strip()}")
    return p.returncode == 1


def published_run(parent: str, watermark: str) -> int:
    p = git("show", f"{parent}:{watermark}", check=False)
    if p.returncode:
        return 0
    try:
        return int(json.loads(p.stdout).get("run_id") or 0)
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-dir", required=True)
    ap.add_argument("--source-run-id", required=True, type=int)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--attempts", type=int, default=80)
    args = ap.parse_args()

    root = Path(args.snapshot_dir).resolve()
    source_run = args.source_run_id
    source_sha = args.source_sha.strip()
    manifest, manifest_bytes = validate_manifest(root, source_run, source_sha)
    items = manifest["items"]
    watermark = "data/publish-evidence.json"
    real_path = "data/real-alerts.json"

    git("fetch", "--no-tags", "origin", source_sha)

    real_item = next(x for x in items if x.get("path") == real_path and x.get("kind") == "file")
    real_digest = str(real_item["sha256"])
    generation_id = f"live-scan:{source_run}:{source_sha}"
    proof = {
        "version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "VERIFIED_PUBLISHED_SNAPSHOT",
        "run_id": source_run,
        "source_run_id": source_run,
        "source_sha": source_sha,
        "generation_id": generation_id,
        "strict_validation": "PASS",
        "scope": "data/",
        "real_alerts_sha256": real_digest,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "proof_rule": "ATOMIC_WITH_VERIFIED_SNAPSHOT_AND_BOUND_TO_REAL_ALERTS_SHA256",
    }
    proof_text = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    proof_blob = git("hash-object", "-w", "--stdin", input_text=proof_text).stdout.strip()

    blobs: dict[str, str] = {}
    for item in items:
        if item["kind"] != "file" or item["path"] == watermark:
            continue
        rel = item["path"]
        blobs[rel] = git("hash-object", "-w", str(root / "files" / rel)).stdout.strip()

    print(f"VERIFIED_SNAPSHOT_VALID paths={len(items)} real_alerts_sha256={real_digest}")

    for attempt in range(1, max(1, args.attempts) + 1):
        git("fetch", "origin", "main")
        parent = git("rev-parse", "origin/main").stdout.strip()
        current = published_run(parent, watermark)
        if current >= source_run:
            print(f"VERIFIED_SNAPSHOT_STALE source_run={source_run} published_run={current}")
            return 0

        index_path = Path(tempfile.gettempdir()) / f"wallet500-verified-{os.getpid()}-{attempt}.index"
        skipped: list[str] = []
        applied: list[str] = []
        try:
            index_path.unlink(missing_ok=True)
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = str(index_path)
            git("read-tree", parent, env=env)
            for item in items:
                rel = item["path"]
                if rel == watermark:
                    # Add proof only if the bound real-alerts path is still eligible below.
                    continue
                if changed_since(source_sha, parent, rel):
                    skipped.append(rel)
                    continue
                if item["kind"] == "file":
                    git("update-index", "--add", "--cacheinfo", f"100644,{blobs[rel]},{rel}", env=env)
                else:
                    git("update-index", "--force-remove", "--", rel, env=env, check=False)
                applied.append(rel)

            if real_path in skipped:
                # A newer real-alerts generation is already on main. This old verified
                # snapshot is safely superseded; publishing its proof would be invalid.
                print(f"VERIFIED_SNAPSHOT_SUPERSEDED source_run={source_run} reason=REAL_ALERTS_NEWER_ON_MAIN")
                return 0

            git("update-index", "--add", "--cacheinfo", f"100644,{proof_blob},{watermark}", env=env)
            applied.append(watermark)
            tree = git("write-tree", env=env).stdout.strip()
        finally:
            index_path.unlink(missing_ok=True)

        if skipped:
            print("VERIFIED_SNAPSHOT_PRESERVED_NEWER " + ",".join(skipped[:40]))
        parent_tree = git("rev-parse", f"{parent}^{{tree}}").stdout.strip()
        if tree == parent_tree:
            print("VERIFIED_SNAPSHOT_NO_SAFE_CHANGE")
            return 0

        commit = git("commit-tree", tree, "-p", parent,
                     input_text=f"data: publish verified live scan {source_run}\n").stdout.strip()
        pushed = git("push", "origin", f"{commit}:refs/heads/main", check=False)
        if pushed.returncode == 0:
            print(f"VERIFIED_PUBLISH_PROOF_OK generation={generation_id} applied={len(applied)} preserved={len(skipped)}")
            return 0
        print(f"VERIFIED_PUBLISH_RETRY attempt={attempt}", flush=True)
        time.sleep(min(2.0, 0.08 * attempt))

    raise RuntimeError(f"Verified snapshot publisher failed after {args.attempts} bounded attempts")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"VERIFIED_SNAPSHOT_FATAL {exc}", file=os.sys.stderr)
        raise SystemExit(1)
