"""Shared backtest engine: one Runner per strategy, common metrics/reporting.

Runners simulate bar-by-bar on the synthetic data layer and emit ``Intent``
objects, so the same classes drive both the per-strategy backtests and the
ch09 allocator's multi-bot paper simulation. Every trade records the detail
the ch11 realism layer needs to net out slippage/commissions/inference.

    !! All numbers produced here come from SYNTHETIC sample data and are
    !! illustrative of the mechanics only. Not real. Not historical.
    !! Not a forecast. See DISCLAIMER.md.

Educational reference implementation. Not financial advice.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from framework import data, metrics, realism, walk_forward
from framework.allocator import Intent
from framework.metrics import inference_tracker
from strategies import cash_carry as cc
from strategies import earnings, flow, news, pairs, trend

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DISCLAIMER = ("Illustrative results on synthetic sample data - not indicative "
              "of real or historical performance. Educational only; not "
              "financial advice. See DISCLAIMER.md.")
BASE_CAPITAL = 100_000.0


class MarketCtx:
    """Shared bar/vix access for a simulation window."""

    def __init__(self, start: str = data.SIM_START, end: str = data.SIM_END):
        self.dates = pd.bdate_range(start, end)
        self.vix = data.vix_series()

    def vix_at(self, date: pd.Timestamp) -> float:
        window = self.vix.loc[self.vix.index <= date]
        return float(window.iloc[-1]) if len(window) else 16.0


class Runner:
    """Base strategy runner: daily P&L ledger + realized-trade records."""

    name = "base"

    def __init__(self, capital: float = BASE_CAPITAL):
        self.capital = capital
        self.daily: dict[pd.Timestamp, float] = defaultdict(float)
        self.trade_pnls: list[float] = []
        self.trades_detail: list[dict] = []

    def add_pnl(self, date: pd.Timestamp, pnl: float) -> None:
        self.daily[date] += pnl

    def close_trade(self, gross_pnl: float, **detail) -> None:
        self.trade_pnls.append(gross_pnl)
        detail.setdefault("strategy", self.name)
        detail.setdefault("inference_count", 0)
        detail.setdefault("model", "sonnet")
        detail["gross_pnl"] = gross_pnl
        self.trades_detail.append(detail)

    def step(self, date: pd.Timestamp, ctx: MarketCtx) -> list[Intent]:
        raise NotImplementedError


# ------------------------------ trend (ch03) --------------------------------

_TREND_ROUTE = {"SPY": ("equity_liquid", "alpaca", "equity"),
                "QQQ": ("equity_liquid", "alpaca", "equity"),
                "ES": ("futures", "ibkr", "futures"),
                "GC": ("futures", "ibkr", "futures")}


class TrendRunner(Runner):
    name = "trend"

    def __init__(self, symbols=None, capital: float = BASE_CAPITAL):
        super().__init__(capital)
        self.symbols = symbols or trend.INSTRUMENTS
        self.ind = {s: trend.compute_indicators(data.get_bars(s))
                    for s in self.symbols}
        self.positions: dict[str, dict] = {}

    def step(self, date, ctx):
        intents: list[Intent] = []
        for sym in self.symbols:
            df = self.ind[sym]
            if date not in df.index:
                continue
            i = df.index.get_loc(date)
            row = df.loc[date]
            if row[["donchian_high_20", "sma_200", "atr_14"]].isna().any():
                continue
            prev_close = float(df["close"].iloc[i - 1]) if i > 0 else row["close"]
            pos = self.positions.get(sym)
            if pos is not None:
                if trend.update_trailing_stop(pos, row) == "EXIT":
                    exit_px = float(min(max(pos["stop"], row["low"]), row["high"]))
                    self.add_pnl(date, pos["qty"] * (exit_px - prev_close))
                    gross = pos["qty"] * (exit_px - pos["entry"])
                    ac, broker, at = _TREND_ROUTE[sym]
                    self.close_trade(gross, asset_class=ac, broker=broker,
                                     asset_type=at, qty=pos["qty"],
                                     notional=pos["qty"] * pos["entry"],
                                     date=str(date.date()))
                    intents.append(Intent(self.name, sym, pos["qty"], "sell"))
                    del self.positions[sym]
                else:
                    self.add_pnl(date, pos["qty"] * (float(row["close"]) - prev_close))
            elif trend.is_entry(row):
                stop_distance = trend.ATR_MULTIPLIER * float(row["atr_14"])
                qty = trend.position_size(self.capital, stop_distance)
                if qty >= 1:
                    self.positions[sym] = {
                        "qty": qty, "entry": float(row["close"]),
                        "stop": float(row["close"]) - stop_distance,
                        "high_water": float(row["high"]),
                    }
                    intents.append(Intent(self.name, sym, qty, "buy"))
        return intents


# ------------------------------ pairs (ch04) --------------------------------

class PairsRunner(Runner):
    name = "pairs"

    def __init__(self, basket=None, window: int = pairs.COINT_WINDOW,
                 capital: float = BASE_CAPITAL):
        super().__init__(capital)
        self.basket = basket or pairs.DEFAULT_BASKET
        self.window = window
        symbols = sorted({s for p in self.basket for s in p})
        self.closes = {s: data.get_bars(s)["close"] for s in symbols}
        self.tradeable: list[dict] = []
        self.last_scan: pd.Timestamp | None = None
        self.positions: list[dict] = []

    def _z_at(self, cand: dict, date: pd.Timestamp) -> float:
        a, b = cand["pair"]
        y0 = self.closes[a].loc[:date]
        y1 = self.closes[b].loc[:date]
        z = pairs.zscore(y0, y1, cand["hedge_ratio"]).iloc[-1]
        return float(z) if z == z else 0.0

    def step(self, date, ctx):
        intents: list[Intent] = []
        # Monthly rolling-window rescan ending YESTERDAY (ch04 look-ahead fix).
        if self.last_scan is None or (date - self.last_scan).days >= 30:
            hist = {s: c.loc[: date - pd.Timedelta(days=1)]
                    for s, c in self.closes.items()}
            self.tradeable = pairs.scan_pairs(hist, basket=self.basket,
                                              window=self.window)
            self.last_scan = date

        # Mark, age, and exit open positions.
        for pos in list(self.positions):
            day_pnl = 0.0
            for sym, signed_qty in pos["legs"].items():
                series = self.closes[sym].loc[:date]
                if len(series) < 2:
                    continue
                day_pnl += signed_qty * float(series.iloc[-1] - series.iloc[-2])
            self.add_pnl(date, day_pnl)
            pos["days"] += 1
            z_now = self._z_at(pos["cand"], date)
            reason = pairs.should_close({"entry_z": pos["entry_z"]}, z_now,
                                        pos["days"])
            if reason:
                gross = sum(q * float(self.closes[s].loc[:date].iloc[-1] - e)
                            for s, (q, e) in pos["entries"].items())
                self.close_trade(gross, asset_class="equity_liquid",
                                 broker="alpaca", asset_type="equity",
                                 qty=sum(abs(q) for q in pos["legs"].values()),
                                 notional=pos["notional"], date=str(date.date()))
                for sym, signed_qty in pos["legs"].items():
                    intents.append(Intent(self.name, sym, abs(signed_qty),
                                          "sell" if signed_qty > 0 else "buy"))
                self.positions.remove(pos)

        # New entries (VIX filter + pair cap live here).
        if ctx.vix_at(date) > pairs.VIX_FILTER:
            return intents
        open_keys = {tuple(p["cand"]["pair"]) for p in self.positions}
        for cand in self.tradeable:
            if len(self.positions) >= pairs.MAX_OPEN_PAIRS:
                break
            a, b = cand["pair"]
            if (a, b) in open_keys:
                continue
            z = self._z_at(cand, date)
            if abs(z) < pairs.Z_ENTRY:
                continue
            risk = self.capital * pairs.DEFAULT_RISK_PCT
            px_a = float(self.closes[a].loc[:date].iloc[-1])
            px_b = float(self.closes[b].loc[:date].iloc[-1])
            qty_a, qty_b = risk / px_a, risk * cand["hedge_ratio"] / px_b
            sign = -1 if z > 0 else 1  # z>2: short the rich leg (b), long (a)
            legs = {a: qty_a * (1 if sign < 0 else -1),
                    b: qty_b * (1 if sign > 0 else -1)}
            self.positions.append({
                "cand": cand, "entry_z": z, "days": 0, "legs": legs,
                "entries": {s: (q, float(self.closes[s].loc[:date].iloc[-1]))
                            for s, q in legs.items()},
                "notional": risk * (1 + cand["hedge_ratio"]),
            })
            for sym, signed_qty in legs.items():
                intents.append(Intent(self.name, sym, abs(signed_qty),
                                      "buy" if signed_qty > 0 else "sell"))
        return intents


# ----------------------------- earnings (ch05) ------------------------------

class EarningsRunner(Runner):
    name = "earnings"

    def __init__(self, post_cutoff_only: bool = True,
                 capital: float = BASE_CAPITAL):
        super().__init__(capital)
        events = data.load_fixture("transcripts")
        if post_cutoff_only:
            events = [e for e in events if e["date"] >= earnings.POST_CUTOFF_DATE]
        self.by_date: dict[str, list[dict]] = defaultdict(list)
        for event in events:
            self.by_date[event["date"]].append(event)
        self.positions: list[dict] = []

    def step(self, date, ctx):
        intents: list[Intent] = []
        for event in self.by_date.get(str(date.date()), []):
            for order in earnings.signal(date, account_equity=self.capital,
                                         events=[event]):
                px = float(data.get_bars(order.symbol,
                                         end=str(date.date()))["close"].iloc[-1])
                self.positions.append({"order": order, "days": 0, "cum": 0.0,
                                       "entry_px": px, "last_px": px})
                intents.append(Intent(self.name, order.symbol, order.qty,
                                      order.side))
        for pos in list(self.positions):
            order = pos["order"]
            series = data.get_bars(order.symbol, end=str(date.date()))["close"]
            px = float(series.iloc[-1])
            delta_px = px - pos["last_px"]
            pos["last_px"] = px
            m = order.meta
            if m["instrument"] == "equity":
                signed = order.qty if m["direction"] == "long" else -order.qty
                day = signed * delta_px
                floor = -earnings.EQUITY_STOP * pos["entry_px"] * order.qty
            else:
                sign = 1 if m["option_type"] == "call" else -1
                day = (order.qty * 100 * 0.5 * sign * delta_px
                       - order.qty * 100 * m["premium"] * 0.02)  # synthetic decay
                floor = -earnings.OPTION_STOP * m["premium"] * 100 * order.qty
            if pos["cum"] + day < floor:  # stop-loss clamps the loss
                day = floor - pos["cum"]
            pos["cum"] += day
            self.add_pnl(date, day)
            pos["days"] += 1
            stopped = pos["cum"] <= floor
            if pos["days"] >= earnings.HOLD_DAYS or stopped:
                asset_class = ("equity_midcap" if m["instrument"] == "equity"
                               else "option")
                self.close_trade(pos["cum"], asset_class=asset_class,
                                 broker="alpaca",
                                 asset_type=("equity" if m["instrument"] == "equity"
                                             else "option"),
                                 qty=order.qty,
                                 notional=(order.qty * pos["entry_px"]
                                           if m["instrument"] == "equity"
                                           else order.qty * 100 * m["premium"]),
                                 inference_count=1, date=str(date.date()))
                intents.append(Intent(self.name, order.symbol, order.qty,
                                      "sell" if order.side == "buy" else "buy"))
                self.positions.remove(pos)
        return intents


# ------------------------------- news (ch06) --------------------------------

_NEWS_ROUTE = {"SPY": ("equity_liquid", "alpaca", "equity"),
               "QQQ": ("equity_liquid", "alpaca", "equity"),
               "GLD": ("equity_liquid", "alpaca", "equity"),
               "EURUSD": ("fx", "ibkr", "fx"),
               "BTC": ("crypto", "binance", "spot")}


class NewsRunner(Runner):
    name = "news"

    def __init__(self, capital: float = BASE_CAPITAL):
        super().__init__(capital)
        self.by_date: dict[str, list[dict]] = defaultdict(list)
        for item in data.load_fixture("headlines"):
            self.by_date[item["ts"][:10]].append(item)
        self.hashes: list[tuple[pd.Timestamp, str]] = []
        self.month: str | None = None
        self.month_cum = 0.0

    def step(self, date, ctx):
        intents: list[Intent] = []
        month_key = f"{date.year}-{date.month:02d}"
        if month_key != self.month:
            self.month, self.month_cum = month_key, 0.0
        self.hashes = [(ts, h) for ts, h in self.hashes
                       if (date - ts) <= pd.Timedelta(days=1)]
        todays = self.by_date.get(str(date.date()), [])
        if not todays:
            return intents
        state = news.AccountState(
            open_news_positions=0,
            equity_drawdown=max(0.0, -self.month_cum / self.capital),
        )
        orders, stats = news.signal(todays, state=state,
                                    recent_hashes=[h for _, h in self.hashes],
                                    account_equity=self.capital)
        self.hashes += [(date, h) for h in stats["recent_hashes"]
                        if h not in {x for _, x in self.hashes}]
        for order in orders:
            sym = order.symbol
            entry = order.meta["entry"]
            direction = 1 if order.side == "buy" else -1
            ret_2h = data.intraday_move(sym, date, news.SOFT_STOP_HOURS)
            if direction * ret_2h >= news.MOVE_DEVELOPED:
                realized_ret = data.intraday_move(sym, date + pd.Timedelta(hours=1),
                                                  news.HARD_STOP_HOURS)
            else:
                realized_ret = ret_2h
            gross = direction * order.qty * entry * realized_ret
            self.add_pnl(date, gross)
            self.month_cum += gross
            ac, broker, at = _NEWS_ROUTE[sym]
            self.close_trade(gross, asset_class=ac, broker=broker, asset_type=at,
                             qty=order.qty, notional=order.qty * entry,
                             inference_count=1, date=str(date.date()))
            # Entry AND same-bar exit are both real orders; at daily-bar
            # granularity they reach the allocator on the same bar and net
            # (ch09: the broker sees one order per symbol per bar).
            intents.append(Intent(self.name, sym, order.qty, order.side))
            intents.append(Intent(self.name, sym, order.qty,
                                  "sell" if order.side == "buy" else "buy"))
        return intents


# ------------------------------- flow (ch07) --------------------------------

class FlowRunner(Runner):
    name = "flow"

    def __init__(self, layers: str = "all", capital: float = BASE_CAPITAL):
        super().__init__(capital)
        self.layers = ({x.strip() for x in layers.split(",")}
                       if layers != "all" else {"delta", "gamma", "iv", "theta", "dte"})
        self.by_date: dict[str, list[dict]] = defaultdict(list)
        for event in data.load_fixture("flow_events"):
            self.by_date[event["ts"][:10]].append(event)
        self.positions: list[dict] = []

    def _open_gammas(self) -> list[float]:
        return [p["gamma_points"] for p in self.positions]

    def step(self, date, ctx):
        intents: list[Intent] = []
        for event in self.by_date.get(str(date.date()), []):
            event = dict(event)
            if "iv" not in self.layers:
                event["iv_percentile"] = 0  # ablation: disable the IV gate
            order = flow.signal(event, account_equity=self.capital,
                                open_gammas=(self._open_gammas()
                                             if "gamma" in self.layers else []))
            if order is None:
                continue
            # 5% portfolio-gross premium cap (ch07): downsize to fit.
            open_notional = sum(p["premium_notional"] for p in self.positions)
            headroom = flow.MAX_PORTFOLIO_OPTIONS_PCT * self.capital - open_notional
            fit = int(headroom / (100 * order.meta["premium"]))
            if fit < 1:
                continue
            order.qty = min(order.qty, fit)
            premium_notional = order.qty * 100 * order.meta["premium"]
            entry_px = float(data.get_bars(order.symbol,
                                           end=str(date.date()))["close"].iloc[-1])
            self.positions.append({
                "order": order, "dte": order.meta["dte"], "cum": 0.0,
                "entry_px": entry_px, "last_px": entry_px,
                "gamma_points": order.meta["gamma"] * order.qty * 100,
                "premium_notional": premium_notional,
            })
            intents.append(Intent(self.name, order.symbol, order.qty, order.side))
        for pos in list(self.positions):
            order = pos["order"]
            m = order.meta
            series = data.get_bars(order.symbol, end=str(date.date()))["close"]
            px = float(series.iloc[-1])
            sign = 1 if m["option_type"] == "call" else -1
            day = (order.qty * 100 * m["delta"] * sign * (px - pos["last_px"])
                   + order.qty * 100 * m["theta"])
            pos["last_px"] = px
            floor = -pos["premium_notional"]  # a long option can't lose more
            if pos["cum"] + day < floor:
                day = floor - pos["cum"]
            pos["cum"] += day
            self.add_pnl(date, day)
            pos["dte"] -= 1
            progress = sign * (px - pos["entry_px"]) / (0.05 * pos["entry_px"])
            reason = (flow.should_close(pos, m["theta"], progress, pos["dte"])
                      if "theta" in self.layers or "dte" in self.layers else None)
            if pos["cum"] <= floor:
                reason = "premium_floor"
            if reason:
                self.close_trade(pos["cum"], asset_class="option",
                                 broker="alpaca", asset_type="option",
                                 qty=order.qty, notional=pos["premium_notional"],
                                 date=str(date.date()))
                intents.append(Intent(self.name, order.symbol, order.qty, "sell"))
                self.positions.remove(pos)
        return intents


# ---------------------------- cash-and-carry (ch08) -------------------------

class CashCarryRunner(Runner):
    name = "cash_carry"

    def __init__(self, exchanges=None, instruments=None, months: int = 24,
                 capital: float = BASE_CAPITAL):
        super().__init__(capital)
        self.exchanges = exchanges or cc.EXCHANGES
        self.instruments = instruments or cc.INSTRUMENTS
        self.by_day: dict[tuple[str, str], dict] = {}
        for e in self.exchanges:
            for i in self.instruments:
                hist = data.get_funding_history(e, i, months=months)
                self.by_day[(e, i)] = {
                    str(day): grp for day, grp in
                    hist.groupby(hist.index.date)
                }
        self.open: dict[tuple[str, str], dict] = {}

    def step(self, date, ctx):
        intents: list[Intent] = []
        day = str(date.date())
        for (exchange, instrument), days in self.by_day.items():
            rows = days.get(day)
            if rows is None or rows.empty:
                continue
            key = (exchange, instrument)
            pos = self.open.get(key)
            if pos is not None:
                income = float(rows["fundingRate"].sum()) * pos["notional"]
                pos["cum"] += income
                self.add_pnl(date, income)
            last = rows.iloc[-1]
            basis = float((last["markPrice"] - last["indexPrice"])
                          / last["indexPrice"])
            if pos is not None:
                reason = cc.should_unwind(pos, float(last["fundingRate"]), basis)
                if reason:
                    gross = pos["cum"] + (pos["entry_basis"] - basis) * pos["notional"]
                    self.close_trade(gross, asset_class="crypto",
                                     broker=exchange, asset_type="futures",
                                     qty=pos["qty"],
                                     notional=2 * pos["notional"],  # both legs
                                     date=day)
                    intents.append(Intent(self.name, instrument, pos["qty"],
                                          "sell"))
                    del self.open[key]
            else:
                snap = {"fundingRate": float(last["fundingRate"]),
                        "exchange": exchange,
                        "symbol": f"{instrument}/USDT:USDT",
                        "indexPrice": float(last["indexPrice"])}
                open_list = [{"exchange": e, "symbol": i, "notional": p["notional"]}
                             for (e, i), p in self.open.items()]
                order = cc.signal(snap, open_list, capital=self.capital)
                if order is not None:
                    self.open[key] = {"notional": order.meta["notional"],
                                      "qty": order.qty, "cum": 0.0,
                                      "entry_basis": basis}
                    intents.append(Intent(self.name, instrument, order.qty, "buy"))
        return intents


# --------------------------- assembly & reporting ---------------------------

def run_runner(runner: Runner, start: str = data.SIM_START,
               end: str = data.SIM_END) -> dict:
    """Drive a runner across the window and assemble the result payload."""
    inference_tracker.reset()
    ctx = MarketCtx(start, end)
    for date in ctx.dates:
        runner.step(date, ctx)
    daily = pd.Series(runner.daily, dtype=float).reindex(ctx.dates, fill_value=0.0)
    returns = daily / runner.capital
    equity = (1.0 + returns).cumprod()
    pnls = runner.trade_pnls
    result = {
        "strategy": runner.name,
        "synthetic_data": True,
        "disclaimer": DISCLAIMER,
        "params": {"capital": runner.capital, "start": start, "end": end},
        "metrics": {
            "annualized_return": round(metrics.annualized_return(returns), 4),
            "max_drawdown": round(metrics.max_drawdown(equity), 4),
            "sharpe": round(metrics.sharpe(returns), 3),
            "win_rate": round(metrics.win_rate(pnls), 3),
            "expected_value_per_trade": round(metrics.expected_value(pnls), 2),
            "trade_count": len(pnls),
        },
        "per_regime": walk_forward.regime_breakdown(returns),
        "daily_returns": {"dates": [str(d.date()) for d in returns.index],
                          "values": [round(float(v), 8) for v in returns]},
        "trade_pnls": [round(float(p), 2) for p in pnls],
        "trades_detail": runner.trades_detail,
        "inference": inference_tracker.snapshot(),
    }
    return result


def realism_pass(result: dict) -> dict:
    """Apply the ch11 realism layer to a gross backtest result."""
    returns = pd.Series(result["daily_returns"]["values"],
                        index=pd.to_datetime(result["daily_returns"]["dates"]))
    capital = result["params"]["capital"]
    net_pnls = []
    cost_total = 0.0
    for detail in result["trades_detail"]:
        trade = realism.Trade(
            strategy=detail["strategy"], asset_class=detail["asset_class"],
            broker=detail["broker"], asset_type=detail["asset_type"],
            qty=detail["qty"], notional=detail["notional"],
            inference_count=detail.get("inference_count", 0),
            model=detail.get("model", "sonnet"), date=detail.get("date"),
        )
        costs = realism.trade_costs(trade)
        cost = sum(costs.values())
        cost_total += cost
        net_pnls.append(detail["gross_pnl"] - cost)
        when = pd.Timestamp(detail["date"])
        if when in returns.index:
            returns.loc[when] -= cost / capital
    equity = (1.0 + returns).cumprod()
    net = json.loads(json.dumps(result))  # deep copy
    net["realism_applied"] = True
    net["friction_total"] = round(cost_total, 2)
    net["metrics"] = {
        "annualized_return": round(metrics.annualized_return(returns), 4),
        "max_drawdown": round(metrics.max_drawdown(equity), 4),
        "sharpe": round(metrics.sharpe(returns), 3),
        "win_rate": round(metrics.win_rate(net_pnls), 3),
        "expected_value_per_trade": round(metrics.expected_value(net_pnls), 2),
        "trade_count": len(net_pnls),
    }
    net["per_regime"] = walk_forward.regime_breakdown(returns)
    net["trade_pnls"] = [round(float(p), 2) for p in net_pnls]
    net["daily_returns"] = {"dates": [str(d.date()) for d in returns.index],
                            "values": [round(float(v), 8) for v in returns]}
    return net


def save_json(name: str, payload: dict, subdir: str = "") -> Path:
    out_dir = RESULTS_DIR / subdir if subdir else RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    return path


def print_report(result: dict, regime: bool = False) -> None:
    m = result["metrics"]
    tag = " (realism net)" if result.get("realism_applied") else " (idealized gross)"
    print(f"\n[{result['strategy']} backtest]{tag} - SYNTHETIC sample data")
    print(f"  annualized return : {m['annualized_return']:+.1%}")
    print(f"  max drawdown      : {m['max_drawdown']:.1%}")
    print(f"  sharpe            : {m['sharpe']:.2f}")
    print(f"  win rate          : {m['win_rate']:.0%} over {m['trade_count']} trades")
    print(f"  EV per trade      : ${m['expected_value_per_trade']:+,.2f} "
          "(the headline metric, ch10)")
    if result.get("inference", {}).get("count"):
        inf = result["inference"]
        print(f"  claude inference  : {inf['count']} calls ~${inf['cost_usd']:.4f}")
    if regime and result.get("per_regime"):
        print(walk_forward.format_regime_table(result["per_regime"]))
    print(f"  note: {DISCLAIMER}")


def summarize_intents(intents: list[Intent]) -> dict[str, float]:
    """Net signed quantity per symbol (used by the allocator dashboard)."""
    net: dict[str, float] = defaultdict(float)
    for intent in intents:
        net[intent.symbol] += intent.qty if intent.side == "buy" else -intent.qty
    return dict(net)


RUNNERS = {
    "trend": TrendRunner,
    "pairs": PairsRunner,
    "earnings": EarningsRunner,
    "news": NewsRunner,
    "flow": FlowRunner,
    "cash_carry": CashCarryRunner,
}
