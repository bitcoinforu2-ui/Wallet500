import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "targeted_binance_spot_watch.py"
spec = importlib.util.spec_from_file_location("targeted_binance_spot_watch", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
announcement_title_matches = module.announcement_title_matches
cms_listing_signals = module.cms_listing_signals


def target():
    return {"symbol": "TAKE", "project_names": ["OVERTAKE"], "spot_symbols": ["TAKEUSDT"]}


def test_exact_overtake_binance_spot_listing_title_matches():
    assert announcement_title_matches("Binance Will List OVERTAKE (TAKE) with Seed Tag Applied", target())


def test_common_english_take_does_not_match_without_project_identity():
    assert not announcement_title_matches("Binance will list ABC — take part in the trading campaign", target())


def test_futures_perpetual_is_rejected_even_with_exact_identity():
    assert not announcement_title_matches("Binance Futures Will Launch OVERTAKE (TAKE) Perpetual Contract", target())


def test_alpha_mention_is_not_spot_listing():
    assert not announcement_title_matches("OVERTAKE (TAKE) is Now Available on Binance Alpha", target())


def test_nested_cms_payload_extracts_only_spot_listing():
    payload = {"data": {"catalogs": [{"articles": [
        {"code": "abc12345", "title": "Binance Will List OVERTAKE (TAKE) with Seed Tag Applied"},
        {"code": "future123", "title": "Binance Futures Will Launch OVERTAKE (TAKE) Perpetual Contract"},
    ]}]}}
    signals = cms_listing_signals(payload, target(), "https://www.binance.com/example")
    assert len(signals) == 1
    assert signals[0]["kind"] == "OFFICIAL_SPOT_ANNOUNCEMENT"
    assert signals[0]["fingerprint"] == "abc12345"
