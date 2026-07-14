"""Per-strategy P&L attribution with intent netting (ch09).

The allocator submits only the NET order per symbol per bar, but each strategy
is marked on its own intent contribution — "each strategy's P&L is computed
from the marked-to-market value of its share of the position, weighted by its
intent contribution" (ch09).

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from framework import data


class AttributionLedger:
    """Virtual per-strategy books marked against shared execution prices."""

    def __init__(self) -> None:
        # (strategy, symbol) -> signed qty
        self.virtual_positions: dict[tuple[str, str], float] = defaultdict(float)
        self._last_price: dict[str, float] = {}
        self.daily_pnl: dict[str, dict[pd.Timestamp, float]] = defaultdict(dict)

    def record_intent(self, strategy: str, symbol: str, signed_qty: float,
                      price: float) -> None:
        """Apply a strategy's (pre-netting) intent to its virtual book."""
        self.virtual_positions[(strategy, symbol)] += signed_qty
        self._last_price[symbol] = price

    def mark(self, date: pd.Timestamp) -> dict[str, float]:
        """Mark every virtual book to today's close; return per-strategy P&L."""
        pnl: dict[str, float] = defaultdict(float)
        prices: dict[str, float] = {}
        for (strategy, symbol), qty in self.virtual_positions.items():
            if qty == 0:
                continue
            if symbol not in prices:
                bars = data.get_bars(symbol)
                window = bars.loc[bars.index <= pd.Timestamp(date), "close"]
                prices[symbol] = float(window.iloc[-1]) if len(window) else 0.0
            last = self._last_price.get(symbol, prices[symbol])
            pnl[strategy] += qty * (prices[symbol] - last)
        for symbol, px in prices.items():
            self._last_price[symbol] = px
        for strategy, value in pnl.items():
            self.daily_pnl[strategy][pd.Timestamp(date)] = value
        return dict(pnl)

    def strategy_series(self, strategy: str) -> pd.Series:
        points = self.daily_pnl.get(strategy, {})
        return pd.Series(points).sort_index() if points else pd.Series(dtype=float)

    def total_by_strategy(self) -> dict[str, float]:
        return {s: float(self.strategy_series(s).sum()) for s in self.daily_pnl}
