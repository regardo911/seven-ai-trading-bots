"""Deterministic synthetic market-data layer (offline-first).

This module is the reason the whole repository runs with **zero API keys and
zero network access**. It generates seeded, regime-aware synthetic OHLCV bars,
a synthetic VIX, synthetic perp funding-rate histories, and deterministic
IV-percentile readings, and it loads the committed text fixtures
(headlines / transcripts / flow events) under ``data/fixtures/``.

The five named regime windows mirror the book's backtest requirement (ch03,
ch10): low-vol 2018-2019, crisis 2020, mania 2021, bear 2022, recovery
2023-2024, plus "current" 2025.

    !! Everything produced here is SYNTHETIC SAMPLE DATA. Any backtest number
    !! computed on it is illustrative of the mechanics only - it is not real,
    !! not historical, and not a forecast. See DISCLAIMER.md.

Passing ``live=True`` (wired to the ``--live-data`` CLI flag) upgrades
``get_bars`` to real daily bars via ``yfinance`` *if it is installed* — the
default path never touches the network.
"""

from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

SIM_START = "2018-01-02"
SIM_END = "2025-12-31"

#: Chapter 3 / Chapter 10 named regime windows (plus "current").
REGIMES: dict[str, tuple[str, str]] = {
    "low_vol": ("2018-01-01", "2019-12-31"),
    "crisis": ("2020-01-01", "2020-12-31"),
    "mania": ("2021-01-01", "2021-12-31"),
    "bear": ("2022-01-01", "2022-12-31"),
    "recovery": ("2023-01-01", "2024-12-31"),
    "current": ("2025-01-01", "2025-12-31"),
}

# (annualized drift, annualized vol) per regime, per asset class.
_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "equity_index": {
        "low_vol": (0.10, 0.12), "crisis": (-0.05, 0.34), "mania": (0.22, 0.15),
        "bear": (-0.18, 0.24), "recovery": (0.15, 0.12), "current": (0.09, 0.13),
    },
    "equity_single": {
        "low_vol": (0.09, 0.18), "crisis": (-0.02, 0.42), "mania": (0.25, 0.24),
        "bear": (-0.22, 0.32), "recovery": (0.16, 0.20), "current": (0.10, 0.19),
    },
    "midcap": {
        "low_vol": (0.07, 0.24), "crisis": (-0.10, 0.52), "mania": (0.30, 0.32),
        "bear": (-0.28, 0.38), "recovery": (0.14, 0.26), "current": (0.08, 0.24),
    },
    "gold": {
        "low_vol": (0.05, 0.11), "crisis": (0.20, 0.18), "mania": (0.00, 0.14),
        "bear": (0.02, 0.16), "recovery": (0.12, 0.12), "current": (0.10, 0.12),
    },
    "crypto": {
        "low_vol": (-0.10, 0.55), "crisis": (0.30, 0.85), "mania": (1.10, 0.80),
        "bear": (-0.60, 0.75), "recovery": (0.55, 0.55), "current": (0.25, 0.45),
    },
    "fx": {
        "low_vol": (0.01, 0.07), "crisis": (0.00, 0.11), "mania": (0.02, 0.07),
        "bear": (-0.03, 0.09), "recovery": (0.02, 0.07), "current": (0.01, 0.07),
    },
}

