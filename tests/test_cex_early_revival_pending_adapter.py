from wallet500 import cex_early_revival_pending_adapter as mod


def test_alias_symbol_collapses_to_base():
    assert mod._base_symbol_fixed("MLPUSDT:MLP_USDT") == "MLP"
    assert mod._base_symbol_fixed("BRUSDT:BR-USDT") == "BR"
    assert mod._base_symbol_fixed("AINUSDT") == "AIN"
