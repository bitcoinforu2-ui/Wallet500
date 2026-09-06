import json
from pathlib import Path

from wallet500 import coin_profile_quality_guard as qg


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def base_files(root: Path, profile: dict):
    key = profile["profile_id"]
    write(root, "coin-intelligence-profile-ledger.json", {
        "truth_contract": {},
        "profiles": {key: profile},
    })
    write(root, "coin-intelligence-profiles.json", {
        "mode": "COIN_INTELLIGENCE_PROFILE_V1",
        "counts": {},
        "truth_contract": {},
        "profiles": [json.loads(json.dumps(profile))],
    })
    write(root, "coin-intelligence-profile-archive.json", {"entries": {}})
    write(root, "coin-profile-dna-library.json", {
        "counts": {},
        "truth_contract": {},
        "profiles": {key: {
            "profile_id": key,
            "fingerprint": json.loads(json.dumps(profile["fingerprint"])),
            "outcome": {"label": "UNLABELED"},
        }},
    })


def test_catastrophic_price_conflict_is_retained_raw_but_removed_from_dna(tmp_path):
    profile = {
        "profile_id": "ethereum:0x" + "1" * 40,
        "chain": "ethereum",
        "token_address": "0x" + "1" * 40,
        "timeline": [
            {
                "first_seen_at": "2026-09-07T10:00:00+00:00",
                "last_seen_at": "2026-09-07T10:00:00+00:00",
                "lane": "CEX_REVIVAL",
                "facts": {"reference_price": 6.245, "dex_price_usd": 4_576_977.1},
            },
            {
                "first_seen_at": "2026-09-07T12:30:00+00:00",
                "last_seen_at": "2026-09-07T12:30:00+00:00",
                "lane": "REVIVAL_SNAPSHOT",
                "facts": {"price_usd": 6_046_926.38, "liquidity_usd": 61_785_723.91},
            },
        ],
        "fingerprint": {
            "dimensions": {
                "price_structure": 0.9,
                "liquidity_depth": 1.0,
                "revival_strength": 0.1,
            },
            "feature_coverage_count": 3,
            "feature_coverage_ratio": 1.0,
        },
    }
    base_files(tmp_path, profile)
    report = qg.run(tmp_path)

    ledger = json.loads((tmp_path / "coin-intelligence-profile-ledger.json").read_text())
    guarded = ledger["profiles"][profile["profile_id"]]
    assert guarded["timeline"][0]["facts"]["dex_price_usd"] == 4_576_977.1
    assert guarded["timeline"][0]["facts"]["reference_price"] == 6.245
    assert guarded["fingerprint"]["dimensions"]["price_structure"] == 0.9
    assert guarded["learning_fingerprint"]["dimensions"]["price_structure"] is None
    assert guarded["learning_fingerprint"]["dimensions"]["liquidity_depth"] == 1.0
    assert guarded["data_quality"]["status"] == "CONFLICT_QUARANTINED"
    assert "price" in guarded["data_quality"]["quarantined_metric_families"]
    assert report["counts"]["profiles_quarantined"] == 1
    assert report["counts"]["price_conflicts"] == 1

    dna = json.loads((tmp_path / "coin-profile-dna-library.json").read_text())
    d = dna["profiles"][profile["profile_id"]]
    assert d["raw_fingerprint"]["dimensions"]["price_structure"] == 0.9
    assert d["fingerprint"]["dimensions"]["price_structure"] is None
    assert d["research_similarity_eligible"] is False


