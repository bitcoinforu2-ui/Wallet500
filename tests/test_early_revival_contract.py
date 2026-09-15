import pytest
from wallet500.early_revival_contract import ExactIdentity, ain_golden_identity, build_checkpoint


def test_ain_fixture_is_exact_identity_only():
    x = ain_golden_identity()
    assert x.chain == "bsc"
    assert x.token_address == "0x9558a9254890b2a8b057a789f413631b9084f4a3"
    assert x.pair_address.lower() == "0xf4262c4dbf524f53851a5176bdc7d6c1e0fa82d8"


def test_checkpoint_is_research_only_and_immutable():
    row = build_checkpoint(
        identity=ain_golden_identity(), observed_at="2026-09-15T20:00:00+00:00",
        first_price_usd=0.10, current_price_usd=0.126,
        evidence={"cex_spot_confirmations": 3, "unknown_wallet_lane": None},
        source_fresh=True, exact_pair_verified=True,
    )
    assert row["crossed_checkpoint_levels_pct"] == [15.0, 25.0]
    assert row["production_promotion_allowed"] is False
    assert row["retroactive_t0_allowed"] is False
    assert row["mutable"] is False
    assert row["evidence"]["unknown_wallet_lane"] is None
    assert len(row["truth_hash_sha256"]) == 64


def test_stale_or_unverified_fails_closed():
    x = ExactIdentity("bsc", "token", "pair")
    with pytest.raises(ValueError, match="FAIL_CLOSED"):
        build_checkpoint(identity=x, observed_at="2026-09-15T20:00:00+00:00",
                         first_price_usd=1, current_price_usd=1.2, evidence={},
                         source_fresh=False, exact_pair_verified=True)
    with pytest.raises(ValueError, match="FAIL_CLOSED"):
        build_checkpoint(identity=x, observed_at="2026-09-15T20:00:00+00:00",
                         first_price_usd=1, current_price_usd=1.2, evidence={},
                         source_fresh=True, exact_pair_verified=False)


def test_naive_timestamp_fails_closed():
    with pytest.raises(ValueError, match="TIMESTAMP_TZ_REQUIRED"):
        build_checkpoint(identity=ain_golden_identity(), observed_at="2026-09-15T20:00:00",
                         first_price_usd=1, current_price_usd=1.2, evidence={},
                         source_fresh=True, exact_pair_verified=True)
