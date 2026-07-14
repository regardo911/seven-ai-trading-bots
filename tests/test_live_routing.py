"""Armed-live routing — the positive live-path proof (ch02 / ch12 deployment).

With ``framework.live_mode`` armed *in source*, ``broker_for(..., paper=False)``
must route a real order into the asset-class SDK. These tests inject FAKE
``alpaca`` / ``ib_async`` / ``ccxt`` modules and dummy credentials — no real
SDK, no network, no live account — and assert the order reaches the live
adapter and returns the SDK's order id. The safety gates are tested too: with
no arming, the live path is unreachable, and a bare ``--live`` is refused.
"""

from __future__ import annotations

import argparse
import sys
import types

import pytest

import framework
from framework import cli
from framework.brokers import AlpacaBroker, CryptoBroker, IBKRBroker, broker_for

CONFIRM = "I_HAVE_REVIEWED_THIS"


# ------------------------- fake SDKs (no network) --------------------------

@pytest.fixture()
def fake_alpaca(monkeypatch):
    """Install a fake ``alpaca`` package tree + dummy credentials."""
    recorder: dict = {}
    root = types.ModuleType("alpaca")
    trading = types.ModuleType("alpaca.trading")
    enums = types.ModuleType("alpaca.trading.enums")
    requests = types.ModuleType("alpaca.trading.requests")

    class _Order:
        id = "ALP-LIVE-1"

    class TradingClient:
        def __init__(self, key, secret, paper=False):
            recorder["client"] = {"key": key, "secret": secret, "paper": paper}

        def submit_order(self, req):
            recorder["submitted"] = req
            return _Order()

    class OrderSide:
        BUY, SELL = "buy", "sell"

    class TimeInForce:
        DAY = "day"

    class MarketOrderRequest:
        def __init__(self, symbol, qty, side, time_in_force):
            self.symbol, self.qty, self.side = symbol, qty, side

    trading.TradingClient = TradingClient
    enums.OrderSide, enums.TimeInForce = OrderSide, TimeInForce
    requests.MarketOrderRequest = MarketOrderRequest
    root.trading = trading
    for name, mod in {
        "alpaca": root, "alpaca.trading": trading,
        "alpaca.trading.enums": enums, "alpaca.trading.requests": requests,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setenv("ALPACA_API_KEY", "dummy-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "dummy-secret")
    return recorder


@pytest.fixture()
def fake_ib_async(monkeypatch):
    """Install a fake ``ib_async`` module (records the contract + order)."""
    recorder: dict = {}
    mod = types.ModuleType("ib_async")

    class _Placed:
        def __init__(self, order):
            self.order = order

    class IB:
        def connect(self, host, port, clientId):
            recorder["connect"] = {"host": host, "port": port, "clientId": clientId}

        def qualifyContracts(self, contract):
            recorder.setdefault("qualified", []).append(contract)

        def placeOrder(self, contract, order):
            recorder["placed"] = {"contract": contract, "order": order}
            return _Placed(order)

        def sleep(self, _seconds):
            pass

        def disconnect(self):
            recorder["disconnected"] = True

    class MarketOrder:
        def __init__(self, action, qty):
            self.action, self.totalQuantity, self.orderId = action, qty, 42

    class Forex:
        def __init__(self, pair):
            self.pair, self.kind = pair, "forex"

    class Future:
        def __init__(self, symbol, exchange=""):
            self.symbol, self.exchange, self.kind = symbol, exchange, "future"

    mod.IB, mod.MarketOrder, mod.Forex, mod.Future = IB, MarketOrder, Forex, Future
    monkeypatch.setitem(sys.modules, "ib_async", mod)
    return recorder


@pytest.fixture()
def fake_ccxt(monkeypatch):
    """Install a fake ``ccxt`` module + dummy credentials."""
    recorder: dict = {}
    mod = types.ModuleType("ccxt")

    class _Exchange:
        def __init__(self, config):
            recorder["config"] = config

        def create_order(self, symbol, order_type, side, qty):
            recorder["order"] = {"symbol": symbol, "type": order_type,
                                 "side": side, "qty": qty}
            return {"id": "CCXT-LIVE-1", "symbol": symbol}

    mod.binance = _Exchange
    monkeypatch.setitem(sys.modules, "ccxt", mod)
    monkeypatch.setenv("BINANCE_API_KEY", "dummy-key")
    monkeypatch.setenv("BINANCE_SECRET_KEY", "dummy-secret")
    return recorder


# ----------------------------- positive tests ------------------------------

def test_armed_alpaca_routes_a_live_equity_order(fake_alpaca):
    framework.set_live_mode(True, confirm=CONFIRM)
    broker = broker_for("SPY", paper=False)
    assert isinstance(broker, AlpacaBroker) and broker.paper is False
    fill = broker.place_order("SPY", 3, "buy")
    assert fill["id"] == "ALP-LIVE-1"          # came back from the (fake) SDK
    assert fake_alpaca["submitted"].symbol == "SPY"
    assert fake_alpaca["client"]["paper"] is False  # live endpoint, not paper


def test_armed_ibkr_routes_a_live_future_order(fake_ib_async):
    framework.set_live_mode(True, confirm=CONFIRM)
    broker = broker_for("ES", paper=False)
    assert isinstance(broker, IBKRBroker) and broker.paper is False
    fill = broker.place_order("ES", 1, "buy")
    assert fill["id"] == "42"                  # trade.order.orderId from the fake
    assert fake_ib_async["placed"]["contract"].kind == "future"
    assert fake_ib_async["placed"]["contract"].exchange == "CME"
    assert fake_ib_async["placed"]["order"].action == "BUY"
    assert fake_ib_async["disconnected"] is True  # connection always closed


def test_armed_ibkr_routes_fx_as_forex(fake_ib_async):
    framework.set_live_mode(True, confirm=CONFIRM)
    broker_for("EURUSD", paper=False).place_order("EURUSD", 1000, "sell")
    assert fake_ib_async["placed"]["contract"].kind == "forex"
    assert fake_ib_async["placed"]["order"].action == "SELL"


def test_armed_crypto_routes_a_live_order(fake_ccxt):
    framework.set_live_mode(True, confirm=CONFIRM)
    broker = broker_for("BTC", paper=False)
    assert isinstance(broker, CryptoBroker) and broker.paper is False
    order = broker.create_order("BTC/USDT:USDT", "market", "buy", 0.5)
    assert order["id"] == "CCXT-LIVE-1"
    assert fake_ccxt["order"]["side"] == "buy"
    assert fake_ccxt["config"]["apiKey"] == "dummy-key"  # creds read from env


# ------------------------------ safety gates -------------------------------

def test_live_broker_is_unreachable_without_arming():
    """The ch02 gate: paper=False cannot even construct a broker unless armed."""
    assert framework.live_mode is False
    with pytest.raises(RuntimeError, match="live_mode is False"):
        broker_for("SPY", paper=False)


def test_guard_live_threads_the_paper_flag():
    """The wiring the strategy CLIs rely on: guard_live -> paper flag."""
    assert cli.guard_live(argparse.Namespace(live=False)) is True   # paper
    framework.set_live_mode(True, confirm=CONFIRM)
    assert cli.guard_live(argparse.Namespace(live=True)) is False   # armed -> live


def test_unarmed_live_flag_exits(capsys):
    """A bare --live with no arming prints the warning and exits (ch02)."""
    with pytest.raises(SystemExit) as exc:
        cli.guard_live(argparse.Namespace(live=True))
    assert exc.value.code == 2
    assert "live_mode is False" in capsys.readouterr().out