def test_clean_profile_with_half_coverage_can_be_similarity_research_candidate(tmp_path):
    profile = {
        "profile_id": "solana:Mint111111111111111111111111111111111111111",
        "chain": "solana",
        "token_address": "Mint111111111111111111111111111111111111111",
        "timeline": [
            {
                "first_seen_at": "2026-09-07T10:00:00+00:00",
                "last_seen_at": "2026-09-07T10:00:00+00:00",
                "lane": "MARKET",
                "facts": {"price_usd": 6.2, "liquidity_usd": 200000},
            },
            {
                "first_seen_at": "2026-09-07T11:00:00+00:00",
                "last_seen_at": "2026-09-07T11:00:00+00:00",
                "lane": "CEX",
                "facts": {"reference_price": 6.3},
            },
        ],
        "fingerprint": {
            "dimensions": {
                "source_confirmation": 0.4,
                "exchange_confirmation": 0.5,
                "revival_strength": 0.7,
                "volume_acceleration": 0.6,
                "liquidity_depth": 0.8,
                "holder_safety": 0.9,
                "wallet_accumulation": None,
                "social_acceleration": None,
                "cex_acceleration": None,
                "price_structure": None,
                "risk_inverse": None,
                "evidence_density": None,
            },
            "feature_coverage_count": 6,
            "feature_coverage_ratio": 0.5,
        },
    }
    base_files(tmp_path, profile)
    report = qg.run(tmp_path)
    ledger = json.loads((tmp_path / "coin-intelligence-profile-ledger.json").read_text())
    guarded = ledger["profiles"][profile["profile_id"]]
    assert guarded["data_quality"]["status"] == "CLEAN"
    assert guarded["research_similarity_eligible"] is True
    assert report["counts"]["research_similarity_eligible"] == 1


def test_invalid_holder_concentration_quarantines_holder_dimension_only(tmp_path):
    profile = {
        "profile_id": "bsc:0x" + "2" * 40,
        "chain": "bsc",
        "token_address": "0x" + "2" * 40,
        "timeline": [
            {
                "first_seen_at": "2026-09-07T10:00:00+00:00",
                "last_seen_at": "2026-09-07T10:00:00+00:00",
                "lane": "HOLDER_CLUSTER_GATE",
                "facts": {"adjusted_top10_pct": 140, "risk_score": 40},
            }
        ],
        "fingerprint": {
            "dimensions": {
                "holder_safety": 0.0,
                "risk_inverse": 0.6,
                "liquidity_depth": 0.7,
            },
            "feature_coverage_count": 3,
            "feature_coverage_ratio": 1.0,
        },
    }
    base_files(tmp_path, profile)
    qg.run(tmp_path)
    ledger = json.loads((tmp_path / "coin-intelligence-profile-ledger.json").read_text())
    guarded = ledger["profiles"][profile["profile_id"]]
    assert guarded["learning_fingerprint"]["dimensions"]["holder_safety"] is None
    assert guarded["learning_fingerprint"]["dimensions"]["risk_inverse"] == 0.6
    assert guarded["learning_fingerprint"]["dimensions"]["liquidity_depth"] == 0.7
    assert "holder_concentration" in guarded["data_quality"]["quarantined_metric_families"]


def test_compact_archive_without_timeline_is_never_auto_similarity_eligible(tmp_path):
    write(tmp_path, "coin-intelligence-profile-ledger.json", {"truth_contract": {}, "profiles": {}})
    write(tmp_path, "coin-intelligence-profiles.json", {"counts": {}, "truth_contract": {}, "profiles": []})
    write(tmp_path, "coin-intelligence-profile-archive.json", {
        "entries": {
            "solana:old": {
                "profile_id": "solana:old",
                "fingerprint": {"dimensions": {"liquidity_depth": 0.8}},
            }
        }
    })
    write(tmp_path, "coin-profile-dna-library.json", {
        "counts": {}, "truth_contract": {},
        "profiles": {"solana:old": {"profile_id": "solana:old", "fingerprint": {"dimensions": {"liquidity_depth": 0.8}}}},
    })
    qg.run(tmp_path)
    dna = json.loads((tmp_path / "coin-profile-dna-library.json").read_text())
    row = dna["profiles"]["solana:old"]
    assert row["research_similarity_eligible"] is False
    assert row["data_quality"]["status"] == "QUALITY_NOT_REEVALUATED_COMPACT_ARCHIVE"
