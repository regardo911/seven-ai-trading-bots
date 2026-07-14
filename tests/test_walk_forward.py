"""ch10: walk-forward stitches TEST windows only; regime table is complete."""


from framework import data
from framework.walk_forward import FixedParamStrategy, regime_breakdown, walk_forward_backtest


def test_walk_forward_reports_test_windows_only():
    bars = data.get_bars("SPY")
    stitched = walk_forward_backtest(bars, FixedParamStrategy(),
                                     train_days=750, test_days=125)
    # nothing from the first (train-only) 750 bars may appear in the output
    assert stitched.index.min() >= bars.index[750]
    assert len(stitched) <= len(bars) - 750


def test_walk_forward_short_series_empty():
    bars = data.get_bars("SPY").tail(100)
    out = walk_forward_backtest(bars, FixedParamStrategy())
    assert len(out) == 0


def test_regime_breakdown_covers_named_windows():
    bars = data.get_bars("SPY")
    returns = bars["close"].pct_change().fillna(0.0)
    table = regime_breakdown(returns)
    assert {"low_vol", "crisis", "mania", "bear", "recovery",
            "current"} <= set(table)
    for row in table.values():
        assert {"annualized_return", "max_drawdown", "sharpe", "days"} <= set(row)
