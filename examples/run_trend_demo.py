"""One-strategy demo: the ch03 runner pattern, verbatim wiring.

Scans the four trend instruments in paper mode against synthetic bars and
routes any signal through the broker abstraction (equities -> Alpaca,
ES/GC -> IBKR). Runs offline with zero API keys.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from framework import data, discord  # noqa: E402
from framework.brokers import broker_for  # noqa: E402
from strategies import trend  # noqa: E402

for symbol in ["SPY", "QQQ", "ES", "GC"]:
    broker = broker_for(symbol)
    bars = trend.compute_indicators(data.get_bars(symbol).tail(250))
    sig = trend.signal(bars, symbol=symbol)
    if sig is not None:
        broker.place_order(symbol, sig.qty, sig.side, "market")
        discord.notify(f"trend: {sig.side} {sig.qty} {symbol}")
    else:
        print(f"{symbol}: no signal today (that's normal - ch03 failure mode 1: "
              "the absence of signals is the signal)")
