"""Chapter 3 lab — the gentle first contact (read this before the whole portfolio).

The raw `make demo` runs all seven bots and prints a portfolio dashboard, which
can leave a first-time reader thinking "the machine found an edge." It didn't —
that output is a plumbing check on synthetic data. This lab does the opposite:
it shows the Chapter 3 trend rule making ONE clear BUY and ONE clear WAIT, with
the exact three numbers behind each decision, so your first experience is
"I can read the mechanic."

Everything here is SYNTHETIC SAMPLE DATA — illustrative of the rules only, not a
backtest result and not a forecast. See DISCLAIMER.md.

Run: `python examples/demo_ch03.py`  (or `make demo-ch03`)
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from framework import data  # noqa: E402
from strategies import trend  # noqa: E402

SYMBOL = "SPY"
ACCOUNT = 100_000.0


def _line(bar) -> str:
    return (f"close {bar['close']:.2f}  |  prior-20d high "
            f"{bar['donchian_high_20']:.2f}  |  200-day SMA {bar['sma_200']:.2f}")


def main() -> int:
    print("== Chapter 3 lab: the trend entry rule, one BUY and one WAIT ==")
    print("Rule (ch03): BUY when close > the prior 20-day high AND close > the 200-day SMA.")
    print("Synthetic sample data — illustrative mechanics only, not a result.\n")

    bars = trend.compute_indicators(data.get_bars(SYMBOL))
    bars = bars.dropna(subset=["donchian_high_20", "sma_200", "atr_14"])
    entries = [i for i in range(len(bars)) if trend.is_entry(bars.iloc[i])]
    waits = [i for i in range(len(bars)) if not trend.is_entry(bars.iloc[i])]

    # Pick a representative day of each kind (deterministic — middle of each set).
    sig = bars.iloc[entries[len(entries) // 2]]
    flat = bars.iloc[waits[len(waits) // 2]]

    stop_distance = trend.ATR_MULTIPLIER * float(sig["atr_14"])
    qty = trend.position_size(ACCOUNT, stop_distance)

    print(f"[SIGNAL]   {sig.name.date()}  {_line(sig)}")
    print(f"           -> close cleared BOTH gates, so the rule fires: "
          f"BUY {qty} {SYMBOL}")
    print(f"           initial stop {sig['close'] - stop_distance:.2f}  "
          f"(risk 1% of ${ACCOUNT:,.0f} / {stop_distance:.2f} stop distance = "
          f"{qty} shares)\n")

    print(f"[NO SIGNAL] {flat.name.date()}  {_line(flat)}")
    print("           -> close did NOT clear the prior-20d high and/or the 200-SMA, "
          "so the rule says WAIT\n")

    print(f"Across the whole synthetic history: {len(entries)} BUY days vs "
          f"{len(waits)} WAIT days. Most days are WAIT days — sitting out is the "
          "strategy, not a bug (ch03: you sit through 3-6 month flat periods).")
    print("\nWhat would break this? Shorten DONCHIAN_WINDOW or drop the 200-SMA "
          "filter in strategies/trend.py and re-run: you get far more entries, and "
          "most of the new ones are noise. The filter is the edge.")
    print("\nNext: `make demo-ch09` (the allocator, honestly captioned), then "
          "`make realism` (what fees and inference cost do to every edge).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
