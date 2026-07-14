"""Walk-forward backtest template + regime breakdown (ch10).

Cross-validation leaks future information on time series; walk-forward does
not. Train on a trailing window, test on the next window, roll forward, and
stitch ONLY the test windows into the reported result.

    "If you find yourself reaching for sklearn KFold on time-series data,
     stop." — ch10

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

from typing import Callable, Protocol

import numpy as np
import pandas as pd

from framework import metrics
from framework.data import REGIMES


class WalkForwardStrategy(Protocol):
    """Anything with fit()/predict() plugs into the template (ch10)."""

    def fit(self, train: pd.DataFrame) -> dict: ...

    def predict(self, test: pd.DataFrame, params: dict) -> pd.Series: ...


def walk_forward_backtest(
    bars: pd.DataFrame,
    strategy: Callable | WalkForwardStrategy,
    train_days: int = 750,   # ~3 years
    test_days: int = 125,    # ~6 months
) -> pd.DataFrame:
    """The ch10 template, verbatim mechanics: stitched test-window returns only."""
    results = []
    start = train_days
    while start + test_days < len(bars):
        train = bars.iloc[start - train_days:start]
        test = bars.iloc[start:start + test_days]
        params = strategy.fit(train)
        test_returns = strategy.predict(test, params)
        results.append(test_returns)
        start += test_days
    if not results:
        return pd.DataFrame()
    return pd.concat(results)


def regime_breakdown(daily_returns: pd.Series) -> dict[str, dict]:
    """Per-regime metrics table (ch10: 'report the worst regime, not the average')."""
    out: dict[str, dict] = {}
    for name, (start, end) in REGIMES.items():
        window = daily_returns.loc[
            (daily_returns.index >= pd.Timestamp(start))
            & (daily_returns.index <= pd.Timestamp(end))
        ]
        if len(window) < 5:
            continue
        equity = (1.0 + window).cumprod()
        out[name] = {
            "period": f"{start[:4]}-{end[:4]}" if start[:4] != end[:4] else start[:4],
            "annualized_return": round(metrics.annualized_return(window), 4),
            "max_drawdown": round(metrics.max_drawdown(equity), 4),
            "sharpe": round(metrics.sharpe(window), 2),
            "days": int(len(window)),
        }
    return out


def format_regime_table(breakdown: dict[str, dict]) -> str:
    lines = [
        f"{'Regime':<10} {'Period':<10} {'AnnRet':>8} {'MaxDD':>8} {'Sharpe':>7} {'Days':>6}",
        "-" * 55,
    ]
    for name, row in breakdown.items():
        lines.append(
            f"{name:<10} {row['period']:<10} {row['annualized_return']:>7.1%} "
            f"{row['max_drawdown']:>7.1%} {row['sharpe']:>7.2f} {row['days']:>6}"
        )
    worst = min(breakdown.values(), key=lambda r: r["annualized_return"], default=None)
    if worst is not None:
        lines.append(f"worst regime annualized return: {worst['annualized_return']:.1%}")
    return "\n".join(lines)


class FixedParamStrategy:
    """Minimal fit/predict adapter used by tests and examples: 'fits' a mean
    daily return on the train window, 'predicts' it against test returns."""

    def fit(self, train: pd.DataFrame) -> dict:
        rets = train["close"].pct_change().dropna()
        return {"bias": float(np.sign(rets.mean()) or 1.0)}

    def predict(self, test: pd.DataFrame, params: dict) -> pd.Series:
        return test["close"].pct_change().fillna(0.0) * params["bias"]
