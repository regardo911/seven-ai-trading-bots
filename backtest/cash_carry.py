"""Cash-and-carry backtest (ch08 BUILD STEP 8): replay of the funding-rate
history with the same threshold and circuit-breaker rules the bot trades.

Synthetic sample data; illustrative mechanics only. Not financial advice.
"""

from __future__ import annotations

from backtest import common

print_report = common.print_report


def run(months: int = 24, exchanges=None, instruments=None,
        write: bool = True) -> dict:
    runner = common.CashCarryRunner(exchanges=exchanges, instruments=instruments,
                                    months=months)
    result = common.run_runner(runner)
    result["params"]["funding_history_months"] = months
    breaker_trades = sum(1 for d in result["trades_detail"]
                         if d.get("gross_pnl", 0) < 0)
    result["params"]["circuit_breaker_note"] = (
        f"{breaker_trades} losing unwinds (incl. inversion breaker fires)"
    )
    if write:
        common.save_json("cash_carry", result)
    return result


if __name__ == "__main__":
    print_report(run(), regime=True)
