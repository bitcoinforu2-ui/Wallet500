import json
from dataclasses import asdict
from pathlib import Path


class Watchlist:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save_events(self, events, threshold: float = 60.0) -> list[dict]:
        current = {item["token"]: item for item in self.load()}
        for event in events:
            if event.score < threshold:
                continue
            item = asdict(event)
            item["observed_at"] = event.observed_at.isoformat()
            current[event.token] = item
        rows = sorted(current.values(), key=lambda x: x.get("score", 0), reverse=True)
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        return rows
