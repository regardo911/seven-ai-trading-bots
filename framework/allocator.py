"""Strategy 7 — the multi-bot portfolio allocator (Chapter 9).

The meta-strategy that turns six bots into one portfolio: risk-parity capital
sizing (inverse 60-day vol), a rolling 90-day correlation monitor (drop the
lower-Sharpe member of any pair > 0.70 for 30 consecutive days), per-strategy
drawdown circuit breakers (-15% MTD half-size, -25% zero until the 90-day
Sharpe recovers above 0.5), and conflict netting (the broker sees ONE order
per symbol per bar). Claude appears only in weekly governance review — never
on the trade path. "Netting is not a decision; it is arithmetic." (ch09)

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd

from framework import cli, data, discord, metrics
from framework.brokers import Order

MULTI_BROKER_THRESHOLD = 25_000.0   # below: Alpaca + ccxt only (ch09)
CORR_THRESHOLD = 0.70
CORR_WINDOW_DAYS = 30
HALF_SIZE_DRAWDOWN = -0.15
ZERO_SIZE_DRAWDOWN = -0.25
RECOVERY_SHARPE = 0.5
STRATEGY_NAMES = ["trend", "pairs", "earnings", "news", "flow", "cash_carry"]


@dataclass
class Intent:
    """One strategy's desired trade for the next bar (pre-netting)."""

    strategy: str
    symbol: str
    qty: float
    side: str  # "buy" | "sell"


@dataclass
class StrategyState:
    """Inputs to the drawdown circuit breaker (ch09, verbatim shape)."""

    mtd_pnl: float
    month_start_equity: float
    rolling_90d_sharpe: float


def risk_parity_weights(strategy_vols: dict[str, float]) -> dict[str, float]:
    """strategy_vols is the 60-day daily-return volatility for each strategy.
    Returns the capital weight (proportion of total) for each strategy.
    (ch09, verbatim.)"""
    inv_vols = {s: 1.0 / v for s, v in strategy_vols.items()}
    total = sum(inv_vols.values())
    return {s: iv / total for s, iv in inv_vols.items()}


