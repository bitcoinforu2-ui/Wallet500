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


def _research_envelope(age=90, liquidity=15000.0):
    return {
        "mode": "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1",
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {
            "minimum_market_age_days": age,
            "minimum_execution_liquidity_usd": liquidity,
            "exact_pair_required": True,
        },
    }


def _strict_real_alert(age=180, liquidity=50000.0):
    return {
        "version": 3,
        "truth_contract": {
            "minimum_market_age_days": age,
            "minimum_execution_pool_liquidity_usd": liquidity,
            "exact_onchain_identity_required": True,
            "exact_dex_pair_required": True,
            "symbol_only_never_actionable": True,
            "cex_only_never_real_alert": True,
        },
    }


def _strict_production_status(age=180, liquidity=50000.0):
    return {
        "policy": {
            "minimum_verified_market_age_days": age,
            "minimum_liquidity_usd": liquidity,
        }
    }


def _decision_fixture(*, producer="CANDIDATE_EVIDENCE_ENVELOPE", partial=False):
    bodies = {
        rel: json.dumps({"path": rel, "v": 1}, sort_keys=True).encode()
        for rel in mod.DECISION_HASH_PATHS.values()
    }
    bodies[mod.DECISION_HASH_PATHS["candidate_evidence"]] = json.dumps(
        _research_envelope(), sort_keys=True
    ).encode()
    bodies[mod.DECISION_HASH_PATHS["real_alerts"]] = json.dumps(
        _strict_real_alert(), sort_keys=True
    ).encode()
    bodies[mod.DECISION_HASH_PATHS["production_status"]] = json.dumps(
        _strict_production_status(), sort_keys=True
    ).encode()

    keys = set(mod.REQUIRED_DECISION_HASH_KEYS) if partial else set(mod.DECISION_HASH_PATHS)
    hashes = {
        key: hashlib.sha256(bodies[mod.DECISION_HASH_PATHS[key]]).hexdigest()
        for key in keys
    }
    prefix = mod.DECISION_PRODUCER_PREFIX[producer]
    source_sha = "a" * 40
    proof = {
        "status": "VERIFIED_COHERENT_DECISION_SNAPSHOT",
        "decision_validation": "PASS",
        "producer": producer,
        "workflow_run_id": "123",
        "source_sha": source_sha,
        "generation_id": f"{prefix}:123:{source_sha}",
        "exact_pair_required": True,
        "minimum_market_age_days": 90,
        "hashes": hashes,
    }
    if producer == "CANDIDATE_EVIDENCE_ENVELOPE":
        proof["minimum_liquidity_usd"] = 15000
        proof["policy_scopes"] = {
            "research_evidence": {
                "minimum_market_age_days": 90,
                "minimum_execution_liquidity_usd": 15000,
            },
            "production_real_alert": {
                "minimum_market_age_days": 180,
                "minimum_execution_liquidity_usd": 50000,
            },
        }
    return proof, bodies


def _parent_reader(proof, bodies):
    def parent_bytes(parent, rel):
        if rel == mod.DECISION_PROOF:
            return json.dumps(proof).encode()
        return bodies.get(rel)
    return parent_bytes


def test_verified_decision_snapshot_accepts_fully_bound_unified_policy_generation(monkeypatch):
    proof, bodies = _decision_fixture()
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, bodies))
    out = mod.verified_decision_snapshot("parent")
    assert out is not None
    assert out["generation_id"] == proof["generation_id"]
    assert mod.DECISION_HASH_PATHS["real_alerts"] in out["_verified_paths"]


def test_verified_decision_snapshot_accepts_pending_confirmation_partial_proof(monkeypatch):
    proof, bodies = _decision_fixture(producer="PENDING_CONFIRMATION_REFRESH", partial=True)
    assert "minimum_liquidity_usd" not in proof
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, bodies))
    out = mod.verified_decision_snapshot("parent")
    assert out is not None
    assert set(out["_verified_paths"]) == {
        mod.DECISION_HASH_PATHS[key] for key in mod.REQUIRED_DECISION_HASH_KEYS
    }


def test_verified_decision_snapshot_fails_closed_on_one_digest_mismatch(monkeypatch):
    proof, bodies = _decision_fixture()
    broken = dict(bodies)
    broken[mod.DECISION_HASH_PATHS["real_alerts"]] = b"tampered"
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, broken))
    assert mod.verified_decision_snapshot("parent") is None


def _replace_real_alert_contract(proof, bodies, *, age, liquidity):
    changed = dict(bodies)
    body = json.dumps(_strict_real_alert(age, liquidity), sort_keys=True).encode()
    changed[mod.DECISION_HASH_PATHS["real_alerts"]] = body
    proof = dict(proof)
    proof["hashes"] = dict(proof["hashes"])
    proof["hashes"]["real_alerts"] = hashlib.sha256(body).hexdigest()
    return proof, changed


def test_verified_decision_snapshot_fails_closed_on_subthreshold_real_alert_contract(monkeypatch):
    proof, bodies = _decision_fixture()
    proof, changed = _replace_real_alert_contract(proof, bodies, age=179, liquidity=49999.0)
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, changed))
    assert mod.verified_decision_snapshot("parent") is None


