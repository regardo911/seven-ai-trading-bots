"""Trend-bot backtest (ch03 BUILD STEP 6-7): SPY/QQQ/ES/GC, per-regime table.

Synthetic sample data; illustrative mechanics only. Not financial advice.
"""

from __future__ import annotations

from backtest import common

print_report = common.print_report


def run(symbols=None, write: bool = True) -> dict:
    runner = common.TrendRunner(symbols=symbols)
    result = common.run_runner(runner)
    if write:
        common.save_json("trend", result)
    return result


if __name__ == "__main__":
    print_report(run(), regime=True)
