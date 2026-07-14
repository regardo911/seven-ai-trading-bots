"""The default paths never touch the network (hard requirement §5.1)."""

import socket

import pandas as pd
import pytest

from framework import claude, data, discord
from framework.brokers import AlpacaBroker
from strategies import trend


@pytest.fixture()
def no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("network access attempted in the offline path")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_offline_stack_makes_no_connections(no_network):
    assert claude.classify("Reply with the single word PASS.") == "PASS"
    assert discord.notify("offline check") is None
    broker = AlpacaBroker(paper=True)
    broker.place_order("SPY", 1, "buy")
    bars = trend.compute_indicators(data.get_bars("SPY").tail(250))
    trend.signal(bars, symbol="SPY")
    assert data.iv_percentile("SPY", pd.Timestamp("2025-05-05")) >= 0