def test_verified_decision_snapshot_rejects_legacy_90d_15k_real_alert_policy(monkeypatch):
    proof, bodies = _decision_fixture()
    proof, changed = _replace_real_alert_contract(proof, bodies, age=90, liquidity=15000.0)
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, changed))
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
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, bad))
    assert mod.verified_decision_snapshot("parent") is None


def test_verified_decision_snapshot_rejects_wrong_research_age(monkeypatch):
    proof, bodies = _decision_fixture()
    proof = dict(proof)
    proof["minimum_market_age_days"] = 89
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, bodies))
    assert mod.verified_decision_snapshot("parent") is None


def test_verified_decision_snapshot_rejects_research_envelope_liquidity_drift(monkeypatch):
    proof, bodies = _decision_fixture()
    changed = dict(bodies)
    body = json.dumps(_research_envelope(90, 14999.0), sort_keys=True).encode()
    changed[mod.DECISION_HASH_PATHS["candidate_evidence"]] = body
    proof = dict(proof)
    proof["hashes"] = dict(proof["hashes"])
    proof["hashes"]["candidate_evidence"] = hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, changed))
    assert mod.verified_decision_snapshot("parent") is None


def test_pending_proof_still_requires_current_canonical_production_status(monkeypatch):
    proof, bodies = _decision_fixture(producer="PENDING_CONFIRMATION_REFRESH", partial=True)
    changed = dict(bodies)
    changed[mod.DECISION_HASH_PATHS["production_status"]] = json.dumps(
        _strict_production_status(90, 15000.0), sort_keys=True
    ).encode()
    monkeypatch.setattr(mod, "_parent_bytes", _parent_reader(proof, changed))
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


def test_snapshot_production_status_rejects_legacy_90d_15k_policy(tmp_path):
    _write_status(tmp_path, 90, 15000.0)
    assert mod._snapshot_production_status_passes_contract(tmp_path) is False


def _bound_generation(monkeypatch, run=123):
    bodies = {p: json.dumps({"path": p}).encode() for p in mod.CANONICAL_FILES}
    bodies["data/real-alerts.json"] = json.dumps(_strict_real_alert()).encode()
    bodies["data/production-status.json"] = json.dumps(_strict_production_status()).encode()
    sha = "a" * 40
    generation = {
        "version": 3, "status": "COHERENT_READY", "automatic_buy": False,
        "workflow_run_id": str(run), "source_sha": sha,
        "generation_id": f"wallet500:{run}:{sha}",
        "hashes": {p: hashlib.sha256(b).hexdigest() for p, b in bodies.items()},
    }
    def reader(parent, path):
        return json.dumps(generation).encode() if path == "data/decision-generation.json" else bodies.get(path)
    monkeypatch.setattr(mod, "_parent_bytes", reader)
    return generation, bodies


def test_new_scan_can_replace_older_hash_bound_post_publish_guard(monkeypatch):
    _bound_generation(monkeypatch)
    paths = mod.previous_generation_paths("main", 124)
    assert paths == set(mod.CANONICAL_FILES)
    assert "data/real-alerts.json" in paths


def test_independently_changed_real_alerts_still_block_overwrite(monkeypatch):
    _, bodies = _bound_generation(monkeypatch)
    bodies["data/real-alerts.json"] += b"\n"
    assert mod.previous_generation_paths("main", 124) == set()


def test_unbound_non_decision_state_never_gets_conflict_override(monkeypatch):
    _, bodies = _bound_generation(monkeypatch)
    bodies["data/unified-watch-state.json"] = b"{}"
    assert "data/unified-watch-state.json" not in mod.previous_generation_paths("main", 124)


def test_changed_canonical_file_does_not_inherit_its_old_hash_proof(monkeypatch):
    _, bodies = _bound_generation(monkeypatch)
    bodies["data/system-health.json"] += b"\n"
    paths = mod.previous_generation_paths("main", 124)
    assert "data/system-health.json" not in paths
    assert "data/real-alerts.json" in paths


def test_equal_or_newer_generation_never_gets_overwritten(monkeypatch):
    _bound_generation(monkeypatch, run=124)
    assert mod.previous_generation_paths("main", 124) == set()
    assert mod.previous_generation_paths("main", 123) == set()


def test_complete_hashes_do_not_authorize_weak_production_policy(monkeypatch):
    generation, bodies = _bound_generation(monkeypatch)
    path = "data/production-status.json"
    bodies[path] = json.dumps(_strict_production_status(90, 15000)).encode()
    generation["hashes"][path] = hashlib.sha256(bodies[path]).hexdigest()
    assert mod.previous_generation_paths("main", 124) == set()


def test_missing_canonical_hash_fails_closed(monkeypatch):
    generation, _ = _bound_generation(monkeypatch)
    generation["hashes"].pop("data/system-health.json")
    assert mod.previous_generation_paths("main", 124) == set()


def test_workflow_cannot_rebind_source_if_snapshot_was_not_published():
    workflow = Path(".github/workflows/verified-publisher.yml").read_text()
    assert 'if [ "$published_run" -lt "$LIVE_SOURCE_RUN" ]' in workflow
    assert "SOURCE_SNAPSHOT_NOT_PUBLISHED" in workflow
    assert workflow.index("SOURCE_SNAPSHOT_NOT_PUBLISHED") < workflow.index("python -m wallet500.decision_generation")
