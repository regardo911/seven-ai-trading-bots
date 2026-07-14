"""Regenerate every backtest in one command (Appendix A6):

    python -m framework.backtest_all --realism-pass --regime-breakdown

Runs the six strategy backtests, optionally re-prices each through the ch11
realism layer into ``backtest/results/realism_pass/``, and prints the
gross-vs-net summary the ch12 ladder evaluates.

Synthetic sample data; illustrative mechanics only. Not financial advice.
"""

from __future__ import annotations

import argparse

from framework import cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="framework.backtest_all",
        description="Run all strategy backtests (+ realism layer) — Appendix A6.",
    )
    parser.add_argument("--realism-pass", action="store_true")
    parser.add_argument("--regime-breakdown", action="store_true")
    args = parser.parse_args(argv)
    cli.banner("backtest_all (Appendix A6)")

    from backtest import common

    names = ["trend", "pairs", "earnings", "news", "flow", "cash_carry"]
    rows = []
    for name in names:
        module = __import__(f"backtest.{name}", fromlist=["run"])
        result = module.run(write=True)
        common.print_report(result, regime=args.regime_breakdown)
        net = None
        if args.realism_pass:
            net = common.realism_pass(result)
            common.save_json(name, net, subdir="realism_pass")
            common.print_report(net, regime=False)
        rows.append((name, result, net))

    print("\n=== SUMMARY (synthetic sample data - illustrative only) ===")
    header = (f"{'strategy':<12}{'gross Sharpe':>13}{'net Sharpe':>12}"
              f"{'gross AnnRet':>14}{'net AnnRet':>12}{'trades':>8}")
    print(header)
    print("-" * len(header))
    for name, gross, net in rows:
        gm, nm = gross["metrics"], (net or {}).get("metrics", {})
        print(f"{name:<12}{gm['sharpe']:>13.2f}"
              f"{nm.get('sharpe', float('nan')):>12.2f}"
              f"{gm['annualized_return']:>13.1%}"
              f"{nm.get('annualized_return', float('nan')):>12.1%}"
              f"{gm['trade_count']:>8}")
    if args.realism_pass:
        print("realism layer applied: slippage + commissions + partial fills "
              "+ latency + Claude inference (ch11). The net Sharpe should be "
              "lower - if it isn't, the layer isn't doing real work.")
    print(f"note: {common.DISCLAIMER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
