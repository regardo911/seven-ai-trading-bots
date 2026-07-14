"""Bench B1 — Volatility risk premium (Appendix B).

Short defined-risk vol on SPX: when IV is cheap-percentile (or VIX < 18), sell
an ATM put and buy a put 5% further out. The long leg caps the loss — never
sell naked SPX puts. Max 3 simultaneous spreads; each sized so max loss <= 1%
of strategy capital.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from framework import cli, data
from framework.brokers import Order

IV_PERCENTILE_ENTRY = 30.0
VIX_ENTRY = 18.0
MAX_SPREADS = 3
SPREAD_WIDTH_PCT = 0.05      # long leg 5% OTM below the short ATM leg
TARGET_DTE = 35              # 30-45 DTE band
PROFIT_TAKE = 0.50           # close at 50% of max profit
DTE_EXIT = 5
MAX_LOSS_PCT = 0.01          # per-spread max loss <= 1% of strategy capital
CREDIT_FRACTION = 0.30       # synthetic premium model: credit = 30% of width


def entry_ok(date: pd.Timestamp, open_spreads: int,
             vix: float | None = None) -> bool:
    """B1 entry rule: IV percentile < 30 OR VIX < 18, and < 3 open spreads."""
    if open_spreads >= MAX_SPREADS:
        return False
    ivp = data.iv_percentile("SPX", date)
    if vix is None:
        series = data.vix_series()
        vix = float(series.loc[series.index <= pd.Timestamp(date)].iloc[-1])
    return ivp < IV_PERCENTILE_ENTRY or vix < VIX_ENTRY


def signal(date: pd.Timestamp, open_spreads: int = 0,
           capital: float = 100_000.0) -> Optional[Order]:
    """One defined-risk put spread when the entry condition holds."""
    date = pd.Timestamp(date)
    if not entry_ok(date, open_spreads):
        return None
    spx_bars = data.get_bars("SPX", end=str(date.date()))
    spx = float(spx_bars["close"].iloc[-1])
    width = SPREAD_WIDTH_PCT * spx
    credit = CREDIT_FRACTION * width      # synthetic pricing (see docs/book-reconciliations.md)
    max_loss_per_spread = (width - credit) * 100.0
    contracts = int((capital * MAX_LOSS_PCT) / max_loss_per_spread)
    if contracts < 1:
        return None
    return Order("SPX", contracts, "sell", meta={
        "instrument": "put_spread", "short_strike": spx,
        "long_strike": spx * (1 - SPREAD_WIDTH_PCT), "dte": TARGET_DTE,
        "credit": credit, "width": width, "max_loss": max_loss_per_spread,
        "profit_take": PROFIT_TAKE, "dte_exit": DTE_EXIT,
    })


def should_close(position: dict, spx: float, dte: int,
                 captured_profit_pct: float) -> str | None:
    """B1 exits: 50% of max profit, DTE <= 5, or the long strike breached."""
    if captured_profit_pct >= PROFIT_TAKE:
        return "profit_take"
    if dte <= DTE_EXIT:
        return "dte_exit"
    if spx <= position["long_strike"]:
        return "long_strike_breached"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser("strategies.bench.vrp",
                              "Bench B1: SPX volatility risk premium (defined-risk).")
    args = parser.parse_args(argv)
    cli.banner("bench: volatility risk premium (Appendix B1)")
    cli.guard_live(args)
    asof = pd.Timestamp(data.SIM_END)
    order = signal(asof)
    if order is None:
        print("[vrp] no entry: IV/VIX condition not met or spread cap reached")
    else:
        m = order.meta
        print(f"[vrp] paper spread: sell {order.qty}x SPX {m['short_strike']:.0f}p / "
              f"buy {m['long_strike']:.0f}p, {m['dte']} DTE, "
              f"credit ~${m['credit']:.2f}, max loss ${m['max_loss']:.0f}/spread")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
