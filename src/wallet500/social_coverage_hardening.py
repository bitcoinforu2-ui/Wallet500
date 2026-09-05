from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data")
INPUT = DATA / "social-intelligence-v2.json"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def harden(payload: dict) -> dict:
    tokens = payload.get("tokens") if isinstance(payload.get("tokens"), list) else []
    observed = {"social": 0, "kol": 0, "news": 0, "manipulation": 0}
    for row in tokens:
        if not isinstance(row, dict):
            continue
        coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        social_ok = coverage.get("organic_social_available") is True
        kol_ok = int(coverage.get("exact_social_events") or 0) > 0
        news_ok = int(coverage.get("news_events") or 0) > 0
        manipulation_ok = social_ok or kol_ok
        availability = {
            "social_momentum": social_ok,
            "kol_quality": kol_ok,
            "news_catalyst": news_ok,
            "hype_manipulation_risk": manipulation_ok,
            "narrative": bool(social_ok or kol_ok or news_ok),
            "confidence": True,
        }
        row["availability"] = availability
        row["unknown_is_not_zero"] = True
        if not social_ok:
            scores["social_momentum"] = None
        else:
            observed["social"] += 1
        if not kol_ok:
            scores["kol_quality"] = None
        else:
            observed["kol"] += 1
        if not news_ok:
            scores["news_catalyst"] = None
        else:
            observed["news"] += 1
        if not manipulation_ok:
            scores["hype_manipulation_risk"] = None
        else:
            observed["manipulation"] += 1
        row["scores"] = scores

    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    counts.update({
        "social_momentum_observed": observed["social"],
        "kol_quality_observed": observed["kol"],
        "news_catalyst_observed": observed["news"],
        "manipulation_risk_observed": observed["manipulation"],
        "unknown_channels_render_as_null": True,
    })
    payload["counts"] = counts
    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth["missing_channel_is_unknown_not_zero"] = True
    payload["truth_contract"] = truth
    return payload


def run(path: str | Path = INPUT) -> dict:
    p = Path(path)
    payload = harden(_load(p, {}))
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload.get("counts") or {}, ensure_ascii=False))


if __name__ == "__main__":
    main()
