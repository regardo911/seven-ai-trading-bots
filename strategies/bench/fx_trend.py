"""Bench B2 — FX trend following (Appendix B).

The chapter 3 Donchian rule, unchanged, on EUR/USD, USD/JPY, GBP/USD through
Interactive Brokers: 20-day breakout entry, 200-day SMA regime filter,
3x ATR(14) trailing stop. Same trend exposure, different driver (central-bank
policy divergence), moderate regime overlap with the equity trend bot.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

from typing import Optional

from framework import cli, data
from framework.brokers import Order, broker_for
from strategies.trend import compute_indicators
from strategies.trend import signal as trend_signal

PAIRS = ["EURUSD", "USDJPY", "GBPUSD"]
RISK_PCT = 0.01           # 1% per trade; 0.5% in high-VIX regimes (B2)
HIGH_VIX = 30.0


def signal(bars, position: dict | None = None, symbol: str = "",
           account_equity: float = 100_000.0,
           vix: float | None = None) -> Optional[Order]:
    """Delegates to the ch03 rules with the B2 risk adjustment."""
    if vix is None:
        vix = float(data.vix_series().iloc[-1])
    risk = RISK_PCT / 2 if vix > HIGH_VIX else RISK_PCT
    return trend_signal(bars, position=position, symbol=symbol,
                        account_equity=account_equity, risk_pct=risk)


def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser("strategies.bench.fx_trend",
                              "Bench B2: Donchian trend on FX majors via IBKR.")
    parser.add_argument("--pairs", default=",".join(PAIRS))
    args = parser.parse_args(argv)
    cli.banner("bench: FX trend (Appendix B2)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live
    for pair in [p.strip().upper() for p in args.pairs.split(",") if p.strip()]:
        bars = compute_indicators(data.get_bars(pair).tail(250))
        order = signal(bars, symbol=pair)
        if order is not None:
            broker_for(pair, paper=paper).place_order(pair, order.qty, order.side, "market")
        else:
            print(f"[fx-trend] {pair}: no signal "
                  f"(close {bars['close'].iloc[-1]:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
