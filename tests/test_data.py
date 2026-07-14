"""Synthetic data layer: deterministic, regime-aware, offline."""

import pandas as pd

from framework import data


def test_bars_deterministic_and_shaped():
    a = data.get_bars("SPY")
    b = data.get_bars("SPY")
    assert a.equals(b)
    assert list(a.columns) == ["open", "high", "low", "close", "volume"]
    assert (a["high"] >= a["low"]).all()
    assert (a["close"] > 0).all()


def test_derived_pair_tracks_driver():
    ko = data.get_bars("KO")["close"]
    pep = data.get_bars("PEP")["close"]
    corr = ko.corr(pep)
    assert corr > 0.8  # PEP is built as 20 + 1.3*KO + stationary noise


def test_vix_and_regimes():
    vix = data.vix_series()
    crisis = vix.loc["2020-03-01":"2020-05-30"]
    calm = vix.loc["2019-01-01":"2019-12-31"]
    assert crisis.mean() > calm.mean()
    assert data.regime_of(pd.Timestamp("2022-06-15")) == "bear"
    assert data.regime_of(pd.Timestamp("2025-02-01")) == "current"


def test_funding_history_and_snapshot():
    hist = data.get_funding_history("binance", "BTC", months=24)
    assert {"fundingRate", "markPrice", "indexPrice"} <= set(hist.columns)
    snap = data.get_funding_snapshot("binance", "BTC")
    assert snap["symbol"] == "BTC/USDT:USDT"
    assert "nextFundingTime" in snap
    # the deterministic June-2025 inversion (exercises the ch08 breaker)
    inversion = hist.loc["2025-06-10":"2025-06-12", "fundingRate"]
    assert (inversion < 0).any()


def test_iv_percentile_bounded_and_deterministic():
    ts = pd.Timestamp("2025-03-03")
    v1 = data.iv_percentile("SPY", ts)
    assert 0 <= v1 < 100
    assert v1 == data.iv_percentile("SPY", ts)


def test_normalize():
    assert data.normalize("BTC/USDT:USDT") == "BTC"
    assert data.normalize("^VIX") == "VIX"
    assert data.normalize("EUR/USD") == "EURUSD"
