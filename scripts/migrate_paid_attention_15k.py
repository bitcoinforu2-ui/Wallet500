from pathlib import Path


def replace(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    new = text
    for old, replacement in pairs:
        new = new.replace(old, replacement)
    if new != text:
        path.write_text(new, encoding="utf-8")


replace(
    Path("src/wallet500/paid_attention_watch.py"),
    [
        ("MIN_RESEARCH_LIQUIDITY_USD = 50_000.0", "MIN_RESEARCH_LIQUIDITY_USD = 15_000.0"),
        ("live_liquidity_lt_50k", "live_liquidity_lt_15k"),
        ("liquidity >= $50K", "liquidity >= $15K"),
    ],
)

replace(
    Path("tests/test_paid_attention_watch.py"),
    [
        ("test_below_50k_is_learning_not_main_watch", "test_below_15k_is_learning_not_main_watch"),
        ("None, 30000, 35000", "None, 12000, 14000"),
    ],
)
