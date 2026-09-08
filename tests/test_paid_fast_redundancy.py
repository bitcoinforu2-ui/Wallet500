from wallet500.paid_fast_redundancy import (
    TELEGRAM_SOURCES,
    X_SOURCES,
    classify_text,
    extract_solana_addresses,
    main_paid_tokens,
    merge_observation,
)

TOKEN = "5qJb9NqPCVzAyF8VGxxz8cJX76bLJYYKN3Ftofo5pump"
PAIR = "7K7pUhUHS4cRD6urry2ZfX7M5iAn2nZUr4kEtdVP6HMu"


def test_classify_paid_boost_and_other_surfaces():
    assert classify_text("Detected PAID Ads DEXScreener: $X") == ["DEXSCREENER_PAID_AD"]
    assert "DEXSCREENER_BOOST" in classify_text("Detect Boost 30⚡ DEXScreener: $MANGA")
    assert "DEXTOOLS_TREND" in classify_text("🐳 DexTools Trends 🐳 Event chat")
    assert "INFLUENCER_SIGNAL" in classify_text("🗣 Influencer Post 🗣 Event chat")


def test_extract_solana_address_ignores_urls():
    text = f"Detected PAID DEXScreener CA: `{TOKEN}` Check https://gmgn.ai/sol/token/abc"
    assert extract_solana_addresses(text) == [TOKEN]


def test_registry_has_no_duplicate_handles():
    tg = [x["handle"].lower() for x in TELEGRAM_SOURCES]
    xx = [x["handle"].lower() for x in X_SOURCES]
    assert len(tg) == len(set(tg))
    assert len(xx) == len(set(xx))
    assert "dexssignal" in tg
    assert "dex_kolwatcher" in xx


def test_main_paid_token_reconciliation():
    payload = {"events": [{"chain": "solana", "token_address": TOKEN}, {"chain": "bsc", "token_address": "0x1"}]}
    assert main_paid_tokens(payload) == {TOKEN}


def test_merge_preserves_pair_and_adds_independent_source():
    events = []
    market = {"pair_address": PAIR, "token_address": TOKEN, "price_usd": 1.0}
    obs1 = {"source": "dexscreener_official", "source_handle": "TOKEN_BOOST_LATEST", "id": "a", "event_types": ["DEXSCREENER_BOOST"], "token_address": TOKEN}
    first = merge_observation(events, obs1, "2026-09-08T12:00:00+00:00", market, False)
    assert first["official_dexscreener_seen"] is True
    assert first["pair_identity_locked"] is True
    obs2 = {"source": "telegram", "source_handle": "dexssignal", "id": "dexssignal/1", "published_at": "2026-09-08T12:01:00+00:00", "event_types": ["DEXSCREENER_PAID"], "token_address": TOKEN}
    second = merge_observation(events, obs2, "2026-09-08T12:02:00+00:00", market, True)
    assert second is first
    assert second["main_paid_ledger_covered"] is True
    assert second["external_confirmation_handles"] == ["dexssignal"]
    assert len(second["source_evidence"]) == 2
