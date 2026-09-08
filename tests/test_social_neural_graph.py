from wallet500.social_neural_graph import analyze_events, canonical_author


def ev(author, ts):
    return {"author": author, "published_at": ts, "attribution": "EXACT_CONTRACT"}


def test_aliases_resolve():
    assert canonical_author("@CryptoHayes") == "arthur_hayes"
    assert canonical_author("Crypto Banter") == "ran_neuner"


def test_same_circle_is_not_three_independent_confirmations():
    rows = [
        ev("MarioNawfal", "2026-09-08T10:00:00Z"),
        ev("ScottMelker", "2026-09-08T10:05:00Z"),
        ev("CryptoManRan", "2026-09-08T10:10:00Z"),
    ]
    out = analyze_events(rows)
    assert out["known_kol_mentions"] == 3
    assert out["independent_clusters"] == 1
    assert out["cascade_score"] <= 28
    assert all(x["same_cluster"] for x in out["edges"])


def test_cross_cluster_cascade_gets_more_credit():
    rows = [
        ev("CryptoHayes", "2026-09-08T10:00:00Z"),
        ev("CoinBureau", "2026-09-08T10:10:00Z"),
        ev("CryptoManRan", "2026-09-08T10:20:00Z"),
    ]
    out = analyze_events(rows)
    assert out["independent_clusters"] == 3
    assert out["cascade_score"] > 60
    assert out["first_source"] == "arthur_hayes"


def test_name_only_context_gets_no_graph_credit():
    out = analyze_events([{"author": "CryptoHayes", "published_at": "2026-09-08T10:00:00Z", "attribution": "NAME_SYMBOL_CONTEXT"}])
    assert out["known_kol_mentions"] == 0
    assert out["cascade_score"] == 0
