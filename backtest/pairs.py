"""Pairs-bot backtest (ch04 BUILD STEP 7): rolling-cointegration walk-forward.

Synthetic sample data; illustrative mechanics only. Not financial advice.
"""

from __future__ import annotations

from backtest import common

print_report = common.print_report


def run(window: int = 252, basket=None, write: bool = True) -> dict:
    runner = common.PairsRunner(basket=basket, window=window)
    result = common.run_runner(runner)
    result["params"]["rolling_coint_window"] = window
    if write:
        common.save_json("pairs", result)
    return result


if __name__ == "__main__":
    print_report(run(), regime=True)