# symbol -> (base price, asset class)
_SYMBOLS: dict[str, tuple[float, str]] = {
    "SPY": (250.0, "equity_index"), "QQQ": (150.0, "equity_index"),
    "ES": (2500.0, "equity_index"), "SPX": (2500.0, "equity_index"),
    "GC": (1300.0, "gold"), "GLD": (125.0, "gold"),
    "KO": (45.0, "equity_single"), "XLE": (70.0, "equity_single"),
    "MSFT": (90.0, "equity_single"), "GOOGL": (55.0, "equity_single"),
    "AAPL": (45.0, "equity_single"),
    "BTC": (9000.0, "crypto"), "ETH": (450.0, "crypto"), "SOL": (150.0, "crypto"),
    "EURUSD": (1.18, "fx"), "USDJPY": (110.0, "fx"), "GBPUSD": (1.33, "fx"),
    # 11 GICS sector ETFs (Appendix B3)
    "XLK": (65.0, "equity_index"), "XLV": (85.0, "equity_index"),
    "XLF": (28.0, "equity_index"), "XLY": (100.0, "equity_index"),
    "XLP": (55.0, "equity_index"), "XLI": (75.0, "equity_index"),
    "XLB": (60.0, "equity_index"), "XLU": (52.0, "equity_index"),
    "XLRE": (33.0, "equity_index"), "XLC": (45.0, "equity_index"),
    # synthetic mid-caps for the PEAD bot (fixtures reference these tickers)
    "ACME": (28.0, "midcap"), "BOLT": (42.0, "midcap"), "CRUX": (19.0, "midcap"),
    "DUNE": (63.0, "midcap"), "EPIC": (35.0, "midcap"), "FLUX": (51.0, "midcap"),
    "GRIT": (24.0, "midcap"), "HAVN": (77.0, "midcap"),
}

# Derived series guaranteed cointegrated with their driver (ch04 candidates):
# derived = intercept + beta * driver + OU(theta, sigma) stationary noise.
_DERIVED: dict[str, tuple[str, float, float, float, float]] = {
    # symbol: (driver, intercept, beta, ou_theta, ou_sigma)
    "PEP": ("KO", 20.0, 1.30, 0.06, 1.10),
    "SLV": ("GLD", 1.5, 0.115, 0.06, 0.35),
    "USO": ("XLE", 4.0, 0.60, 0.05, 1.00),
}

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures"
_BARS_CACHE: dict[str, pd.DataFrame] = {}
_VIX_CACHE: pd.Series | None = None
_FUNDING_CACHE: dict[tuple[str, str], pd.DataFrame] = {}


