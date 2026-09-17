from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "unified-watch-engine.yml"


def test_unified_diagnostics_and_verified_state_have_separate_publication_contracts():
    text = WORKFLOW.read_text(encoding="utf-8")

    diagnostic = text.split("- name: Persist runtime diagnostics independently", 1)[1]
    verified = text.split("- name: Persist verified forward-only business state atomically", 1)[1]

    assert "if: always()" in diagnostic.split("- name: Persist verified", 1)[0]
    assert "continue-on-error: true" in diagnostic.split("- name: Persist verified", 1)[0]
    assert "data/unified-watch-runtime-evidence.json" in diagnostic.split("- name: Persist verified", 1)[0]

    assert "if: success()" in verified
    assert "--fail-on-newer" in verified
    assert "scripts/atomic_publish.py" in verified
    assert "data/unified-watch-runtime-evidence.json" not in verified


def test_unified_workflow_does_not_raw_reset_or_push_verified_state():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "git reset --hard origin/main" not in text
    assert "git push origin HEAD:main" not in text
    assert "--github-api-cas" in text
