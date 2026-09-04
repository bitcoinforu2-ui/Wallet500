from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
LEDGER = DATA / "veteran-dna-forward-ledger.json"
OUT = DATA / "veteran-dna-shadow-eval.json"
MODE = "VETERAN_DNA_SHADOW_EVAL_V1"

TARGET_HOURS = {"1h": 1.0, "3h": 3.0, "6h": 6.0, "24h": 24.0}
MAX_LAG_HOURS = {"1h": 1.25, "3h": 1.5, "6h": 2.0, "24h": 2.0}
TURNOVER_GRID = (0.10, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50)
BUY_RATIO_GRID = (1.10, 1.25, 1.40, 1.50)
ANTI_CHASE_H1_MAX = (None, 10.0, 20.0)
MIN_SAMPLE_WINNERS = 20
MIN_SAMPLE_CONTROLS = 20


def load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def n(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def split_bucket(key: str) -> str:
    value = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 10
    return "TRAIN" if value < 7 else "HOLDOUT"


def timing_valid(cp: dict | None, horizon: str) -> bool:
    if not isinstance(cp, dict):
        return False
    age = n(cp.get("observed_age_hours"))
    target = TARGET_HOURS[horizon]
    if age is None or age < target:
        return False
    return age <= target + MAX_LAG_HOURS[horizon]


def checkpoint_audit(records: dict) -> dict:
    now = datetime.now(timezone.utc)
    result = {}
    for horizon, target in TARGET_HOURS.items():
        matured = 0
        present = 0
        valid = 0
        late = 0
        missing = 0
        for rec in records.values():
            t0 = parse_ts(rec.get("t0_at"))
            if not t0:
                continue
            age_h = (now - t0).total_seconds() / 3600.0
            if age_h < target:
                continue
            matured += 1
            cp = (rec.get("checkpoints") or {}).get(horizon)
            if isinstance(cp, dict):
                present += 1
                if timing_valid(cp, horizon):
                    valid += 1
                else:
                    late += 1
            else:
                missing += 1
        result[horizon] = {
            "matured_expected": matured,
            "checkpoint_present": present,
            "timing_valid": valid,
            "late": late,
            "missing": missing,
            "valid_coverage_pct": round(100.0 * valid / matured, 2) if matured else None,
            "target_hours": target,
            "max_lag_hours": MAX_LAG_HOURS[horizon],
        }
    return result


def labeled_rows(records: dict, split: str | None = None) -> list[dict]:
    out = []
    for key, rec in records.items():
        label = rec.get("label_24h")
        if label not in {"WINNER", "CONTROL"}:
            continue
        if split and split_bucket(key) != split:
            continue
        cp = (rec.get("checkpoints") or {}).get("24h")
        if not timing_valid(cp, "24h"):
            continue
        out.append({"key": key, "record": rec, "label": label, "return_24h": n(cp.get("return_pct"))})
    return out


def fires(rec: dict, turnover_min: float, buy_min: float, anti_chase_max: float | None) -> bool:
    feat = rec.get("t0_features") or {}
    turnover = n(feat.get("turnover_h1"))
    buy_ratio = n(feat.get("buy_sell_ratio_h1"))
    liq = n(feat.get("liquidity_usd"), 0.0) or 0.0
    h1 = n(feat.get("price_change_h1_pct"))
    if turnover is None or buy_ratio is None or liq < 50_000:
        return False
    if turnover < turnover_min or turnover >= 0.75 or buy_ratio < buy_min:
        return False
    if anti_chase_max is not None and h1 is not None and h1 > anti_chase_max:
        return False
    return True


def median(values):
    clean = [float(x) for x in values if x is not None]
    return round(statistics.median(clean), 6) if clean else None


def evaluate(rows: list[dict], turnover_min: float, buy_min: float, anti_chase_max: float | None) -> dict:
    winners = [x for x in rows if x["label"] == "WINNER"]
    controls = [x for x in rows if x["label"] == "CONTROL"]
    flagged = [x for x in rows if fires(x["record"], turnover_min, buy_min, anti_chase_max)]
    fw = [x for x in flagged if x["label"] == "WINNER"]
    fc = [x for x in flagged if x["label"] == "CONTROL"]
    precision = len(fw) / len(flagged) if flagged else None
    recall = len(fw) / len(winners) if winners else None
    fpr = len(fc) / len(controls) if controls else None
    score = None
    if precision is not None and recall is not None:
        score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "turnover_min": turnover_min,
        "turnover_max_exclusive": 0.75,
        "buy_sell_ratio_min": buy_min,
        "anti_chase_h1_max_pct": anti_chase_max,
        "eligible_labeled_n": len(rows),
        "winner_n": len(winners),
        "control_n": len(controls),
        "flagged_n": len(flagged),
        "flagged_winners": len(fw),
        "flagged_controls": len(fc),
        "precision_pct": round(100 * precision, 2) if precision is not None else None,
        "recall_pct": round(100 * recall, 2) if recall is not None else None,
        "false_positive_rate_pct": round(100 * fpr, 2) if fpr is not None else None,
        "f1": round(score, 6) if score is not None else None,
        "median_flagged_return_24h_pct": median([x["return_24h"] for x in flagged]),
    }


