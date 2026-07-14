"""ch03 rules: Donchian entry, ratcheting trailing stop, the sizing formula."""

import pandas as pd

from framework import data
from strategies import trend


def _bar(**kwargs) -> pd.Series:
    return pd.Series(kwargs)


def test_indicator_columns():
    bars = trend.compute_indicators(data.get_bars("SPY").tail(300))
    for col in ("donchian_high_20", "sma_200", "atr_14"):
        assert col in bars.columns
        assert bars[col].notna().iloc[-1]


def test_is_entry_needs_both_rules():
    yes = _bar(close=101.0, donchian_high_20=100.0, sma_200=90.0)
    below_sma = _bar(close=101.0, donchian_high_20=100.0, sma_200=150.0)
    no_breakout = _bar(close=99.0, donchian_high_20=100.0, sma_200=90.0)
    assert trend.is_entry(yes)
    assert not trend.is_entry(below_sma)
    assert not trend.is_entry(no_breakout)


def test_trailing_stop_never_lowers():
    position = {"high_water": 100.0, "stop": 88.0, "qty": 10}
    # ATR spikes: the naive stop would DROP; the book's rule ratchets only up.
    bar = _bar(high=101.0, low=95.0, atr_14=10.0)
    assert trend.update_trailing_stop(position, bar) == "HOLD"
    assert position["stop"] == 88.0  # max(88, 101 - 30) -> unchanged
    bar2 = _bar(high=120.0, low=110.0, atr_14=4.0)
    assert trend.update_trailing_stop(position, bar2) == "HOLD"
    assert position["stop"] == 108.0  # ratcheted up
    bar3 = _bar(high=109.0, low=107.0, atr_14=4.0)
    assert trend.update_trailing_stop(position, bar3) == "EXIT"


def test_position_size_matches_book_worked_example():
    # ch03: $10,000 account, 1% risk = $100; SPY ATR $4 -> stop $12 -> 8 shares.
    assert trend.position_size(10_000, stop_distance=12.0, risk_pct=0.01) == 8


def test_signal_none_under_sma_warmup():
    bars = trend.compute_indicators(data.get_bars("SPY").tail(150))
    assert trend.signal(bars, symbol="SPY") is None
