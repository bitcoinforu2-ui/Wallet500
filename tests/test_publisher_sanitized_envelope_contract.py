"""Regression for the exact October 2026 sanitized-envelope generation mismatch."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verified-publisher.yml"


def test_publisher_does_not_undo_solana_sanitization_before_generation():
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split("- name: Publish coherent generation and input-health manifest", 1)[1]
    block = block.split("- name: Dispatch dashboard from published main", 1)[0]
    assert "python -m wallet500.decision_snapshot_guard" in block
    # Initial git restore takes canonical source from main; the *later*
    # git show loop must not overwrite sanitized candidate evidence.
    committed_restore = block.split("for rel in \\\n", 1)[1].split('git show "HEAD:$rel" > "$rel"', 1)[0]
    assert "data/candidate-evidence-envelope.json" not in committed_restore
    local_hashes = block.split("locally_generated = {", 1)[1].split("}", 1)[0]
    assert "'data/candidate-evidence-envelope.json'" in local_hashes


def test_sanitized_envelope_and_generation_are_committed_atomically():
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split("python scripts/atomic_publish.py \\", 1)[1]
    block = block.split("rc=$?", 1)[0]
    assert "data/candidate-evidence-envelope.json" in block
    assert "data/real-alerts.json" in block
    assert "data/decision-generation.json" in block


def test_pipeline_audit_tracks_mutated_envelope_as_regenerated_canonical():
    from scripts.pipeline_integrity_audit import audit

    report = audit()
    assert not any(
        x["code"] == "REGENERATED_CANONICAL_NOT_ATOMICALLY_PUBLISHED"
        for x in report["findings"]
    ), report["findings"]
