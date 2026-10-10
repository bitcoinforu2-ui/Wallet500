"""Keep current Gate movers visible before slow unified-watch completion."""
from pathlib import Path


def test_research_discovery_checkpoint_precedes_long_unified_scan():
    flow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "unified-watch-engine.yml").read_text()
    start = flow.index("- name: Checkpoint fresh Gate discovery before long-running verification")
    assert flow.index("- name: Bridge final BUY and Gate movers into dynamic decision candidates") < start
    assert start < flow.index("- name: Collect configured plus final-BUY free intelligence")
    checkpoint = flow[start:flow.index("# CEX decision data is built", start)]
    for path in ("spot-market-discovery.json", "spot-market-discovery-state.json",
                 "futures-market-discovery.json", "futures-market-discovery-state.json"):
        assert path in checkpoint
    assert "--github-api-cas --attempts 3" in checkpoint
    assert "continue-on-error: true" in checkpoint
    assert "real-alerts.json" not in checkpoint.lower()
    assert "telegram" not in checkpoint.lower().replace("telegram messages", "")

