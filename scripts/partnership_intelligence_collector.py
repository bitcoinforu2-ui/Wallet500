"""Entry point invoked after enrichment INSIDE the unified watch workflow."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wallet500.partnership_intelligence import run

if __name__ == "__main__":
    print("PARTNERSHIP_RESEARCH", json.dumps(run(), ensure_ascii=False))
