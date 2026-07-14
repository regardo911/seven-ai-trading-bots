"""ch04: cointegration scan, Z-score, time-stop, hedge sizing."""

from framework import data
from strategies import pairs


def test_scanner_finds_engineered_pair():
    closes = {s: data.get_bars(s)["close"] for s in ("KO", "PEP")}
    found = pairs.scan_pairs(closes, basket=[("KO", "PEP")])
    assert found, "KO/PEP is constructed cointegrated; scanner must find it"
    cand = found[0]
    assert cand["p_value"] < 0.05
    assert 1.0 < cand["hedge_ratio"] < 1.6  # built with beta 1.30


def test_zscore_is_standardized():
    closes = {s: data.get_bars(s)["close"] for s in ("KO", "PEP")}
    z = pairs.zscore(closes["KO"], closes["PEP"], 1.30).dropna()
    assert abs(z.mean()) < 0.5
    assert 0.5 < z.std() < 2.0


def test_should_close_time_stop_and_zero_cross():
    position = {"entry_z": 2.4}
    assert pairs.should_close(position, z_today=2.1, days_held=5) is None
    assert pairs.should_close(position, z_today=2.1, days_held=20) == "time_stop"
    assert pairs.should_close(position, z_today=-0.2,
                              days_held=3) == "z_crossed_zero"


def test_vix_filter_blocks_new_entries():
    bars = {s: data.get_bars(s) for s in ("KO", "PEP")}
    orders = pairs.signal(bars, vix=35.0, basket=[("KO", "PEP")])
    assert orders == []
