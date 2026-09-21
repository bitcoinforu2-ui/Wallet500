from pathlib import Path


PRODUCTION_WORKFLOWS = [
    Path(".github/workflows/live-scan.yml"),
    Path(".github/workflows/unified-watch-engine.yml"),
    Path(".github/workflows/verified-publisher.yml"),
]


def test_production_workflows_are_not_push_triggered():
    for path in PRODUCTION_WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "  workflow_dispatch:" in text, path
        assert "  schedule:" in text or "  workflow_run:" in text, path
        assert "  push:\n" not in text, path


def test_production_concurrency_never_cancels_running_work():
    for path in PRODUCTION_WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "concurrency:" in text, path
        assert "cancel-in-progress: false" in text, path
