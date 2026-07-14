"""Broker abstraction: paper fills, A7 account shape, asset-class routing."""

from framework.brokers import AlpacaBroker, CryptoBroker, IBKRBroker, PaperLedger, broker_for


def test_account_info_matches_appendix_a7_shape():
    broker = AlpacaBroker(paper=True)
    info = broker.get_account_info()
    assert info["account_number"] == "PA1234567"
    assert info["cash"] == "100000.00"
    assert info["buying_power"] == "200000.00"
    assert info["pattern_day_trader"] is False


def test_paper_order_fills_and_updates_positions():
    broker = AlpacaBroker(paper=True, ledger=PaperLedger())
    fill = broker.place_order("SPY", 10, "buy")
    assert fill["symbol"] == "SPY" and fill["qty"] == 10
    positions = broker.get_positions()
    assert positions[0]["symbol"] == "SPY" and positions[0]["qty"] == 10
    broker.place_order("SPY", 10, "sell")
    assert broker.get_positions() == []


def test_router_by_asset_class():
    assert isinstance(broker_for("SPY"), AlpacaBroker)
    assert isinstance(broker_for("ES"), IBKRBroker)
    assert isinstance(broker_for("GC"), IBKRBroker)
    assert isinstance(broker_for("EURUSD"), IBKRBroker)
    assert isinstance(broker_for("BTC"), CryptoBroker)


def test_get_bars_dict_keyed_by_symbol():
    bars = AlpacaBroker(paper=True).get_bars(["SPY", "QQQ"], lookback_days=250)
    assert set(bars) == {"SPY", "QQQ"}
    assert len(bars["SPY"]) == 250
    assert {"open", "high", "low", "close", "volume"} <= set(bars["SPY"].columns)


def test_crypto_broker_ccxt_shaped_methods():
    broker = CryptoBroker(exchange="binance", paper=True)
    ticker = broker.fetch_ticker("BTC")
    assert ticker["last"] > 0
    funding = broker.fetch_funding_rate("BTC/USDT:USDT")
    assert {"fundingRate", "markPrice", "indexPrice", "nextFundingTime"} <= set(funding)
