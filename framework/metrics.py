"""Metrics, inference-cost counters, and position state (ch06 / ch10 / ch11).

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Anthropic per-million-token pricing used throughout ch11's token math.
# ($3 in / $15 out Sonnet; $5 in / $25 out Opus — "verify at the source".)
_PRICING = {"sonnet": (3.0, 15.0), "opus": (5.0, 25.0)}


def _price_for(model: str) -> tuple[float, float]:
    return _PRICING["opus"] if "opus" in model.lower() else _PRICING["sonnet"]


class InferenceCostTracker:
    """Counts every Claude call so the realism layer (ch11) can net it out."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.count = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        in_price, out_price = _price_for(model)
        cost = input_tokens * in_price / 1e6 + output_tokens * out_price / 1e6
        self.count += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost
        return cost

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


#: Module-level tracker shared by the classifier and the backtests.
inference_tracker = InferenceCostTracker()


@dataclass
class PositionState:
    """Open-position bookkeeping used by the trailing-stop strategies (ch03)."""

    symbol: str
    qty: float
    entry: float
    stop: float
    high_water: float
    opened: pd.Timestamp | None = None
    meta: dict = field(default_factory=dict)


class DrawdownTracker:
    """Month-to-date drawdown state for the ch06/ch09 circuit breakers."""

    def __init__(self, month_start_equity: float) -> None:
        self.month_start_equity = float(month_start_equity)
        self.equity = float(month_start_equity)

    def update(self, equity: float) -> None:
        self.equity = float(equity)

    @property
    def mtd_pnl_pct(self) -> float:
        if self.month_start_equity == 0:
            return 0.0
        return (self.equity - self.month_start_equity) / self.month_start_equity


# --------------------------- performance metrics ---------------------------

def sharpe(daily_returns, periods_per_year: int = 252) -> float:
    r = np.asarray(daily_returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year))


def max_drawdown(equity) -> float:
    """Peak-to-trough drawdown as a positive fraction (the cumulative-min trick)."""
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return 0.0
    peaks = np.maximum.accumulate(eq)
    dd = (eq - peaks) / np.where(peaks == 0, 1.0, peaks)
    return float(abs(dd.min()))  # abs() also normalizes -0.0


def annualized_return(daily_returns, periods_per_year: int = 252) -> float:
    r = np.asarray(daily_returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) == 0:
        return 0.0
    total = float(np.prod(1.0 + r))
    if total <= 0:
        return -1.0
    return total ** (periods_per_year / len(r)) - 1.0


def win_rate(trade_pnls) -> float:
    p = np.asarray(trade_pnls, dtype=float)
    if len(p) == 0:
        return 0.0
    return float((p > 0).mean())


def expected_value(trade_pnls) -> float:
    """Edge per trade — the headline metric ch10 insists on over win rate."""
    p = np.asarray(trade_pnls, dtype=float)
    return float(p.mean()) if len(p) else 0.0
