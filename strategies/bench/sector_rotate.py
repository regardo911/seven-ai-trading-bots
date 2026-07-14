"""Bench B3 — Sector momentum rotation (Appendix B).

On the first trading day of each month, rank the 11 GICS sector ETFs by the
standard 12-1 momentum factor (trailing 12-month return excluding the most
recent month), hold the top 3 equal-weight, rebalance monthly. Slow factor
exposure, deliberately uncorrelated to VRP and FX trend.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

import pandas as pd

from framework import cli, data
from framework.brokers import Order, broker_for

SECTOR_ETFS = ["XLK", "XLV", "XLF", "XLY", "XLP", "XLE", "XLI", "XLB",
               "XLU", "XLRE", "XLC"]
TOP_N = 3
LOOKBACK = 252          # trailing 12 months...
SKIP_RECENT = 21        # ...excluding the most recent month (12-1 factor)


def momentum_12_1(closes: pd.Series) -> float:
    """The standard 12-1 momentum factor (Appendix B3)."""
    if len(closes) < LOOKBACK:
        return float("nan")
    return float(closes.iloc[-SKIP_RECENT] / closes.iloc[-LOOKBACK] - 1.0)


def rank_sectors(asof: pd.Timestamp) -> list[tuple[str, float]]:
    scores = []
    for etf in SECTOR_ETFS:
        closes = data.get_bars(etf, end=str(pd.Timestamp(asof).date()))["close"]
        score = momentum_12_1(closes)
        if score == score:  # not NaN
            scores.append((etf, score))
    return sorted(scores, key=lambda kv: kv[1], reverse=True)


def signal(date: pd.Timestamp, holdings: list[str] | None = None,
           capital: float = 100_000.0) -> list[Order]:
    """Monthly rebalance into the top-3 (equal weight); drop the fallers."""
    date = pd.Timestamp(date)
    holdings = holdings or []
    ranked = rank_sectors(date)
    top = [etf for etf, _ in ranked[:TOP_N]]
    orders: list[Order] = []
    sleeve = capital / TOP_N
    for etf in holdings:
        if etf not in top:
            px = float(data.get_bars(etf, end=str(date.date()))["close"].iloc[-1])
            orders.append(Order(etf, int(sleeve / px), "sell",
                                meta={"reason": "fell_out_of_top3"}))
    for etf in top:
        if etf not in holdings:
            px = float(data.get_bars(etf, end=str(date.date()))["close"].iloc[-1])
            qty = int(sleeve / px)
            if qty:
                orders.append(Order(etf, qty, "buy", meta={"rank": top.index(etf) + 1}))
    return orders


def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser("strategies.bench.sector_rotate",
                              "Bench B3: monthly 12-1 momentum rotation, top-3 GICS ETFs.")
    args = parser.parse_args(argv)
    cli.banner("bench: sector momentum rotation (Appendix B3)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live
    asof = pd.Timestamp(data.SIM_END)
    ranked = rank_sectors(asof)
    print(f"[sector-rotate] 12-1 momentum ranking as of {asof.date()}:")
    for i, (etf, score) in enumerate(ranked, 1):
        marker = " <- hold" if i <= TOP_N else ""
        print(f"  {i:>2}. {etf:<5} {score:+.1%}{marker}")
    for order in signal(asof):
        broker_for(order.symbol, paper=paper).place_order(order.symbol, order.qty,
                                             order.side, "market")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
