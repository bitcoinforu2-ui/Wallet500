import wallet500.social_feed_scan_v4 as scan


def test_source_health_separates_config_direct_and_index_evidence():
    payload = {
        "direct_provider_config": {
            "x": True,
            "youtube": True,
            "reddit_oauth": False,
            "reddit_public": True,
            "telegram_public_direct": True,
        },
        "mesh_provider_config": {
            "telegram_mtproto": False,
            "farcaster_neynar": False,
            "discord_watch": False,
            "threads_keyword": False,
            "bluesky_public": True,
        },
        "mesh_public_index": {"enabled": True},
        "targets": [{
            "token_address": "TOKEN1",
            "provider_status": [
                {"provider": "x", "status": "FALLBACK_INDEX_OK_CONTEXT_ONLY"},
                {"provider": "telegram_official", "status": "OK"},
                {"provider": "telegram_mtproto", "status": "NOT_CONFIGURED"},
                {"provider": "bluesky", "status": "HTTP_403"},
                {"provider": "social_mesh_public_index", "status": "INDEX_OK_CONTEXT_ONLY"},
            ],
            "events": [
                {"source": "telegram", "author": "official", "attribution": "OFFICIAL_CHANNEL_CONTEXT", "timestamp_provenance": "TELEGRAM_ORIGINAL_DATETIME"},
                {"source": "x_index", "context_only": True, "attribution": "EXACT_CONTRACT"},
                {"source": "bluesky_index", "context_only": True, "attribution": "EXACT_PAIR"},
                {"source": "bluesky", "attribution": "EXACT_CONTRACT"},
            ],
        }],
    }
    health = scan._source_health(payload)
    assert health["version"] == 2
    assert health["providers"]["telegram_official"]["state"] == "ACTIVE_OFFICIAL_CONTEXT"
    assert health["providers"]["telegram_mtproto"]["state"] == "NOT_CONFIGURED"
    assert health["providers"]["bluesky"]["state"] == "ACTIVE_EXACT_EVIDENCE"
    assert health["providers"]["x"]["state"] == "INDEX_CONTEXT_ONLY"
    assert health["providers"]["x"]["indexed_exact_context_events"] == 1
    assert health["providers"]["x"]["exact_direct_events"] == 0
    assert health["providers"]["x"]["tokens_with_exact_evidence"] == 1
    assert health["providers"]["x"]["tokens_with_direct_exact_evidence"] == 0
    assert health["providers"]["x"]["tokens_with_indexed_exact_context"] == 1
    assert health["providers"]["bluesky"]["tokens_with_direct_exact_evidence"] == 1
    assert health["providers"]["bluesky"]["tokens_with_indexed_exact_context"] == 0
    assert health["providers"]["social_mesh_public_index"]["state"] == "INDEX_CONTEXT_ONLY"
    assert health["providers"]["social_mesh_public_index"]["indexed_exact_context_events"] == 1
    assert health["providers"]["social_mesh_public_index"]["tokens_with_direct_exact_evidence"] == 0
    assert health["providers"]["social_mesh_public_index"]["tokens_with_indexed_exact_context"] == 1
    assert health["truth"]["provider_health_does_not_modify_token_scores"] is True
    assert health["truth"]["secret_values_never_exposed"] is True
    assert health["truth"]["direct_and_indexed_exact_token_counts_are_separate"] is True


def test_mtproto_event_is_not_misclassified_as_public_telegram():
    payload = {
        "direct_provider_config": {"telegram_public_direct": True},
        "mesh_provider_config": {"telegram_mtproto": True, "bluesky_public": True},
        "mesh_public_index": {"enabled": True},
        "targets": [{
            "token_address": "TOKEN2",
            "provider_status": [
                {"provider": "telegram_official", "status": "OK"},
                {"provider": "telegram_mtproto", "status": "OK_DIRECT"},
            ],
            "events": [{
                "source": "telegram",
                "query_kind": "GLOBAL_SEARCH",
                "attribution": "EXACT_PAIR",
            }],
        }],
    }
    health = scan._source_health(payload)
    assert health["providers"]["telegram_mtproto"]["exact_direct_events"] == 1
    assert health["providers"]["telegram_mtproto"]["tokens_with_direct_exact_evidence"] == 1
    assert health["providers"]["telegram_official"]["exact_direct_events"] == 0
    assert health["providers"]["telegram_official"]["tokens_with_direct_exact_evidence"] == 0
