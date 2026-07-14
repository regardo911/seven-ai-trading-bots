"""News-bot backtest (ch06 BUILD STEP 8): post-cutoff headlines with the
inference cost tracked and netted per ch11.

Synthetic sample data; illustrative mechanics only. Not financial advice.
"""

from __future__ import annotations

from backtest import common

print_report = common.print_report


def run(write: bool = True) -> dict:
    runner = common.NewsRunner()
    result = common.run_runner(runner)
    if write:
        common.save_json("news", result)
    return result


if __name__ == "__main__":
    print_report(run(), regime=True)
