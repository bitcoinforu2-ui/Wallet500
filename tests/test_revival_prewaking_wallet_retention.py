from wallet500 import revival_prewaking_wallet_retention as retention


def test_retains_only_fresh_exact_pair_rows(monkeypatch):
    revival = {"coins": []}
    ranked = [
        {"token_address": "MintA", "pair_address": "PairA", "reason": "PRE_WAKING_DEEP_WATCH"},
        {"token_address": "MintB", "pair_address": "PairB", "reason": "PRE_WAKING_DEEP_WATCH"},
        {"token_address": "MintC", "pair_address": "PairC", "reason": "PRE_WAKING_DEEP_WATCH"},
    ]
    state = {
        "tokens": {
            "MintA": {"pair_address": "PairA", "last_run": {"at": 990}},
            "MintB": {"pair_address": "WrongPair", "last_run": {"at": 995}},
            "MintC": {"pair_address": "PairC", "last_run": {"at": 100}},
        }
    }

    monkeypatch.setattr(retention.pre, "_ranked_candidates", lambda _: ranked)
    monkeypatch.setattr(retention.collector, "_epoch_now", lambda: 1000)
    monkeypatch.setattr(
        retention.collector,
        "_load",
        lambda path, default: revival if path == retention.pre.REVIVAL else state,
    )
    monkeypatch.setattr(
        retention.collector,
        "_summary_for",
        lambda target, token_state, now: {
            "token_address": target["token_address"],
            "exact_pair": target["pair_address"],
            "coverage": {},
        },
    )
    monkeypatch.setattr(retention.collector, "_write", lambda path, payload: None)
    monkeypatch.setattr(retention, "RETAIN_SECONDS", 120)

    payload = {
        "tokens": [
            {
                "token_address": "MintSelected",
                "exact_pair": "PairSelected",
                "selection_lane": "ROTATION_COVERAGE",
            }
        ]
    }
    out = retention.retain_fresh_rotation_evidence(payload)

    assert out["selected_target_tokens"] == ["MintSelected"]
    assert {row["token_address"] for row in out["tokens"]} == {"MintSelected", "MintA"}
    kept = next(row for row in out["tokens"] if row["token_address"] == "MintA")
    assert kept["selection_lane"] == "ROTATION_COVERAGE"
    assert kept["publication_lane"] == "RETAINED_ROTATION_EVIDENCE"
    assert kept["coverage"]["retained_rotation_evidence"] is True
    assert out["rotation_retention"]["retained_fresh_rows"] == 1
    assert out["rotation_retention"]["pair_mismatch_rows_skipped"] == 1
    assert out["rotation_retention"]["stale_rows_skipped"] == 1
    assert out["truth_contract"]["retained_rotation_rows_never_change_positive_status"] is True