def normalize(symbol: str) -> str:
    """Map broker/exchange notations onto generator symbols."""
    s = symbol.upper().strip()
    if s.startswith("^"):
        s = s[1:]
    for suffix in ("/USDT:USDT", "/USDT", "/USD:USD"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s.replace("/", "")


def _seed(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode())


def _dates() -> pd.DatetimeIndex:
    return pd.bdate_range(SIM_START, SIM_END)


def regime_of(ts: pd.Timestamp) -> str:
    for name, (start, end) in REGIMES.items():
        if pd.Timestamp(start) <= ts <= pd.Timestamp(end):
            return name
    return "current"


def _drift_offset(symbol: str) -> float:
    """Small deterministic per-symbol drift tilt so cross-sections disperse
    (gives the Appendix B3 momentum rotation something real to rank)."""
    h = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
    return ((h % 1000) / 1000.0 - 0.5) * 0.12  # +/- 6% annualized


def _synthesize(symbol: str) -> pd.DataFrame:
    base, klass = _SYMBOLS[symbol]
    profile = _PROFILES[klass]
    dates = _dates()
    rng = np.random.default_rng(_seed("bars", symbol))
    z = rng.standard_normal((len(dates), 4))
    tilt = _drift_offset(symbol)

    rets = np.empty(len(dates))
    sig_d = np.empty(len(dates))
    for i, ts in enumerate(dates):
        mu, sigma = profile[regime_of(ts)]
        sig_d[i] = sigma / np.sqrt(252.0)
        rets[i] = (mu + tilt) / 252.0 + sig_d[i] * z[i, 0]

    close = base * np.cumprod(1.0 + rets)
    return _ohlcv_around(close, sig_d, z, dates, rng)


def _ohlcv_around(
    close: np.ndarray, sig_d: np.ndarray, z: np.ndarray,
    dates: pd.DatetimeIndex, rng: np.random.Generator,
) -> pd.DataFrame:
    prev = np.concatenate([[close[0]], close[:-1]])
    open_ = prev * (1.0 + 0.25 * sig_d * z[:, 1])
    hi = np.maximum(open_, close) * (1.0 + np.abs(z[:, 2]) * 0.45 * sig_d)
    lo = np.minimum(open_, close) * (1.0 - np.abs(z[:, 3]) * 0.45 * sig_d)
    lo = np.minimum(lo, np.minimum(open_, close))
    volume = np.exp(rng.normal(15.0, 0.35, len(dates))).astype(np.int64)
    return pd.DataFrame(
        {"open": open_, "high": hi, "low": lo, "close": close, "volume": volume},
        index=dates,
    )


def _synthesize_derived(symbol: str) -> pd.DataFrame:
    driver, intercept, beta, theta, ou_sigma = _DERIVED[symbol]
    drv = get_bars(driver)["close"].to_numpy()
    dates = _dates()
    rng = np.random.default_rng(_seed("derived", symbol))
    noise = np.zeros(len(dates))
    eps = rng.standard_normal(len(dates))
    for i in range(1, len(dates)):
        noise[i] = noise[i - 1] * (1.0 - theta) + ou_sigma * eps[i]
    close = np.maximum(intercept + beta * drv + noise, 0.5)
    sig_d = np.abs(np.diff(close, prepend=close[0])) / np.maximum(close, 1e-9) + 0.002
    z = rng.standard_normal((len(dates), 4))
    return _ohlcv_around(close, sig_d, z, dates, rng)


def get_bars(
    symbol: str, start: str | None = None, end: str | None = None, live: bool = False
) -> pd.DataFrame:
    """Daily OHLCV bars. Synthetic by default; real via yfinance when live=True."""
    sym = normalize(symbol)
    if sym == "VIX":
        vix = vix_series()
        df = pd.DataFrame(
            {"open": vix, "high": vix * 1.03, "low": vix * 0.97, "close": vix,
             "volume": 0},
        )
        return _slice(df, start, end)
    if live:  # pragma: no cover - network path, exercised manually
        import yfinance as yf

        raw = yf.Ticker(symbol).history(period="5y", interval="1d")
        raw.columns = [c.lower() for c in raw.columns]
        return raw[["open", "high", "low", "close", "volume"]]
    if sym not in _BARS_CACHE:
        if sym in _DERIVED:
            _BARS_CACHE[sym] = _synthesize_derived(sym)
        elif sym in _SYMBOLS:
            _BARS_CACHE[sym] = _synthesize(sym)
        else:
            raise KeyError(f"unknown synthetic symbol: {symbol!r}")
    return _slice(_BARS_CACHE[sym], start, end)


def _slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df
    if start is not None:
        out = out.loc[out.index >= pd.Timestamp(start)]
    if end is not None:
        out = out.loc[out.index <= pd.Timestamp(end)]
    return out.copy()


def vix_series() -> pd.Series:
    """Mean-reverting synthetic VIX with a crisis spike (drives the ch04 filter)."""
    global _VIX_CACHE
    if _VIX_CACHE is not None:
        return _VIX_CACHE
    means = {"low_vol": 14.0, "crisis": 33.0, "mania": 19.0, "bear": 27.0,
             "recovery": 15.0, "current": 16.0}
    dates = _dates()
    rng = np.random.default_rng(_seed("vix"))
    level = 14.0
    out = np.empty(len(dates))
    for i, ts in enumerate(dates):
        mu = means[regime_of(ts)]
        if ts.year == 2020 and 60 <= ts.dayofyear <= 110:  # synthetic March-2020 shock
            mu = 55.0
        level += 0.15 * (mu - level) + 1.6 * rng.standard_normal()
        level = float(np.clip(level, 9.0, 80.0))
        out[i] = level
    _VIX_CACHE = pd.Series(out, index=dates, name="VIX")
    return _VIX_CACHE


# ---------------------------------------------------------------------------
# Perp funding rates (ch08). Rates are per 8-hour settlement window.
# ---------------------------------------------------------------------------
_FUNDING_MEANS = {"low_vol": 0.00008, "crisis": 0.00004, "mania": 0.00045,
                  "bear": -0.00002, "recovery": 0.00018, "current": 0.00035}
_INSTRUMENT_SCALE = {"BTC": 1.0, "ETH": 1.2, "SOL": 1.6}


def get_funding_history(exchange: str, symbol: str, months: int = 24) -> pd.DataFrame:
    """8-hour funding-rate history ending at SIM_END (synthetic, deterministic)."""
    sym = normalize(symbol)
    key = (exchange.lower(), sym)
    if key not in _FUNDING_CACHE:
        end = pd.Timestamp(SIM_END)
        idx = pd.date_range(end=end, periods=months * 30 * 3, freq="8h")
        rng = np.random.default_rng(_seed("funding", exchange.lower(), sym))
        scale = _INSTRUMENT_SCALE.get(sym, 1.0)
        offset = -0.00003 if exchange.lower() == "bybit" else 0.0
        rates = np.empty(len(idx))
        for i, ts in enumerate(idx):
            mu = _FUNDING_MEANS[regime_of(ts)] * scale + offset
            rates[i] = mu + rng.normal(0.0, 0.00012 * scale)
        # deterministic inversion event (exercises the ch08 circuit breaker)
        inv = (idx >= pd.Timestamp("2025-06-10")) & (idx <= pd.Timestamp("2025-06-12"))
        rates[inv] -= 0.0009
        rates = np.clip(rates, -0.001, 0.0035)
        spot = get_bars(sym)["close"].reindex(idx, method="ffill").bfill()
        basis = np.clip(rates * 5.0, -0.004, 0.010)
        _FUNDING_CACHE[key] = pd.DataFrame(
            {"fundingRate": rates, "indexPrice": spot.to_numpy(),
             "markPrice": (spot * (1.0 + basis)).to_numpy()},
            index=idx,
        )
    return _FUNDING_CACHE[key].copy()


def get_funding_snapshot(exchange: str, symbol: str,
                         asof: pd.Timestamp | None = None) -> dict:
    """ccxt-shaped ``fetch_funding_rate`` result for the paper exchange."""
    hist = get_funding_history(exchange, symbol)
    if asof is not None:
        hist = hist.loc[hist.index <= pd.Timestamp(asof)]
    row = hist.iloc[-1]
    ts = hist.index[-1]
    return {
        "symbol": f"{normalize(symbol)}/USDT:USDT",
        "fundingRate": float(row["fundingRate"]),
        "markPrice": float(row["markPrice"]),
        "indexPrice": float(row["indexPrice"]),
        "nextFundingTime": int((ts + pd.Timedelta(hours=8)).timestamp() * 1000),
    }


def iv_percentile(symbol: str, date: pd.Timestamp) -> float:
    """Deterministic pseudo IV-percentile in [0, 100) (ch05/ch07 filters)."""
    digest = hashlib.md5(f"{normalize(symbol)}|{pd.Timestamp(date).date()}".encode())
    return int(digest.hexdigest()[:6], 16) % 10000 / 100.0


def intraday_move(symbol: str, ts: pd.Timestamp, hours: float) -> float:
    """Deterministic intraday return over ``hours`` (news-bot 2h/24h exits)."""
    sym = normalize(symbol)
    _, klass = _SYMBOLS.get(sym, (0.0, "equity_index"))
    sigma = _PROFILES[klass][regime_of(pd.Timestamp(ts))][1] / np.sqrt(252.0)
    rng = np.random.default_rng(_seed("intraday", sym, str(pd.Timestamp(ts))))
    return float(rng.normal(0.0, sigma * np.sqrt(max(hours, 0.1) / 6.5)))


def load_fixture(name: str):
    """Load a committed JSON fixture from ``data/fixtures/``."""
    path = _FIXTURES_DIR / f"{name}.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
