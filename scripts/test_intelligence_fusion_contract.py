from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import intelligence_fusion as fusion

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "data/close-watch-intelligence-policy.json").read_text())
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def event(target, family="market_microstructure", kind="volume_acceleration", direction=1, strength=90, confidence=90, at=None, **extra):
    row = {
        "symbol": target["symbol"],
        "network": target["network"],
        "contract": target["contract"],
        "pair": target["pair"],
        "family": family,
        "kind": kind,
        "direction": direction,
        "strength": strength,
        "confidence": confidence,
        "source": "contract-test",
        "canonical_event_id": f"{kind}:{target['pair']}",
        "event_time": (at or NOW).isoformat(),
        "observed_at": (at or NOW).isoformat(),
    }
    row.update(extra)
    return row


def main():
    target = {"symbol": "ARB", "network": "arbitrum", "contract": "0xAa00000000000000000000000000000000000001", "pair": "0xBb00000000000000000000000000000000000002"}

    good = event(target)
    row = fusion.fuse(target, [good], POLICY, now_dt=NOW)
    assert row["current_evidence_count"] == 1
    assert row["identity_mode"] if "identity_mode" in row else True
    assert row["status"] == "CURRENT"

    wrong_pair_target = dict(target, pair="0xCc00000000000000000000000000000000000003")
    wrong_pair_event = event(wrong_pair_target)
    row = fusion.fuse(target, [wrong_pair_event], POLICY, now_dt=NOW)
    assert row["current_evidence_count"] == 0, "same symbol on a different pair must never fuse"

    missing_ts = event(target)
    missing_ts.pop("event_time", None)
    missing_ts.pop("observed_at", None)
    row = fusion.fuse(target, [missing_ts], POLICY, now_dt=NOW)
    assert row["current_evidence_count"] == 0
    assert row["invalid_timestamp_evidence_count"] == 1

    stale = event(target, at=NOW - timedelta(minutes=181))
    row = fusion.fuse(target, [stale], POLICY, now_dt=NOW)
    assert row["current_evidence_count"] == 0
    assert row["stale_evidence_count"] == 1
    assert row["status"] == "STALE_ONLY"

    upper = dict(target, contract=target["contract"].upper(), pair=target["pair"].upper())
    row = fusion.fuse(target, [event(upper)], POLICY, now_dt=NOW)
    assert row["current_evidence_count"] == 1, "EVM identity must be case-insensitive"

    sol = {"symbol": "RAY", "network": "solana", "contract": "AbCdEf123456789ABCDEFGHJKLMNPQRSTUVWXYZ", "pair": "9ZyXwVuTsRqPonMLKJHGFEDCBA987654321abcde"}
    sol_wrong_case = dict(sol, contract=sol["contract"].lower())
    row = fusion.fuse(sol, [event(sol_wrong_case)], POLICY, now_dt=NOW)
    assert row["current_evidence_count"] == 0, "Solana base58 identity must remain case-sensitive"

    hard = event(target, family="supply_tokenomics", kind="honeypot_or_transfer_block", direction=-1, strength=100, confidence=100, hard_risk=True)
    row = fusion.fuse(target, [good, hard], POLICY, now_dt=NOW)
    assert row["score"] <= 29
    assert "honeypot_or_transfer_block" in row["hard_risks"]

    # Newer exact-pair execution evidence may supersede an older provider hard-risk
    # flag, but only when the event explicitly names the hard-risk kind it replaces.
    conflict = event(
        target,
        family="supply_tokenomics",
        kind="honeypot_provider_conflict_real_sells",
        direction=-1,
        strength=55,
        confidence=80,
        at=NOW + timedelta(minutes=1),
        hard_risk=False,
        supersedes_hard_risk_kinds=["honeypot_or_transfer_block"],
    )
    row = fusion.fuse(target, [hard, conflict], POLICY, now_dt=NOW + timedelta(minutes=1))
    assert "honeypot_or_transfer_block" not in row["hard_risks"]

    unrelated = event(
        target,
        family="supply_tokenomics",
        kind="other_warning",
        direction=-1,
        strength=20,
        confidence=80,
        at=NOW + timedelta(minutes=1),
        supersedes_hard_risk_kinds=["different_risk"],
    )
    row = fusion.fuse(target, [hard, unrelated], POLICY, now_dt=NOW + timedelta(minutes=1))
    assert "honeypot_or_transfer_block" in row["hard_risks"]

    neutral = event(target, kind="verified_market_snapshot", direction=0, strength=0, confidence=100)
    row = fusion.fuse(target, [neutral], POLICY, now_dt=NOW)
    assert row["current_evidence_count"] == 1
    assert row["score"] == 0.0
    assert row["status"] == "CURRENT"

    print("INTELLIGENCE_FUSION_CONTRACT_OK")


if __name__ == "__main__":
    main()
