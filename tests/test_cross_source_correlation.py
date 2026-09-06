from wallet500 import cross_source_correlation as csc


TOKEN = "0x1111111111111111111111111111111111111111"


def obs(owner, at, *, chain="ethereum", source_id=None, evidence_id=None, token=TOKEN):
    return {
        "evidence_id": evidence_id or f"{owner}:{source_id or owner}:{at}",
        "lane": "TEST",
        "source_owner": owner,
        "source_id": source_id or owner,
        "source_kind": "OFFICIAL_EXCHANGE",
        "source_category": "exchange",
        "event_type": "SPOT_LISTING_EXPECTED",
        "token": token,
        "chain": chain,
        "first_seen_at": at,
        "last_seen_at": at,
    }


def test_repeated_surfaces_from_same_exchange_do_not_fake_double_signal():
    assets = csc._correlate([
        obs("kraken", "2026-09-07T00:00:00+00:00", source_id="KRAKEN_WEB", evidence_id="a"),
        obs("kraken", "2026-09-07T00:05:00+00:00", source_id="KRAKEN_API", evidence_id="b"),
    ])
    asset = assets[f"ethereum:{TOKEN}"]
    assert asset["source_confirmation_count"] == 1
    assert asset["surface_count"] == 2
    assert asset["confirmation_tier"] == "SINGLE_SOURCE"
    assert asset["discovery_confirmation_multiplier"] == 1.0


def test_two_exchanges_at_different_times_create_double_confirmation():
    assets = csc._correlate([
        obs("kraken", "2026-09-07T00:00:00+00:00", evidence_id="a"),
        obs("okx", "2026-09-07T03:00:00+00:00", evidence_id="b"),
    ])
    asset = assets[f"ethereum:{TOKEN}"]
    assert asset["source_confirmation_count"] == 2
    assert asset["exchange_confirmation_count"] == 2
    assert asset["confirmation_tier"] == "DOUBLE_SOURCE_CONFIRMED"
    assert asset["discovery_confirmation_multiplier"] == 2.0
    assert asset["source_first_seen_spread_seconds"] == 3 * 60 * 60


def test_late_new_source_upgrades_already_known_asset():
    first = csc.build(
        observations=[obs("kraken", "2026-09-07T00:00:00+00:00", evidence_id="a")],
        previous={},
        ts="2026-09-07T00:01:00+00:00",
    )
    second = csc.build(
        observations=[
            obs("kraken", "2026-09-07T00:00:00+00:00", evidence_id="a"),
            obs("okx", "2026-09-07T04:00:00+00:00", evidence_id="b"),
        ],
        previous=first,
        ts="2026-09-07T04:01:00+00:00",
    )
    assert second["counts"]["upgraded_this_scan"] == 1
    upgrade = second["upgrades"][0]
    assert upgrade["previous_source_confirmation_count"] == 1
    assert upgrade["new_source_confirmation_count"] == 2
    assert upgrade["new_sources"] == ["okx"]


def test_provisional_evm_listing_attaches_only_to_unique_exact_chain_identity():
    assets = csc._correlate([
        obs("kraken", "2026-09-07T00:00:00+00:00", chain="evm_unknown", evidence_id="a"),
        obs("okx", "2026-09-07T01:00:00+00:00", chain="base", evidence_id="b"),
    ])
    assert f"evm_unknown:{TOKEN}" not in assets
    asset = assets[f"base:{TOKEN}"]
    assert asset["source_confirmation_count"] == 2
    assert asset["identity_confidence"] == "EXACT_CHAIN_CONTRACT"


def test_ambiguous_same_evm_address_never_cross_merges_exact_chains():
    assets = csc._correlate([
        obs("kraken", "2026-09-07T00:00:00+00:00", chain="evm_unknown", evidence_id="a"),
        obs("okx", "2026-09-07T01:00:00+00:00", chain="base", evidence_id="b"),
        obs("coinbase", "2026-09-07T02:00:00+00:00", chain="ethereum", evidence_id="c"),
    ])
    assert f"evm_unknown:{TOKEN}" in assets
    assert f"base:{TOKEN}" in assets
    assert f"ethereum:{TOKEN}" in assets
    assert assets[f"evm_unknown:{TOKEN}"]["source_confirmation_count"] == 1


def test_watchlist_enrichment_keeps_truth_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(csc, "WATCHLIST", tmp_path / "manual-watchlist.json")
    (tmp_path / "manual-watchlist.json").write_text(
        '[{"chain":"ethereum","token":"0x1111111111111111111111111111111111111111","source":"MANUAL"}]',
        encoding="utf-8",
    )
    assets = csc._correlate([
        obs("kraken", "2026-09-07T00:00:00+00:00", evidence_id="a"),
        obs("okx", "2026-09-07T01:00:00+00:00", evidence_id="b"),
    ])
    result = csc._merge_watchlist(assets)
    assert result["existing_rows_enriched"] == 1
    rows = csc._load(csc.WATCHLIST, [])
    assert rows[0]["source"] == "MANUAL"
    assert rows[0]["cross_source_confirmation_count"] == 2
    assert rows[0]["cross_source_continuous_rescan"] is True
