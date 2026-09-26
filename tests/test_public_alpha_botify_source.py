from scripts import public_alpha_source_collector as mod


MINT_A = "1KKPWerw6vXryXb57yzXoMqAL8NUYJ9eFdM9aqcBTFY"
MINT_B = "7C94RweVKZtBhA291WpXW7pkYEnbqhGvCFTU8nPoBTFY"
MINT_C = "3tzkdxJ1qVCaPAuWmd8FjRFKUbwMYpLUAq5gg4Vopump"


def test_botify_launch_routes_are_ingested_as_solana_only_when_enabled():
    body = (
        f'<a href="/launches/{MINT_A}">HAWKGLD</a>'
        f'<a href="/launches/{MINT_B}?ref=home">BOTIFY</a>'
    )
    assert mod.extract_candidates(body, {"extract_botify_launch_routes": True}) == [
        ("solana", MINT_A),
        ("solana", MINT_B),
    ]
    assert mod.extract_candidates(body, {}) == []


def test_newest_first_batch_retains_unselected_backlog():
    unseen = [("solana", MINT_A), ("solana", MINT_B), ("solana", MINT_C)]
    selected, mark_seen = mod.select_unseen_pairs(
        unseen,
        {
            "max_new_per_scan": 2,
            "selection_order": "head",
            "retain_unselected_backlog": True,
        },
    )
    assert selected == unseen[:2]
    assert mark_seen == unseen[:2]


def test_default_source_behavior_still_suppresses_unselected_backfill():
    unseen = [("solana", MINT_A), ("solana", MINT_B), ("solana", MINT_C)]
    selected, mark_seen = mod.select_unseen_pairs(unseen, {"max_new_per_scan": 2})
    assert selected == unseen[-2:]
    assert mark_seen == unseen


def test_botify_detail_url_is_contract_specific():
    source = {
        "url": "https://app.botify.cloud/launches",
        "source_url_template": "https://app.botify.cloud/launches/{contract}",
    }
    assert mod.source_url_for_contract(source, MINT_A) == (
        "https://app.botify.cloud/launches/" + MINT_A
    )