def choose_train_candidate(train_rows: list[dict]) -> tuple[dict | None, list[dict]]:
    grid = []
    for turnover in TURNOVER_GRID:
        for buy in BUY_RATIO_GRID:
            for anti in ANTI_CHASE_H1_MAX:
                grid.append(evaluate(train_rows, turnover, buy, anti))
    def rank(row):
        adequate = 1 if row.get("flagged_n", 0) >= 3 else 0
        return (
            adequate,
            row.get("f1") if row.get("f1") is not None else -1,
            row.get("precision_pct") if row.get("precision_pct") is not None else -1,
            row.get("flagged_n", 0),
            -row.get("turnover_min", 0),
        )
    grid.sort(key=rank, reverse=True)
    return (grid[0] if grid else None), grid[:15]


def eval_same_rule(rows: list[dict], rule: dict | None) -> dict | None:
    if not rule:
        return None
    return evaluate(rows, rule["turnover_min"], rule["buy_sell_ratio_min"], rule.get("anti_chase_h1_max_pct"))


def feature_medians(rows: list[dict], label: str) -> dict:
    selected = [x["record"] for x in rows if x["label"] == label]
    fields = ("liquidity_usd", "volume_h1_usd", "turnover_h1", "buy_sell_ratio_h1", "buys_h1", "sells_h1", "price_change_h1_pct", "price_change_h6_pct")
    out = {}
    for field in fields:
        out[field] = median([(r.get("t0_features") or {}).get(field) for r in selected])
    return out


def main() -> None:
    ledger = load(LEDGER, {})
    if ledger.get("mode") != "VETERAN_DNA_FORWARD_NO_HINDSIGHT_V1":
        raise SystemExit("VETERAN_DNA_SHADOW_LEDGER_CONTRACT_INVALID")
    records = ledger.get("records") or {}

    all_rows = labeled_rows(records)
    train_rows = labeled_rows(records, "TRAIN")
    holdout_rows = labeled_rows(records, "HOLDOUT")
    best_train, top_grid = choose_train_candidate(train_rows)
    holdout_eval = eval_same_rule(holdout_rows, best_train)

    winners_all = sum(x["label"] == "WINNER" for x in all_rows)
    controls_all = sum(x["label"] == "CONTROL" for x in all_rows)
    base_ready = winners_all >= MIN_SAMPLE_WINNERS and controls_all >= MIN_SAMPLE_CONTROLS

    payload = {
        "version": 1,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_change": False,
        "automatic_buy": False,
        "threshold_promotion": False,
        "truth_contract": {
            "veteran_only": True,
            "exact_pair_only": True,
            "no_hindsight": True,
            "pre_registered_grid": True,
            "deterministic_train_holdout_split": "SHA256(KEY) MOD 10; 0-6 TRAIN, 7-9 HOLDOUT",
            "late_24h_checkpoints_excluded_from_rule_evaluation": True,
            "ambiguous_24h_labels_excluded_from_binary_precision_recall": True,
            "minimum_winners_for_research_ready": MIN_SAMPLE_WINNERS,
            "minimum_controls_for_research_ready": MIN_SAMPLE_CONTROLS,
            "production_promotion_requires_separate_future_prospective_validation": True,
        },
        "checkpoint_quality": checkpoint_audit(records),
        "labeled_sample": {
            "all_valid_24h": len(all_rows),
            "winners": winners_all,
            "controls": controls_all,
            "train_valid_24h": len(train_rows),
            "holdout_valid_24h": len(holdout_rows),
        },
        "winner_t0_medians": feature_medians(all_rows, "WINNER"),
        "control_t0_medians": feature_medians(all_rows, "CONTROL"),
        "best_train_shadow_rule": best_train,
        "same_rule_holdout_result": holdout_eval,
        "top15_pre_registered_train_grid": top_grid,
        "research_ready_for_separation_analysis": base_ready,
        "promotion_allowed": False,
        "status": "RESEARCH_READY_SHADOW_ONLY" if base_ready else "COLLECTING_PROSPECTIVE_VETERAN_SAMPLE",
        "interpretation": "The grid was fixed before the 24h labels matured. Train chooses a shadow rule; holdout measures it. No result can change production thresholds without a separate future prospective validation phase.",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sample": payload["labeled_sample"], "status": payload["status"], "best": best_train, "holdout": holdout_eval}, indent=2))


if __name__ == "__main__":
    main()