def correlation_check(returns_df: pd.DataFrame, threshold: float = CORR_THRESHOLD,
                      window_days: int = CORR_WINDOW_DAYS) -> list[tuple[str, str]]:
    """Returns pairs of strategies whose 90-day rolling correlation has
    exceeded ``threshold`` for at least ``window_days`` consecutive days."""
    flagged: list[tuple[str, str]] = []
    cols = list(returns_df.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            rolling = returns_df[a].rolling(90).corr(returns_df[b])
            above = (rolling > threshold).astype(int)
            # longest consecutive run of days above the threshold
            run, best = 0, 0
            for flag in above.fillna(0):
                run = run + 1 if flag else 0
                best = max(best, run)
            if best >= window_days:
                flagged.append((a, b))
    return flagged


def drawdown_circuit(strategy_state: StrategyState) -> float:
    """Returns the multiplier on the strategy's risk-parity weight.
    (ch09, verbatim thresholds: -15% MTD half, -25% zero w/ Sharpe recovery.)"""
    if strategy_state.month_start_equity == 0:
        return 1.0
    mtd_pnl_pct = strategy_state.mtd_pnl / strategy_state.month_start_equity
    if mtd_pnl_pct <= ZERO_SIZE_DRAWDOWN:
        if strategy_state.rolling_90d_sharpe < RECOVERY_SHARPE:
            return 0.0
        return 1.0  # recovered, restore full weight
    if mtd_pnl_pct <= HALF_SIZE_DRAWDOWN:
        return 0.5
    return 1.0


def net_intents(intents: list[Intent]) -> list[Order]:
    """intents is a list of (strategy, symbol, qty, side) tuples.
    Returns the netted order list — one order per symbol per bar (ch09)."""
    net_qty: dict[str, float] = defaultdict(float)
    for intent in intents:
        sign = 1 if intent.side == "buy" else -1
        net_qty[intent.symbol] += sign * intent.qty
    orders: list[Order] = []
    for symbol, qty in net_qty.items():
        if qty > 0:
            orders.append(Order(symbol, abs(qty), "buy"))
        elif qty < 0:
            orders.append(Order(symbol, abs(qty), "sell"))
    return orders


@dataclass
class PortfolioState:
    """Snapshot the dashboard prints daily (ch09 BUILD STEP 6)."""

    capital: float
    weights: dict[str, float] = field(default_factory=dict)
    breaker: dict[str, float] = field(default_factory=dict)
    mtd_pnl: dict[str, float] = field(default_factory=dict)
    sharpe_90d: dict[str, float] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    corr_flags: list[tuple[str, str]] = field(default_factory=list)
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    netting_events: int = 0


class Allocator:
    """Runs all six strategy runners under one risk-disciplined portfolio."""

    def __init__(self, capital: float = 100_000.0,
                 strategies: list[str] | None = None,
                 warmup_days: int = 120, period_days: int = 30):
        self.capital = capital
        self.names = strategies or list(STRATEGY_NAMES)
        self.warmup_days = warmup_days
        self.period_days = period_days

    def run(self, write: bool = False) -> dict:
        from backtest import common  # lazy: avoids an import cycle

        runners = {n: common.RUNNERS[n]() for n in self.names}
        base = common.BASE_CAPITAL
        total_days = self.warmup_days + self.period_days
        all_dates = pd.bdate_range(data.SIM_START, data.SIM_END)
        window = all_dates[-total_days:]
        ctx = common.MarketCtx(str(window[0].date()), str(window[-1].date()))

        state = PortfolioState(capital=self.capital)
        state.weights = {n: 1.0 / len(self.names) for n in self.names}
        state.breaker = {n: 1.0 for n in self.names}
        month = None
        month_start_cum = {n: 0.0 for n in self.names}
        cum = {n: 0.0 for n in self.names}
        portfolio_daily: list[float] = []
        report_started = False

        for day_index, date in enumerate(ctx.dates):
            if day_index == self.warmup_days:
                # Risk-parity weights from realized warmup vols (ch09 mech. 1).
                vols = {}
                for name, runner in runners.items():
                    series = (pd.Series(runner.daily, dtype=float)
                              .reindex(ctx.dates[:day_index], fill_value=0.0)
                              / base)
                    vol = float(series.tail(60).std())
                    vols[name] = max(vol, 1e-5)
                state.weights = risk_parity_weights(vols)
                report_started = True

            month_key = (date.year, date.month)
            if month_key != month:
                month = month_key
                month_start_cum = dict(cum)

            day_intents: list[Intent] = []
            for name, runner in runners.items():
                intents = runner.step(date, ctx)
                pnl = runner.daily.get(date, 0.0)
                scale = (state.weights[name] * state.breaker[name]
                         * self.capital / base)
                cum[name] += pnl * scale
                day_intents += [
                    Intent(name, i.symbol, i.qty * scale, i.side)
                    for i in intents if state.breaker[name] > 0
                ]

            # Circuit breakers (ch09 mechanic 3) - evaluated daily.
            for name, runner in runners.items():
                series = (pd.Series(runner.daily, dtype=float)
                          .reindex(ctx.dates[:day_index + 1], fill_value=0.0)
                          / base)
                sharpe_90 = metrics.sharpe(series.tail(90))
                state.sharpe_90d[name] = sharpe_90
                state.mtd_pnl[name] = cum[name] - month_start_cum[name]
                strategy_equity = self.capital * state.weights[name]
                state.breaker[name] = drawdown_circuit(StrategyState(
                    mtd_pnl=state.mtd_pnl[name],
                    month_start_equity=max(strategy_equity, 1e-9),
                    rolling_90d_sharpe=sharpe_90,
                ))

            # Conflict netting (ch09 mechanic 4).
            sides = defaultdict(set)
            for intent in day_intents:
                sides[intent.symbol].add(intent.side)
            conflicts = [s for s, ss in sides.items() if len(ss) == 2]
            netted = net_intents(day_intents)
            if conflicts and report_started:
                state.netting_events += len(conflicts)
                print(f"[allocator] {date.date()}: netted opposing intents on "
                      f"{', '.join(conflicts)} -> {len(netted)} net order(s) "
                      "(one order per symbol per bar, ch09)")

            portfolio_daily.append(sum(
                runners[n].daily.get(date, 0.0)
                * state.weights[n] * state.breaker[n] * self.capital / base
                for n in self.names
            ))

        # Correlation monitor (ch09 mechanic 2) on the full window.
        returns_df = pd.DataFrame({
            n: (pd.Series(runners[n].daily, dtype=float)
                .reindex(ctx.dates, fill_value=0.0) / base)
            for n in self.names
        })
        state.corr_flags = correlation_check(returns_df)
        for a, b in state.corr_flags:
            drop = a if state.sharpe_90d.get(a, 0) <= state.sharpe_90d.get(b, 0) else b
            if drop not in state.dropped:
                state.dropped.append(drop)

        daily = pd.Series(portfolio_daily, index=ctx.dates)
        report = daily.iloc[self.warmup_days:]
        equity = self.capital + report.cumsum()
        state.total_pnl = float(report.sum())
        state.max_drawdown = metrics.max_drawdown(equity)

        self._print_dashboard(state)
        result = {
            "strategy": "allocator",
            "synthetic_data": True,
            "disclaimer": common.DISCLAIMER,
            "params": {"capital": self.capital, "period_days": self.period_days,
                       "warmup_days": self.warmup_days,
                       "multi_broker": self.capital >= MULTI_BROKER_THRESHOLD},
            "weights": {k: round(v, 4) for k, v in state.weights.items()},
            "breaker": state.breaker,
            "mtd_pnl": {k: round(v, 2) for k, v in state.mtd_pnl.items()},
            "sharpe_90d": {k: round(v, 2) for k, v in state.sharpe_90d.items()},
            "corr_flags": state.corr_flags,
            "dropped": state.dropped,
            "netting_events": state.netting_events,
            "metrics": {
                "total_pnl": round(state.total_pnl, 2),
                "max_drawdown": round(state.max_drawdown, 4),
                "sharpe": round(metrics.sharpe(report / self.capital), 3),
            },
            "daily_returns": {
                "dates": [str(d.date()) for d in report.index],
                "values": [round(float(v) / self.capital, 8) for v in report],
            },
        }
        if write:
            path = common.save_json("portfolio_paper", result)
            print(f"[allocator] wrote {path}")
        return result

    def _print_dashboard(self, state: PortfolioState) -> None:
        """The unified daily dashboard (ch09 BUILD STEP 6), end-of-run form."""
        print("\n=== PORTFOLIO DASHBOARD (paper, synthetic data) ===")
        broker_mode = ("multi-broker split: Alpaca + IBKR + ccxt"
                       if state.capital >= MULTI_BROKER_THRESHOLD
                       else "single-broker simplicity: Alpaca + ccxt")
        print(f"capital ${state.capital:,.0f} -> {broker_mode} (ch09 $25K rule)")
        header = (f"{'strategy':<12}{'weight':>8}{'breaker':>9}"
                  f"{'MTD P&L':>12}{'90d Sharpe':>12}")
        print(header)
        print("-" * len(header))
        for name in self.names:
            breaker = state.breaker.get(name, 1.0)
            tag = {1.0: "full", 0.5: "HALF", 0.0: "ZERO"}.get(breaker, f"{breaker}")
            print(f"{name:<12}{state.weights.get(name, 0):>7.1%}{tag:>9}"
                  f"{state.mtd_pnl.get(name, 0):>12,.2f}"
                  f"{state.sharpe_90d.get(name, 0):>12.2f}")
        print(f"correlation flags (>0.70 x 30d): {state.corr_flags or 'none'}")
        print(f"dropped strategies: {state.dropped or 'none'}")
        print(f"netted-conflict events: {state.netting_events}")
        print(f"report-window P&L: ${state.total_pnl:+,.2f} | "
              f"max drawdown: {max(state.max_drawdown, 0.0):.1%}")
        discord.notify(
            f"allocator dashboard: P&L ${state.total_pnl:+,.2f}, "
            f"maxDD {state.max_drawdown:.1%}, "
            f"netted {state.netting_events} conflicts, "
            f"dropped {state.dropped or 'none'}"
        )


# ------------------------------- CLI (A3) ----------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser(
        "framework.allocator",
        "Portfolio allocator (ch09): risk parity, correlation drops, breakers, netting.",
    )
    parser.add_argument("--strategies", default="all")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--paper-pass", action="store_true")
    parser.add_argument("--period", type=int, default=30)
    args = parser.parse_args(argv)
    cli.banner("portfolio allocator (ch09)")
    cli.guard_live(args)

    names = (list(STRATEGY_NAMES) if args.strategies == "all"
             else [s.strip() for s in args.strategies.split(",") if s.strip()])
    allocator = Allocator(capital=args.capital, strategies=names,
                          period_days=args.period)
    allocator.run(write=args.backtest or args.paper_pass)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
