from pathlib import Path


def test_hot_recheck_publish_uses_latest_main_as_cas_base():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "unified-watch-engine.yml"
    ).read_text(encoding="utf-8")

    marker = "- name: Persist hot-candidate confirmation state immediately"
    assert marker in workflow
    block = workflow.split(marker, 1)[1].split("\n      - name:", 1)[0]

    assert "git fetch --no-tags --depth=1 origin main" in block
    assert 'HOT_RECHECK_BASE_SHA="$(git rev-parse origin/main)"' in block
    assert '--base "$HOT_RECHECK_BASE_SHA"' in block
    assert "data/user-watch-final-buy-report.json" in block
