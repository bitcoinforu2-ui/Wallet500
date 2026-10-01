"""Entry point invoked after enrichment INSIDE the unified watch workflow."""
from wallet500.partnership_intelligence import run

if __name__ == "__main__":
    import json
    print("PARTNERSHIP_RESEARCH", json.dumps(run(), ensure_ascii=False))
