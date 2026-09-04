from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
SOURCE = DATA / "revival-1000-latest.json"
MIN_VETERAN_DAYS = 180


def _dt(value: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _age_lower_bound_days(row: dict[str, Any], now: datetime) -> float | None:
    # An ATH observation is hard evidence that the asset already existed at that time.
    # This is conservative: recent ATH does not prove a token is young, so such rows
    # remain unverified rather than being guessed old.
    evidence = _dt(row.get("ath_date"))
    if evidence is None or evidence > now:
        return None
    return max(0.0, (now - evidence).total_seconds() / 86400.0)


def _counts(coins: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "universe": len(coins),
        "core_drawdown_watch": sum(
            1 for x in coins if x.get("watch_status") != "OUTSIDE_CORE_DRAWDOWN_BAND"
        ),
        "waking_market_only": sum(
            1 for x in coins if x.get("watch_status") == "WAKING_MARKET_ONLY"
        ),
        "pre_alpha": sum(1 for x in coins if x.get("pre_alpha_eligible") is True),
        "dex_verified_pairs": sum(
            1 for x in coins if x.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
        ),
        "pair_survival_observed": sum(
            1
            for x in coins
            if (x.get("revival_score_components") or {}).get("same_pair_as_previous") is True
        ),
    }


def apply_veteran_filter(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    minimum_days: int = MIN_VETERAN_DAYS,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("REVIVAL_VETERAN_SOURCE_NOT_OBJECT")
    if payload.get("network") != "solana":
        raise ValueError("REVIVAL_VETERAN_NETWORK_MISMATCH")
    rows = payload.get("coins")
    if not isinstance(rows, list):
        raise ValueError("REVIVAL_VETERAN_COINS_NOT_LIST")

    ts = now or datetime.now(timezone.utc)
    accepted: list[dict[str, Any]] = []
    rejected_missing_age = 0
    rejected_too_young_lower_bound = 0

    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        lower_bound = _age_lower_bound_days(row, ts)
        row["veteran_age_evidence_source"] = "COINGECKO_ATH_DATE"
        row["veteran_age_lower_bound_days"] = (
            round(lower_bound, 3) if lower_bound is not None else None
        )
        row["veteran_minimum_market_age_days"] = int(minimum_days)
        row["veteran_verified"] = bool(
            lower_bound is not None and lower_bound >= minimum_days
        )
        if row["veteran_verified"] is not True:
            if lower_bound is None:
                rejected_missing_age += 1
            else:
                # The available ATH evidence is too recent to prove veteran status;
                # this is not a claim that the token itself is young.
                rejected_too_young_lower_bound += 1
            continue
        accepted.append(row)

    out = dict(payload)
    original_count = len(rows)
    out["coins"] = accepted
    out["counts"] = _counts(accepted)
    out["veteran_age_governance"] = {
        "mode": "FAIL_CLOSED_VERIFIED_MARKET_AGE_V1",
        "minimum_market_age_days": int(minimum_days),
        "evidence_source": "COINGECKO_ATH_DATE",
        "interpretation": (
            "ATH date is used only as a lower-bound proof of existence. "
            "A recent or missing ATH date cannot prove youth and is therefore "
            "excluded as age-unverified rather than classified as young."
        ),
        "raw_before_age_filter": original_count,
        "accepted_verified_veterans": len(accepted),
        "excluded_age_unverified": original_count - len(accepted),
        "excluded_missing_age_evidence": rejected_missing_age,
        "excluded_recent_ath_insufficient_to_prove_age": rejected_too_young_lower_bound,
        "missing_age_never_imputed_as_old": True,
        "production_portfolio_impact": "NONE",
    }
    out["universe_definition"] = (
        str(out.get("universe_definition") or "")
        + f"; VERIFIED VETERAN LOWER-BOUND AGE >= {int(minimum_days)} DAYS REQUIRED"
    )
    out["production_portfolio_impact"] = "NONE"
    return out


def run(data_dir: Path = DATA) -> dict[str, Any]:
    source = data_dir / SOURCE.name
    if not source.exists():
        raise SystemExit("REVIVAL_VETERAN_SOURCE_MISSING")
    payload = json.loads(source.read_text(encoding="utf-8"))
    filtered = apply_veteran_filter(payload)
    source.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return filtered


def main() -> None:
    out = run()
    print(
        json.dumps(
            {
                "mode": out.get("mode"),
                "network": out.get("network"),
                "counts": out.get("counts"),
                "veteran_age_governance": out.get("veteran_age_governance"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
