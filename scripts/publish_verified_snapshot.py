#!/usr/bin/env python3
"""Publish an immutable verified Live Scan snapshot safely onto main.

Rules:
- validate manifest identity, hashes, and strict validation before publishing;
- never overwrite a path that changed on main after the source scan;
- bind publication proof to the effective canonical real-alerts.json digest;
- preserve a newer, independently verified coherent decision snapshot as one unit;
- only preserve a newer decision snapshot when every proof-bound file matches;
- reject immutable source snapshots whose policy metadata differs from the
  canonical 90d / $15K veteran-revival contract, including stricter drift;
- if real-alerts changed without a valid coherent decision proof, treat the scan as
  superseded instead of weakening verification;
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

from wallet500.policy import (
    CANONICAL_MIN_EXECUTION_LIQUIDITY_USD,
    CANONICAL_MIN_MARKET_AGE_DAYS,
)

DECISION_PROOF = "data/decision-publish-evidence.json"
DECISION_HASH_PATHS = {
    "revival_universe": "data/revival-1000-latest.json",
    "cex_revival": "data/cex-revival-radar.json",
    "active_candidates": "data/active-qualified-candidates.json",
    "active_age_gate": "data/active-qualified-age-gate.json",
    "candidate_evidence": "data/candidate-evidence-envelope.json",
    "real_alerts": "data/real-alerts.json",
    "revival_funnel": "data/revival-funnel-diagnostics.json",
    "cross_signal_fusion": "data/cross-signal-fusion-v2.json",
    "production_status": "data/production-status.json",
    "decision_integrity": "data/decision-snapshot-integrity.json",
}
# These policy-bearing decision paths can also be present in the Live Scan artifact.
# A fresher verified generation must be preserved as one unit rather than mixed.
DECISION_OWNED_LIVE_PATHS = set(DECISION_HASH_PATHS.values())

PRODUCTION_MIN_MARKET_AGE_DAYS = CANONICAL_MIN_MARKET_AGE_DAYS
PRODUCTION_MIN_EXECUTION_LIQUIDITY_USD = CANONICAL_MIN_EXECUTION_LIQUIDITY_USD


def git(*args: str, env: dict[str, str] | None = None, input_text: str | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        ["git", *args], text=True, input=input_text,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False
    )
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p


def git_bytes(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    p = subprocess.run(
        ["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if check and p.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {p.stderr.decode('utf-8', 'replace').strip()}"
        )
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

    real_item = next(
        (x for x in items if x.get("path") == "data/real-alerts.json" and x.get("kind") == "file"),
        None,
    )
    if not real_item or not real_item.get("sha256"):
        raise RuntimeError("Verified snapshot missing immutable real-alerts.json digest")
    if not _snapshot_production_status_passes_contract(root):
        raise RuntimeError(
            "Verified snapshot production-status policy differs from canonical 90d / $15K contract"
        )
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


def _parent_bytes(parent: str, rel: str) -> bytes | None:
    p = git_bytes("show", f"{parent}:{rel}", check=False)
    return p.stdout if p.returncode == 0 else None


def _bound_real_alerts_passes_production_contract(raw: bytes) -> bool:
    """Fail closed unless the bound REAL ALERT feed declares the exact contract."""
    try:
        feed = json.loads(raw.decode("utf-8"))
        truth = feed.get("truth_contract")
        if not isinstance(truth, dict):
            return False
        age = int(truth.get("minimum_market_age_days"))
        liquidity = float(truth.get("minimum_execution_pool_liquidity_usd"))
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        age == PRODUCTION_MIN_MARKET_AGE_DAYS
        and liquidity == PRODUCTION_MIN_EXECUTION_LIQUIDITY_USD
        and truth.get("exact_onchain_identity_required") is True
        and truth.get("exact_dex_pair_required") is True
        and truth.get("symbol_only_never_actionable") is True
        and truth.get("cex_only_never_real_alert") is True
    )


def _snapshot_production_status_passes_contract(root: Path) -> bool:
    """Reject any immutable artifact whose operator policy drifted from 90d/$15K."""
    path = root / "files" / "data" / "production-status.json"
    if not path.is_file():
        return False
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
        rules = status.get("policy")
        if not isinstance(rules, dict):
            # Compatibility only for old test/artifact shapes; still exact-match.
            rules = status.get("cohort_rules")
        if not isinstance(rules, dict):
            return False
        age = int(rules.get("minimum_verified_market_age_days"))
        liquidity = float(rules.get("minimum_liquidity_usd"))
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return age == PRODUCTION_MIN_MARKET_AGE_DAYS and liquidity == PRODUCTION_MIN_EXECUTION_LIQUIDITY_USD


def verified_decision_snapshot(parent: str) -> dict | None:
    """Return proof only when every bound decision file on parent matches its hash.

    This is deliberately fail-closed. A malformed/missing proof, missing file,
    single digest mismatch, or bound REAL ALERT feed that does not independently
    satisfy the exact production truth contract means the verified publisher must
    not preserve the newer decision generation as trusted canonical state.
    """
    raw = _parent_bytes(parent, DECISION_PROOF)
    if raw is None:
        return None
    try:
        proof = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if proof.get("status") != "VERIFIED_COHERENT_DECISION_SNAPSHOT":
        return None
    if proof.get("decision_validation") != "PASS":
        return None
    if proof.get("exact_pair_required") is not True:
        return None
    if int(proof.get("minimum_market_age_days") or 0) != PRODUCTION_MIN_MARKET_AGE_DAYS:
        return None
    if float(proof.get("minimum_liquidity_usd") or 0) != PRODUCTION_MIN_EXECUTION_LIQUIDITY_USD:
        return None
    hashes = proof.get("hashes")
    if not isinstance(hashes, dict):
        return None
    bodies: dict[str, bytes] = {}
    for key, rel in DECISION_HASH_PATHS.items():
        expected = str(hashes.get(key) or "")
        body = _parent_bytes(parent, rel)
        if not expected or body is None:
            return None
        if hashlib.sha256(body).hexdigest() != expected:
            return None
        bodies[key] = body
    if not _bound_real_alerts_passes_production_contract(bodies["real_alerts"]):
        return None
    return proof


def _proof_blob(
    *,
    source_run: int,
    source_sha: str,
    manifest_bytes: bytes,
    snapshot_real_digest: str,
    effective_real_digest: str,
    preserved_decision: dict | None,
) -> tuple[str, dict]:
    generation_id = f"live-scan:{source_run}:{source_sha}"
    preserving = preserved_decision is not None
    proof = {
        "version": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "VERIFIED_PUBLISHED_SNAPSHOT",
        "run_id": source_run,
        "source_run_id": source_run,
        "source_sha": source_sha,
        "generation_id": generation_id,
        "strict_validation": "PASS",
        "scope": "data/",
        "real_alerts_sha256": effective_real_digest,
        "snapshot_real_alerts_sha256": snapshot_real_digest,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "canonical_decision_preserved": preserving,
        "decision_snapshot_generation_id": (
            preserved_decision.get("generation_id") if preserving else None
        ),
        "decision_snapshot_hashes_verified": preserving,
        "proof_rule": (
            "ATOMIC_LIVE_SNAPSHOT_WITH_HASH_VERIFIED_COHERENT_DECISION_PRESERVATION"
            if preserving
            else "ATOMIC_WITH_VERIFIED_SNAPSHOT_AND_BOUND_TO_REAL_ALERTS_SHA256"
        ),
    }
    text = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    blob = git("hash-object", "-w", "--stdin", input_text=text).stdout.strip()
    return blob, proof


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
    snapshot_real_digest = str(real_item["sha256"])

    blobs: dict[str, str] = {}
    for item in items:
        if item["kind"] != "file" or item["path"] == watermark:
            continue
        rel = item["path"]
        blobs[rel] = git("hash-object", "-w", str(root / "files" / rel)).stdout.strip()

    print(f"VERIFIED_SNAPSHOT_VALID paths={len(items)} real_alerts_sha256={snapshot_real_digest}")

    for attempt in range(1, max(1, args.attempts) + 1):
        git("fetch", "origin", "main")
        parent = git("rev-parse", "origin/main").stdout.strip()
        current = published_run(parent, watermark)
        if current >= source_run:
            print(f"VERIFIED_SNAPSHOT_STALE source_run={source_run} published_run={current}")
            return 0

        decision = verified_decision_snapshot(parent)
        decision_changed = any(
            changed_since(source_sha, parent, rel)
            for rel in DECISION_OWNED_LIVE_PATHS
            if any(item.get("path") == rel for item in items)
        )
        preserve_decision = decision if decision_changed and decision is not None else None

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
                    continue
                if preserve_decision is not None and rel in DECISION_OWNED_LIVE_PATHS:
                    skipped.append(rel)
                    continue
                if changed_since(source_sha, parent, rel):
                    skipped.append(rel)
                    continue
                if item["kind"] == "file":
                    git("update-index", "--add", "--cacheinfo", f"100644,{blobs[rel]},{rel}", env=env)
                else:
                    git("update-index", "--force-remove", "--", rel, env=env, check=False)
                applied.append(rel)

            if real_path in skipped and preserve_decision is None:
                print(
                    f"VERIFIED_SNAPSHOT_SUPERSEDED source_run={source_run} "
                    "reason=REAL_ALERTS_NEWER_WITHOUT_VALID_COHERENT_DECISION_PROOF"
                )
                return 0

            effective_real_digest = snapshot_real_digest
            if preserve_decision is not None:
                effective_real_digest = str((preserve_decision.get("hashes") or {}).get("real_alerts") or "")
                if not effective_real_digest:
                    raise RuntimeError("Verified decision proof missing real_alerts digest")

            proof_blob, proof = _proof_blob(
                source_run=source_run,
                source_sha=source_sha,
                manifest_bytes=manifest_bytes,
                snapshot_real_digest=snapshot_real_digest,
                effective_real_digest=effective_real_digest,
                preserved_decision=preserve_decision,
            )
            git("update-index", "--add", "--cacheinfo", f"100644,{proof_blob},{watermark}", env=env)
            applied.append(watermark)
            tree = git("write-tree", env=env).stdout.strip()
        finally:
            index_path.unlink(missing_ok=True)

        if skipped:
            print("VERIFIED_SNAPSHOT_PRESERVED_NEWER " + ",".join(skipped[:40]))
        if preserve_decision is not None:
            print(
                "VERIFIED_DECISION_SNAPSHOT_PRESERVED "
                f"generation={proof.get('decision_snapshot_generation_id')} "
                f"real_alerts_sha256={proof.get('real_alerts_sha256')}"
            )
        parent_tree = git("rev-parse", f"{parent}^{{tree}}").stdout.strip()
        if tree == parent_tree:
            print("VERIFIED_SNAPSHOT_NO_SAFE_CHANGE")
            return 0

        commit = git(
            "commit-tree", tree, "-p", parent,
            input_text=f"data: publish verified live scan {source_run}\n",
        ).stdout.strip()
        pushed = git("push", "origin", f"{commit}:refs/heads/main", check=False)
        if pushed.returncode == 0:
            print(
                f"VERIFIED_PUBLISH_PROOF_OK generation=live-scan:{source_run}:{source_sha} "
                f"applied={len(applied)} preserved={len(skipped)}"
            )
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
