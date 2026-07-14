"""PEAD-bot backtest (ch05 BUILD STEP 8): post-cutoff transcripts only by
default — pre-cutoff LLM backtests are contaminated by training data (ch05).

Synthetic sample data; illustrative mechanics only. Not financial advice.
"""

from __future__ import annotations

from backtest import common

print_report = common.print_report


def run(post_cutoff_only: bool = True, write: bool = True) -> dict:
    runner = common.EarningsRunner(post_cutoff_only=post_cutoff_only)
    result = common.run_runner(runner)
    result["params"]["post_cutoff_only"] = post_cutoff_only
    if write:
        common.save_json("earnings", result)
    return result


if __name__ == "__main__":
    print_report(run(), regime=True)
