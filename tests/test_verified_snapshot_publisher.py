from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_verified_snapshot.py"
spec = importlib.util.spec_from_file_location("publish_verified_snapshot", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _decision_fixture():
    bodies = {
        rel: json.dumps({"path": rel, "v": 1}, sort_keys=True).encode()
        for rel in mod.DECISION_HASH_PATHS.values()
    }
    bodies[mod.DECISION_HASH_PATHS["real_alerts"]] = json.dumps(
        {
            "version": 3,
            "truth_contract": {
                "minimum_market_age_days": 180,
                "minimum_execution_pool_liquidity_usd": 50000.0,
                "exact_onchain_identity_required": True,
                "exact_dex_pair_required": True,
                "symbol_only_never_actionable": True,
                "cex_only_never_real_alert": True,
            },
        },
        sort_keys=True,
    ).encode()
    hashes = {
        key: hashlib.sha256(bodies[rel]).hexdigest()
        for key, rel in mod.DECISION_HASH_PATHS.items()
    }
    proof = {
        "status": "VERIFIED_COHERENT_DECISION_SNAPSHOT",
        "decision_validation": "PASS",
        "exact_pair_required": True,
        "minimum_market_age_days": 180,
        "minimum_liquidity_usd": 50000,
        "generation_id": "candidate-evidence:123:abc",
        "hashes": hashes,
    }
    return proof, bodies


def test_verified_decision_snapshot_accepts_only_fully_bound_generation(monkeypatch):
    proof, bodies = _decision_fixture()

    def parent_bytes(parent, rel):
        if rel == mod.DECISION_PROOF:
            return json.dumps(proof).encode()
        return bodies.get(rel)

    monkeypatch.setattr(mod, "_parent_bytes", parent_bytes)
    out = mod.verified_decision_snapshot("parent")
    assert out is not None
    assert out["generation_id"] == proof["generation_id"]


def test_verified_decision_snapshot_fails_closed_on_one_digest_mismatch(monkeypatch):
    proof, bodies = _decision_fixture()
    broken = dict(bodies)
    broken[mod.DECISION_HASH_PATHS["real_alerts"]] = b"tampered"

    def parent_bytes(parent, rel):
        if rel == mod.DECISION_PROOF:
            return json.dumps(proof).encode()
        return broken.get(rel)

    monkeypatch.setattr(mod, "_parent_bytes", parent_bytes)
    assert mod.verified_decision_snapshot("parent") is None


def _replace_real_alert_contract(proof, bodies, *, age, liquidity):
    changed = dict(bodies)
    body = json.dumps(
        {
            "version": 3,
            "truth_contract": {
                "minimum_market_age_days": age,
                "minimum_execution_pool_liquidity_usd": liquidity,
                "exact_onchain_identity_required": True,
                "exact_dex_pair_required": True,
                "symbol_only_never_actionable": True,
                "cex_only_never_real_alert": True,
            },
        },
        sort_keys=True,
    ).encode()
    changed[mod.DECISION_HASH_PATHS["real_alerts"]] = body
    proof = dict(proof)
    proof["hashes"] = dict(proof["hashes"])
    proof["hashes"]["real_alerts"] = hashlib.sha256(body).hexdigest()
    return proof, changed


def test_verified_decision_snapshot_fails_closed_on_subthreshold_real_alert_contract(monkeypatch):
    proof, bodies = _decision_fixture()
    proof, changed = _replace_real_alert_contract(proof, bodies, age=179, liquidity=49999.0)

    def parent_bytes(parent, rel):
        if rel == mod.DECISION_PROOF:
            return json.dumps(proof).encode()
        return changed.get(rel)

    monkeypatch.setattr(mod, "_parent_bytes", parent_bytes)
    assert mod.verified_decision_snapshot("parent") is None


def test_verified_decision_snapshot_rejects_legacy_policy_drift(monkeypatch):
    proof, bodies = _decision_fixture()
    proof, changed = _replace_real_alert_contract(proof, bodies, age=90, liquidity=15000.0)

    def parent_bytes(parent, rel):
        if rel == mod.DECISION_PROOF:
            return json.dumps(proof).encode()
        return changed.get(rel)

    monkeypatch.setattr(mod, "_parent_bytes", parent_bytes)
    assert mod.verified_decision_snapshot("parent") is None


def test_verified_decision_snapshot_fails_closed_when_exact_identity_contract_missing(monkeypatch):
    proof, bodies = _decision_fixture()
    bad = dict(bodies)
    feed = json.loads(bad[mod.DECISION_HASH_PATHS["real_alerts"]].decode())
    feed["truth_contract"]["exact_onchain_identity_required"] = False
    bad_body = json.dumps(feed, sort_keys=True).encode()
    bad[mod.DECISION_HASH_PATHS["real_alerts"]] = bad_body
    proof = dict(proof)
    proof["hashes"] = dict(proof["hashes"])
    proof["hashes"]["real_alerts"] = hashlib.sha256(bad_body).hexdigest()

    def parent_bytes(parent, rel):
        if rel == mod.DECISION_PROOF:
            return json.dumps(proof).encode()
        return bad.get(rel)

    monkeypatch.setattr(mod, "_parent_bytes", parent_bytes)
    assert mod.verified_decision_snapshot("parent") is None


def test_publish_proof_binds_effective_and_snapshot_real_alert_digests(monkeypatch):
    proof, _ = _decision_fixture()

    class Result:
        stdout = "blobsha\n"

    monkeypatch.setattr(mod, "git", lambda *a, **k: Result())
    _, published = mod._proof_blob(
        source_run=456,
        source_sha="a" * 40,
        manifest_bytes=b"manifest",
        snapshot_real_digest="snapshot-digest",
        effective_real_digest="effective-digest",
        preserved_decision=proof,
    )
    assert published["version"] == 3
    assert published["canonical_decision_preserved"] is True
    assert published["decision_snapshot_hashes_verified"] is True
    assert published["snapshot_real_alerts_sha256"] == "snapshot-digest"
    assert published["real_alerts_sha256"] == "effective-digest"
    assert published["decision_snapshot_generation_id"] == proof["generation_id"]


def _write_status(tmp_path, age, liquidity, key="policy"):
    path = tmp_path / "files" / "data" / "production-status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                key: {
                    "minimum_verified_market_age_days": age,
                    "minimum_liquidity_usd": liquidity,
                }
            }
        ),
        encoding="utf-8",
    )


def test_snapshot_production_status_accepts_canonical_contract(tmp_path):
    _write_status(tmp_path, 180, 50000.0)
    assert mod._snapshot_production_status_passes_contract(tmp_path) is True


def test_snapshot_production_status_accepts_legacy_shape_only_when_values_are_canonical(tmp_path):
    _write_status(tmp_path, 180, 50000.0, key="cohort_rules")
    assert mod._snapshot_production_status_passes_contract(tmp_path) is True


def test_snapshot_production_status_fails_closed_on_subthreshold_contract(tmp_path):
    _write_status(tmp_path, 179, 49999.0)
    assert mod._snapshot_production_status_passes_contract(tmp_path) is False


def test_snapshot_production_status_rejects_legacy_policy_drift(tmp_path):
    _write_status(tmp_path, 90, 15000.0)
    assert mod._snapshot_production_status_passes_contract(tmp_path) is False
