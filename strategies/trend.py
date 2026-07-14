"""Strategy 1 — Trend following on equities and futures (Chapter 3).

Donchian-20 breakout entries, a 200-day SMA regime filter, and a 3x ATR(14)
trailing stop, on SPY / QQQ / ES / GC. Claude is OFFLINE at runtime for this
strategy — the rules are mechanical (ch06 placement table).

Note on the Donchian window: the chapter's prose defines the entry against the
highest level of the *prior* 20 trading days, so the rolling max is shifted by
one bar here (a same-bar close can never exceed a rolling max that includes
its own high). See ERRATA.md.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from framework import cli, data, discord
from framework.brokers import Order, broker_for

INSTRUMENTS = ["SPY", "QQQ", "ES", "GC"]
ATR_MULTIPLIER = 3.0        # ch03: "Use 3x ATR(14), not 1.8 to 2.5x."
DONCHIAN_WINDOW = 20
SMA_WINDOW = 200
DEFAULT_RISK_PCT = 0.01     # 1% of account equity per trade (ch03 risk framing)


def compute_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    """Five lines of pandas — no indicator library needed (ch03)."""
    bars = bars.copy()
    # Donchian high over the PRIOR 20 days (see module docstring).
    bars["donchian_high_20"] = bars["high"].rolling(DONCHIAN_WINDOW).max().shift(1)
    bars["sma_200"] = bars["close"].rolling(SMA_WINDOW).mean()
    high_low = bars["high"] - bars["low"]
    high_close = (bars["high"] - bars["close"].shift()).abs()
    low_close = (bars["low"] - bars["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    bars["atr_14"] = true_range.rolling(14).mean()
    return bars


def atr(bars: pd.DataFrame, window: int = 14) -> float:
    """Latest ATR reading (shared with the news bot's stop sizing, ch06)."""
    high_low = bars["high"] - bars["low"]
    high_close = (bars["high"] - bars["close"].shift()).abs()
    low_close = (bars["low"] - bars["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return float(true_range.rolling(window).mean().iloc[-1])


def is_entry(bar: pd.Series) -> bool:
    """ch03 Rule 1 + Rule 2: 20-day breakout AND above the 200-day SMA."""
    return bool(
        bar["close"] > bar["donchian_high_20"] and bar["close"] > bar["sma_200"]
    )


def update_trailing_stop(position: dict, current_bar: pd.Series) -> str:
    """ch03 Rule 3, verbatim mechanics: the stop ratchets up, never down."""
    new_high = max(position["high_water"], current_bar["high"])
    new_stop = new_high - ATR_MULTIPLIER * current_bar["atr_14"]
    position["high_water"] = new_high
    position["stop"] = max(position["stop"], new_stop)  # never lower the stop
    if current_bar["low"] <= position["stop"]:
        return "EXIT"
    return "HOLD"


def position_size(account_equity: float, stop_distance: float,
                  risk_pct: float = DEFAULT_RISK_PCT) -> int:
    """The formula the book says to memorize: risk dollars / stop distance."""
    if stop_distance <= 0:
        return 0
    return int((account_equity * risk_pct) / stop_distance)


def signal(bars: pd.DataFrame, position: dict | None = None, symbol: str = "",
           account_equity: float = 100_000.0,
           risk_pct: float = DEFAULT_RISK_PCT) -> Optional[Order]:
    """The strategy-module contract (ch03 BUILD STEP 1): one function, one
    Order or None. Entry when flat; trailing-stop exit when in a position."""
    if len(bars) < SMA_WINDOW:
        return None  # the 200-day SMA needs its warmup (ch03)
    if "donchian_high_20" not in bars.columns:
        bars = compute_indicators(bars)
    bar = bars.iloc[-1]

    if position is not None and position.get("qty", 0) > 0:
        if update_trailing_stop(position, bar) == "EXIT":
            return Order(symbol, position["qty"], "sell",
                         meta={"reason": "trailing_stop"})
        return None

    if is_entry(bar):
        stop_distance = ATR_MULTIPLIER * float(bar["atr_14"])
        qty = position_size(account_equity, stop_distance, risk_pct)
        if qty < 1:
            return None
        return Order(symbol, qty, "buy", meta={
            "stop": float(bar["close"]) - stop_distance,
            "stop_distance": stop_distance,
            "entry": float(bar["close"]),
        })
    return None


# ------------------------------- CLI (A3) ----------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser(
        "strategies.trend",
        "Trend-following bot (ch03): Donchian-20 + 200-SMA + 3x ATR(14) trail.",
    )
    parser.add_argument("--instruments", default=",".join(INSTRUMENTS))
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--regime-breakdown", action="store_true")
    args = parser.parse_args(argv)
    cli.banner("trend bot (ch03)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live

    if args.backtest:
        from backtest import trend as trend_backtest

        result = trend_backtest.run(write=True)
        trend_backtest.print_report(result, regime=args.regime_breakdown)
        return 0

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    for symbol in instruments:
        broker = broker_for(symbol, paper=paper)  # equities -> Alpaca; ES/GC -> IBKR
        bars = compute_indicators(
            data.get_bars(symbol, live=args.live_data).tail(250)
        )
        sig = signal(bars, symbol=symbol)
        if sig is not None:
            broker.place_order(symbol, sig.qty, sig.side, "market")
            discord.notify(f"trend: {sig.side} {sig.qty} {symbol} "
                           f"(stop {sig.meta['stop']:.2f})")
        else:
            print(f"[trend] {symbol}: no signal "
                  f"(close {bars['close'].iloc[-1]:.2f}, "
                  f"20d-high {bars['donchian_high_20'].iloc[-1]:.2f}, "
                  f"200-SMA {bars['sma_200'].iloc[-1]:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
