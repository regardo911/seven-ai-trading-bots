"""Portfolio demo: all six strategies under the ch09 allocator, paper mode.

Prints the unified dashboard (weights, breakers, MTD P&L, 90-day Sharpe,
correlation flags, netting events). Offline, zero keys, synthetic data.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from framework.allocator import Allocator  # noqa: E402

Allocator(capital=100_000.0, period_days=30).run(write=False)
