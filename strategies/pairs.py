"""Strategy 2 — Mean reversion with cointegrated pairs (Chapter 4).

Engle-Granger cointegration (NOT correlation — the distinction is the whole
chapter), Z-score entries at +/-2.0, hedge-ratio-aware sizing, a hard 20-day
time-stop instead of a price stop (the stop-loss paradox), and a VIX-30 regime
filter. Claude is OFFLINE at runtime — cointegration is statistics.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from framework import cli, data, discord
from framework.brokers import Order, broker_for

#: ch04 candidate basket — candidates the TEST evaluates, not pairs you trust.
DEFAULT_BASKET: list[tuple[str, str]] = [
    ("KO", "PEP"), ("XLE", "USO"), ("GLD", "SLV"), ("MSFT", "GOOGL"),
]
P_VALUE_THRESHOLD = 0.05
Z_ENTRY = 2.0
Z_LOOKBACK = 60
TIME_STOP_DAYS = 20      # the published-literature pairs time-stop (ch04)
VIX_FILTER = 30.0        # no new entries above this (ch04 Policy A)
COINT_WINDOW = 252       # rolling one-trading-year window (ch04 look-ahead fix)
DEFAULT_RISK_PCT = 0.005  # 0.5% per pair, half the trend bot's budget (ch04)
MAX_OPEN_PAIRS = 5


def scan_pairs(closes: dict[str, pd.Series],
               basket: list[tuple[str, str]] | None = None,
               window: int = COINT_WINDOW) -> list[dict]:
    """Engle-Granger scan (ch04 BUILD STEP 3): keep p < 0.05, hedge via OLS slope."""
    tradeable = []
    for a, b in basket or DEFAULT_BASKET:
        if a not in closes or b not in closes:
            continue
        joined = pd.concat([closes[a], closes[b]], axis=1, keys=[a, b]).dropna()
        y0, y1 = joined[a].tail(window), joined[b].tail(window)
        if len(y0) < 60:
            continue
        t_stat, p_value, _crit = coint(y0, y1, trend="c", method="aeg")
        if p_value < P_VALUE_THRESHOLD:
            hedge_ratio = float(np.polyfit(y0, y1, 1)[0])
            tradeable.append({"pair": (a, b), "p_value": float(p_value),
                              "hedge_ratio": hedge_ratio})
    return tradeable


def zscore(y0: pd.Series, y1: pd.Series, hedge_ratio: float,
           lookback: int = Z_LOOKBACK) -> pd.Series:
    """Z of the spread y1 - h*y0 against its rolling mean/std (ch04 step 4)."""
    spread = y1 - hedge_ratio * y0
    mean = spread.rolling(lookback).mean()
    std = spread.rolling(lookback).std()
    return (spread - mean) / std


def signal(bars: dict[str, pd.DataFrame], open_positions: list[dict] | None = None,
           vix: float | None = None, account_equity: float = 100_000.0,
           risk_pct: float = DEFAULT_RISK_PCT,
           basket: list[tuple[str, str]] | None = None) -> list[Order]:
    """ch04 BUILD STEP 1 contract: dict of bars in, list of leg Orders out."""
    open_positions = open_positions or []
    if vix is None:
        vix = float(data.vix_series().iloc[-1])
    if vix > VIX_FILTER:
        return []  # regime filter: sit out, ride existing under the time-stop
    if len(open_positions) >= MAX_OPEN_PAIRS:
        return []

    closes = {s: df["close"] for s, df in bars.items()}
    orders: list[Order] = []
    open_keys = {tuple(p["pair"]) for p in open_positions}
    for candidate in scan_pairs(closes, basket=basket):
        a, b = candidate["pair"]
        if (a, b) in open_keys:
            continue
        hedge = candidate["hedge_ratio"]
        z = zscore(closes[a], closes[b], hedge).iloc[-1]
        if np.isnan(z) or abs(z) < Z_ENTRY:
            continue
        risk_dollars = account_equity * risk_pct
        px_a, px_b = float(closes[a].iloc[-1]), float(closes[b].iloc[-1])
        qty_a = risk_dollars / px_a                      # long-leg notional = risk $
        qty_b = risk_dollars * hedge / px_b              # short leg scaled by hedge
        meta = {"pair": (a, b), "hedge_ratio": hedge, "z": float(z),
                "time_stop_days": TIME_STOP_DAYS}
        if z > Z_ENTRY:   # spread rich: short the rich (b), long the cheap (a)
            orders += [Order(a, qty_a, "buy", meta=meta),
                       Order(b, qty_b, "sell", meta=meta)]
        else:             # z < -2: inverse
            orders += [Order(a, qty_a, "sell", meta=meta),
                       Order(b, qty_b, "buy", meta=meta)]
    return orders


def should_close(position: dict, z_today: float, days_held: int) -> str | None:
    """Exit tests (ch04 step 6): Z crossed zero, or the 20-day time-stop."""
    if np.sign(z_today) != np.sign(position["entry_z"]) or z_today == 0:
        return "z_crossed_zero"
    if days_held >= TIME_STOP_DAYS:
        return "time_stop"
    return None


# ------------------------------- CLI (A3) ----------------------------------

def _parse_custom_pairs(raw: list[str]) -> list[tuple[str, str]]:
    return [tuple(p.upper().split(",", 1)) for p in raw]


def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser(
        "strategies.pairs",
        "Pairs bot (ch04): Engle-Granger cointegration + Z-score mean reversion.",
    )
    parser.add_argument("--basket", default="sectors", choices=["sectors", "custom"])
    parser.add_argument("--pairs", nargs="*", default=[],
                        help='custom pairs as "A,B C,D ..." (with --basket custom)')
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--rolling-coint", action="store_true")
    parser.add_argument("--window", type=int, default=COINT_WINDOW)
    args = parser.parse_args(argv)
    cli.banner("pairs bot (ch04)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live

    basket = (_parse_custom_pairs(args.pairs)
              if args.basket == "custom" and args.pairs else DEFAULT_BASKET)

    if args.backtest:
        from backtest import pairs as pairs_backtest

        result = pairs_backtest.run(window=args.window, write=True)
        pairs_backtest.print_report(result, regime=True)
        return 0

    symbols = sorted({s for pair in basket for s in pair})
    bars = {s: data.get_bars(s, live=args.live_data) for s in symbols}
    closes = {s: df["close"] for s, df in bars.items()}
    vix = float(data.vix_series().iloc[-1])
    print(f"[pairs] VIX {vix:.1f} "
          f"({'filter ACTIVE - no new entries' if vix > VIX_FILTER else 'ok'})")

    found = scan_pairs(closes, basket=basket, window=args.window)
    if not found:
        print("[pairs] scanner: 0 cointegrated pairs in this basket/regime "
              "(ch04 failure mode 1: expand the basket, don't weaken the p-value)")
    for cand in found:
        a, b = cand["pair"]
        z = zscore(closes[a], closes[b], cand["hedge_ratio"]).iloc[-1]
        print(f"[pairs] {a}/{b}: cointegrated p={cand['p_value']:.4f} "
              f"hedge={cand['hedge_ratio']:.2f} z={z:+.2f}")
    for order in signal(bars, vix=vix, basket=basket):
        broker_for(order.symbol, paper=paper).place_order(order.symbol, round(order.qty, 2),
                                             order.side, "market")
        a, b = order.meta["pair"]
        discord.notify(f"pairs: {order.side} {order.qty:.2f} {order.symbol} "
                       f"({a}/{b} z={order.meta['z']:+.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
