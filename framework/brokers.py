"""Broker abstraction — pick brokers per asset class, not per book (ch02).

Three concrete brokers behind one interface: ``AlpacaBroker`` (US equities &
options), ``IBKRBroker`` (futures & FX), ``CryptoBroker`` (ccxt-style crypto).
In paper mode — the default, and the only mode this repository ever selects on
its own — orders fill against the synthetic data layer and are logged; **no
broker endpoint is ever called**. Live mode additionally requires
``framework.live_mode`` (the ch02 code-change confirmation) plus real
credentials plus the optional broker SDKs.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

import framework
from framework import data


@dataclass
class Order:
    """A single order intent as the strategies emit it (ch03-ch09)."""

    symbol: str
    qty: float
    side: str  # "buy" | "sell"
    type: str = "market"
    meta: dict = field(default_factory=dict)


class PaperLedger:
    """Simulated account: $100,000 paper cash, positions, and a fill log."""

    def __init__(self, cash: float = 100_000.0) -> None:
        self.start_cash = cash
        self.cash = cash
        self.positions: dict[str, dict] = {}
        self.fills: list[dict] = []

    def price(self, symbol: str, asof: pd.Timestamp | None = None) -> float:
        bars = data.get_bars(symbol)
        if asof is not None:
            bars = bars.loc[bars.index <= pd.Timestamp(asof)]
        return float(bars["close"].iloc[-1])

    def execute(self, broker: str, symbol: str, qty: float, side: str,
                order_type: str = "market", price: float | None = None,
                asof: pd.Timestamp | None = None) -> dict:
        px = price if price is not None else self.price(symbol, asof)
        signed = qty if side == "buy" else -qty
        pos = self.positions.setdefault(symbol, {"qty": 0.0, "avg": px})
        new_qty = pos["qty"] + signed
        if signed > 0 and pos["qty"] >= 0:  # extending a long
            total_cost = pos["avg"] * pos["qty"] + px * signed
            pos["avg"] = total_cost / new_qty if new_qty else px
        pos["qty"] = new_qty
        self.cash -= signed * px
        fill = {"broker": broker, "symbol": symbol, "qty": qty, "side": side,
                "type": order_type, "price": px}
        self.fills.append(fill)
        return fill

    def portfolio_value(self, asof: pd.Timestamp | None = None) -> float:
        value = self.cash
        for symbol, pos in self.positions.items():
            if pos["qty"]:
                value += pos["qty"] * self.price(symbol, asof)
        return value


class Broker(ABC):
    """Abstract broker (ch02): strategies say "buy 100 SPY" without knowing
    whether the order routes to Alpaca or Interactive Brokers."""

    name = "broker"

    def __init__(self, paper: bool = True, ledger: PaperLedger | None = None) -> None:
        if not paper and not framework.live_mode:
            raise RuntimeError(
                "live broker requested but framework.live_mode is False - "
                'call framework.set_live_mode(True, confirm="I_HAVE_REVIEWED_THIS") '
                "in source first (ch02 safety rule)"
            )
        self.paper = paper
        self.ledger = ledger if ledger is not None else PaperLedger()

    # -- shared paper implementations ------------------------------------
    def get_account_info(self) -> dict:
        cash = self.ledger.cash
        return {
            "account_number": self._account_number(),
            "cash": f"{cash:.2f}",
            "buying_power": f"{cash * 2:.2f}",
            "portfolio_value": f"{self.ledger.portfolio_value():.2f}",
            "pattern_day_trader": False,
        }

    def get_positions(self) -> list[dict]:
        return [
            {"symbol": s, "qty": p["qty"], "avg_entry_price": p["avg"]}
            for s, p in self.ledger.positions.items() if p["qty"]
        ]

    def get_bars(self, symbols, lookback_days: int = 250,
                 timeframe: str = "1d", live: bool = False):
        """Daily bars keyed by symbol (the ch03 runner indexes ``bars[symbol]``)."""
        if isinstance(symbols, str):
            return data.get_bars(symbols, live=live).tail(lookback_days)
        return {s: data.get_bars(s, live=live).tail(lookback_days) for s in symbols}

    def place_order(self, symbol: str, qty: float, side: str,
                    type: str = "market") -> dict:  # noqa: A002 - book signature
        """Paper mode logs a simulated fill; live re-checks every safety gate."""
        if self.paper or not framework.live_mode:
            fill = self.ledger.execute(self.name, symbol, qty, side, type)
            print(f"[paper:{self.name}] {side} {round(qty, 4):g} {symbol} "
                  f"@ {fill['price']:.2f}")
            return fill
        return self._place_live_order(symbol, qty, side, type)

    def _account_number(self) -> str:
        return "PA1234567" if self.paper else "LIVE"

    @abstractmethod
    def _place_live_order(self, symbol: str, qty: float, side: str,
                          order_type: str) -> dict:  # pragma: no cover
        ...


class AlpacaBroker(Broker):
    """US equities & options. Live path uses ``alpaca-py`` (NOT the legacy
    ``alpaca-trade-api`` — ch02's install trap)."""

    name = "alpaca"

    def _place_live_order(self, symbol, qty, side, order_type):
        from alpaca.trading import TradingClient  # lazy: optional extra

        client = TradingClient(
            os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=False
        )
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        req = MarketOrderRequest(
            symbol=symbol, qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)
        return {"broker": self.name, "symbol": symbol, "qty": qty, "side": side,
                "type": order_type, "id": str(order.id)}


class IBKRBroker(Broker):
    """Futures & FX via Interactive Brokers. Use ``ib_async``, never the
    archived ``ib_insync`` (ch02). Live orders need IB Gateway/TWS running on
    port 7497 (paper) or 7496 (live) — Appendix A5."""

    name = "ibkr"

    #: symbol -> IBKR listing exchange for the futures routed here (ch02).
    _FUTURES_EXCHANGE = {"ES": "CME", "GC": "COMEX"}

    def _live_contract(self, symbol: str):
        """Build the ``ib_async`` contract for a routed symbol: FX majors become
        a ``Forex`` contract, ES/GC a ``Future`` that ``qualifyContracts``
        resolves to the front month. Confirm the contract month and listing
        exchange for YOUR instrument before trading live (Appendix A5)."""
        from ib_async import Forex, Future  # lazy: optional [brokers] extra

        sym = data.normalize(symbol)
        if sym in {"EURUSD", "USDJPY", "GBPUSD"}:
            return Forex(sym)
        return Future(sym, exchange=self._FUTURES_EXCHANGE.get(sym, "CME"))

    def _place_live_order(self, symbol, qty, side, order_type):
        from ib_async import IB, MarketOrder  # lazy: optional [brokers] extra

        ib = IB()
        ib.connect(
            os.environ.get("IBKR_HOST", "127.0.0.1"),
            int(os.environ.get("IBKR_PORT", "7496")),  # 7496 live / 7497 paper
            clientId=int(os.environ.get("IBKR_CLIENT_ID", "1")),
        )
        try:
            contract = self._live_contract(symbol)
            ib.qualifyContracts(contract)
            trade = ib.placeOrder(
                contract, MarketOrder("BUY" if side == "buy" else "SELL", qty)
            )
            ib.sleep(1)  # let the order status settle on the ib_async event loop
            return {"broker": self.name, "symbol": symbol, "qty": qty,
                    "side": side, "type": order_type,
                    "id": str(getattr(trade.order, "orderId", ""))}
        finally:
            ib.disconnect()


class CryptoBroker(Broker):
    """Crypto via a ccxt-shaped interface (ch08). Paper mode answers
    ``fetch_ticker`` / ``fetch_funding_rate`` / ``create_order`` from the
    synthetic data layer using the unified ccxt method names."""

    name = "crypto"

    def __init__(self, exchange: str = "binance", paper: bool = True,
                 ledger: PaperLedger | None = None) -> None:
        super().__init__(paper=paper, ledger=ledger)
        self.exchange = exchange
        self.name = exchange

    def fetch_ticker(self, symbol: str) -> dict:
        return {"symbol": symbol, "last": self.ledger.price(symbol)}

    def fetch_funding_rate(self, symbol: str,
                           asof: pd.Timestamp | None = None) -> dict:
        return data.get_funding_snapshot(self.exchange, symbol, asof=asof)

    def create_order(self, symbol: str, type: str, side: str, amount: float,  # noqa: A002
                     price: float | None = None) -> dict:
        """ccxt unified signature: create_order(symbol, type, side, amount, price)."""
        if self.paper or not framework.live_mode:
            fill = self.ledger.execute(self.name, symbol, amount, side, type, price)
            print(f"[paper:{self.name}] {side} {round(amount, 4):g} {symbol} "
                  f"@ {fill['price']:.2f}")
            return fill
        return self._place_live_order(symbol, amount, side, type)

    def _place_live_order(self, symbol, qty, side, order_type):
        import ccxt  # lazy: optional extra

        exchange_cls = getattr(ccxt, self.exchange)
        client = exchange_cls({
            "apiKey": os.environ[f"{self.exchange.upper()}_API_KEY"],
            "secret": os.environ[f"{self.exchange.upper()}_SECRET_KEY"],
            "enableRateLimit": True,  # ch08: let ccxt manage throttling
        })
        order = client.create_order(symbol, order_type, side, qty)
        return {"broker": self.name, "symbol": symbol, "qty": qty, "side": side,
                "type": order_type, "id": order.get("id")}


# ------------------------- asset-class routing (ch02) -----------------------

_FUTURES_FX = {"ES", "GC", "EURUSD", "USDJPY", "GBPUSD"}
_CRYPTO = {"BTC", "ETH", "SOL"}

_paper_alpaca: AlpacaBroker | None = None
_paper_ibkr: IBKRBroker | None = None
_paper_crypto: dict[str, CryptoBroker] = {}


def broker_for(symbol: str, exchange: str = "binance", paper: bool = True) -> Broker:
    """Route a symbol to its asset-class broker (ch02 routing).

    ``paper`` defaults to True — this repository never selects live on its own.
    A live broker (``paper=False``) is only constructible when
    ``framework.live_mode`` is True (the ch02 gate in ``Broker.__init__``), so
    the strategy CLIs thread ``paper=cli.guard_live(args)`` through here: an
    *armed* ``--live`` run (``set_live_mode`` called in source) routes real
    orders, while an unarmed ``--live`` has already printed the warning and
    exited. Paper brokers are shared singletons; live brokers are built fresh
    per call so no armed state is ever cached across a run.
    """
    global _paper_alpaca, _paper_ibkr
    sym = data.normalize(symbol)
    if sym in _CRYPTO:
        if not paper:
            return CryptoBroker(exchange=exchange, paper=False)
        if exchange not in _paper_crypto:
            _paper_crypto[exchange] = CryptoBroker(exchange=exchange, paper=True)
        return _paper_crypto[exchange]
    if sym in _FUTURES_FX:
        if not paper:
            return IBKRBroker(paper=False)
        if _paper_ibkr is None:
            _paper_ibkr = IBKRBroker(paper=True)
        return _paper_ibkr
    if not paper:
        return AlpacaBroker(paper=False)
    if _paper_alpaca is None:
        _paper_alpaca = AlpacaBroker(paper=True)
    return _paper_alpaca
