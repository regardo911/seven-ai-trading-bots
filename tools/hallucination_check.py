"""Mechanical half of the ch10 Claude-hallucination checklist.

Recomputes every checkable metric in a backtest results JSON from its raw
``daily_returns`` / ``trade_pnls`` arrays using plain NumPy — deliberately
independent of ``framework.metrics`` — and compares against the reported
values. That is checklist item 3/4: "never accept a number Claude reports
without an independent check."

Usage:
    python tools/hallucination_check.py backtest/results/trend.json
"""

from __future__ import annotations

import json
import sys

import numpy as np

TOLERANCE = 1e-4


def independent_metrics(daily_returns: list[float], trade_pnls: list[float]) -> dict:
    r = np.asarray(daily_returns, dtype=float)
    p = np.asarray(trade_pnls, dtype=float)
    equity = np.cumprod(1.0 + r)
    peaks = np.maximum.accumulate(equity)
    out = {
        "sharpe": (float(r.mean() / r.std(ddof=1) * np.sqrt(252))
                   if len(r) > 1 and r.std(ddof=1) > 0 else 0.0),
        "max_drawdown": float(-((equity - peaks) / peaks).min()) if len(r) else 0.0,
        "annualized_return": (float(np.prod(1 + r) ** (252 / len(r)) - 1)
                              if len(r) and np.prod(1 + r) > 0 else 0.0),
        "win_rate": float((p > 0).mean()) if len(p) else 0.0,
        "expected_value_per_trade": float(p.mean()) if len(p) else 0.0,
    }
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        result = json.load(fh)
    reported = result["metrics"]
    recomputed = independent_metrics(result["daily_returns"]["values"],
                                     result.get("trade_pnls", []))
    print(f"hallucination check: {argv[0]} ({result['strategy']})")
    failures = 0
    for key, independent_value in recomputed.items():
        reported_value = reported.get(key)
        if reported_value is None:
            continue
        ok = abs(reported_value - independent_value) <= max(
            TOLERANCE, abs(independent_value) * 0.01
        )
        status = "PASS" if ok else "FAIL"
        failures += (not ok)
        print(f"  [{status}] {key}: reported {reported_value:.6f} "
              f"vs independent {independent_value:.6f}")
    if result.get("synthetic_data"):
        print("  [info] synthetic_data=true - numbers are illustrative only")
    print("checklist items 1-2 and 5-8 are manual reads: see "
          "docs/hallucination_check.md")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
