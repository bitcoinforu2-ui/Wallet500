import json
import tempfile
import unittest
from pathlib import Path

from wallet500.search_intelligence import (
    ProviderResult,
    collect_search_intelligence,
    fetch_coingecko,
    fetch_coinmarketcap,
    load_search_signal,
    score_snapshot,
)


def asset(rank, price=1.0, change24=2.0, provider="coingecko", token_id="alpha", symbol="ALPHA"):
    return {
        "provider": provider,
        "token_id": token_id,
        "symbol": symbol,
        "name": symbol.title(),
        "search_rank": rank,
        "market_cap_rank": 500,
        "price_usd": price,
        "price_change_24h_pct": change24,
        "observed_at": "2026-09-13T00:00:00Z",
    }


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class SearchIntelligenceTests(unittest.TestCase):
    def test_first_observation_warms_up(self):
        scored = score_snapshot([asset(20)], None)
        self.assertEqual(scored[0]["signal"], "WARMING_UP")
        self.assertEqual(scored[0]["previous_search_rank"], None)

    def test_rank_acceleration_with_quiet_price_is_pre_wave(self):
        older = {"assets": [asset(100, 1.00)]}
        previous = {"assets": [asset(40, 1.02)]}
        current = [asset(12, 1.04)]
        scored = score_snapshot(current, previous, older)
        row = scored[0]
        self.assertEqual(row["signal"], "SEARCH_PRE_WAVE")
        self.assertGreaterEqual(row["search_momentum_score"], 70)
        self.assertEqual(row["rank_improvement"], 28)
        self.assertLess(abs(row["interval_price_change_pct"]), 5)

    def test_overextended_top_rank_is_saturation(self):
        previous = {"assets": [asset(8, 1.0, 10)]}
        current = [asset(1, 1.20, 80)]
        row = score_snapshot(current, previous)[0]
        self.assertEqual(row["signal"], "SEARCH_SATURATION")

    def test_cross_source_confirmation_is_available(self):
        previous = {
            "assets": [
                asset(30, provider="coingecko", token_id="a"),
                asset(30, provider="coinmarketcap", token_id="1"),
            ]
        }
        current = [
            asset(10, provider="coingecko", token_id="a"),
            asset(12, provider="coinmarketcap", token_id="1"),
        ]
        rows = score_snapshot(current, previous)
        for row in rows:
            component = row["components"]["cross_source_confirmation"]
            self.assertTrue(component["available"])
            self.assertEqual(component["pct"], 100.0)

    def test_coinmarketcap_without_key_is_nonfatal_skip(self):
        result = fetch_coinmarketcap(api_key=None)
        self.assertEqual(result.status, "skipped_no_key")
        self.assertEqual(result.assets, [])

    def test_coingecko_normalizes_live_shape(self):
        payload = {
            "coins": [
                {
                    "item": {
                        "id": "alpha-token",
                        "name": "Alpha Token",
                        "symbol": "alpha",
                        "market_cap_rank": 123,
                        "data": {
                            "price": 0.42,
                            "price_change_percentage_24h": {"usd": 3.5},
                        },
                    }
                }
            ]
        }

        def opener(request, timeout=20):
            self.assertIn("search/trending", request.full_url)
            return FakeResponse(payload)

        result = fetch_coingecko(opener=opener, observed_at="2026-09-13T01:00:00Z")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.assets[0]["symbol"], "ALPHA")
        self.assertEqual(result.assets[0]["search_rank"], 1)
        self.assertEqual(result.assets[0]["price_usd"], 0.42)

    def test_collection_persists_state_and_latest(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            latest = Path(temp) / "latest.json"

            def first():
                return ProviderResult("coingecko", "ok", [asset(50, 1.00)])

            first_run = collect_search_intelligence(
                state_path=state,
                latest_path=latest,
                fetchers=[first],
                observed_at="2026-09-13T01:00:00Z",
                require_live=True,
            )
            self.assertEqual(first_run["decision_mode"], "shadow")
            self.assertFalse(first_run["changes_real_alert_gate"])
            self.assertEqual(first_run["assets"][0]["signal"], "WARMING_UP")

            def second():
                return ProviderResult("coingecko", "ok", [asset(10, 1.02)])

            second_run = collect_search_intelligence(
                state_path=state,
                latest_path=latest,
                fetchers=[second],
                observed_at="2026-09-13T01:10:00Z",
                require_live=True,
            )
            self.assertEqual(second_run["assets"][0]["signal"], "SEARCH_PRE_WAVE")
            saved_state = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(len(saved_state["snapshots"]), 2)
            loaded = load_search_signal("alpha", latest)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["symbol"], "ALPHA")

    def test_provider_failure_isolated_when_another_source_works(self):
        with tempfile.TemporaryDirectory() as temp:
            good = lambda: ProviderResult("coingecko", "ok", [asset(5)])
            bad = lambda: ProviderResult("coinmarketcap", "error", [], "boom")
            result = collect_search_intelligence(
                state_path=Path(temp) / "state.json",
                latest_path=Path(temp) / "latest.json",
                fetchers=[good, bad],
                require_live=True,
            )
            self.assertEqual(result["collection"]["live_provider_count"], 1)
            self.assertEqual(result["collection"]["providers"]["coinmarketcap"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
