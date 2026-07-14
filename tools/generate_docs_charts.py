"""Generate the explanatory strategy charts embedded in docs/strategies/*.md.

Every figure is computed from the repository's deterministic synthetic data
(framework/data.py + the committed fixtures) — same zero-key, zero-network
contract as everything else. Charts follow a validated palette (categorical
slots in fixed order, status colors only for entry/exit semantics, one-hue
ordinal ramps for funnels, blue<->red diverging for correlation) with direct
labels backing every sub-3:1 hue.

Regenerate with:
    pip install -e ".[viz]"
    python tools/generate_docs_charts.py

Outputs land in docs/images/ (committed). Synthetic sample data — the charts
illustrate mechanics, never performance. Not financial advice.
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from framework import data  # noqa: E402
from strategies import earnings, flow, news, pairs, trend  # noqa: E402
from strategies.bench import sector_rotate, vrp  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "images"

# Validated reference palette (dataviz method) --------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
S1, S2, S3 = "#2a78d6", "#1baf7a", "#eda100"   # categorical slots, fixed order
GOOD, CRIT = "#0ca30c", "#d03b3b"              # status: entry / stop-exit only
SEQ = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]  # ordinal ramp

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.family": "sans-serif", "font.size": 9,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.titlecolor": INK, "text.color": INK2,
})


def style(ax, grid_axis="y"):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def caption(fig):
    fig.text(0.99, 0.005, "synthetic sample data — illustrative mechanics only",
             ha="right", va="bottom", fontsize=6.8, color=MUTED)


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote docs/images/{name}")


def titled(ax, title, subtitle=None):
    ax.set_title(title, loc="left", fontsize=11, fontweight="semibold", pad=28)
    if subtitle:
        ax.text(0, 1.012, subtitle, transform=ax.transAxes, fontsize=8.2,
                color=INK2, va="bottom")


def funnel(ax, stages, counts):
    """Ordinal one-hue funnel (labels carry the values — relief rule)."""
    y = np.arange(len(stages))[::-1]
    colors = SEQ[:len(stages)]
    ax.barh(y, counts, height=0.62, color=colors, edgecolor=SURFACE, linewidth=1)
    for yi, stage, count in zip(y, stages, counts):
        ax.text(counts[0] * 0.01, yi, f" {stage}", va="center", fontsize=8.6,
                color=SURFACE if count > counts[0] * 0.35 else INK2)
        ax.text(count, yi, f" {count}", va="center", fontsize=8.6, color=INK2)
    ax.set_yticks([])
    ax.set_xlim(0, counts[0] * 1.12)
    style(ax, grid_axis="x")


def _mini_trend_sim(symbol, start):
    """Entry/exit marks for the display window using the real ch03 rules."""
    bars = trend.compute_indicators(data.get_bars(symbol)).loc[start:]
    position, entries, exits = None, [], []
    for ts, row in bars.iterrows():
        if row[["donchian_high_20", "sma_200", "atr_14"]].isna().any():
            continue
        if position is None and trend.is_entry(row):
            position = {"qty": 1, "entry": row["close"], "high_water": row["high"],
                        "stop": row["close"] - trend.ATR_MULTIPLIER * row["atr_14"]}
            entries.append((ts, row["close"]))
        elif position is not None:
            if trend.update_trailing_stop(position, row) == "EXIT":
                exits.append((ts, position["stop"]))
                position = None
    return bars, entries, exits


def chart_trend(name="trend_donchian.png", symbol="SPY", start="2024-01-01"):
    bars, entries, exits = _mini_trend_sim(symbol, start)
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    ax.plot(bars.index, bars["close"], color=INK2, lw=1.1, label=f"{symbol} close")
    ax.plot(bars.index, bars["donchian_high_20"], color=S1, lw=2,
            label="Donchian-20 high (prior 20d)")
    ax.plot(bars.index, bars["sma_200"], color=S3, lw=2, label="200-day SMA")
    ax.text(bars.index[-1], bars["donchian_high_20"].iloc[-1], "  Donchian-20",
            fontsize=8, color=INK2, va="center")
    ax.text(bars.index[-1], bars["sma_200"].iloc[-1], "  200-SMA",
            fontsize=8, color=INK2, va="center")
    if entries:
        ax.scatter(*zip(*entries), marker="^", s=52, color=GOOD, zorder=5,
                   label="entry (breakout + filter)")
    if exits:
        ax.scatter(*zip(*exits), marker="v", s=52, color=CRIT, zorder=5,
                   label="exit (3xATR trailing stop)")
    titled(ax, "Trend bot — Donchian breakout with a ratcheting trailing stop (ch03)",
           "buy a 20-day breakout above the 200-SMA; trail 3x ATR(14); the stop only moves up")
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    style(ax)
    caption(fig)
    save(fig, name)


def chart_fx(name="fx_trend_donchian.png"):
    chart_trend(name=name, symbol="EURUSD", start="2024-01-01")


def chart_pairs():
    ko = data.get_bars("KO", start="2024-06-01")["close"]
    pep = data.get_bars("PEP", start="2024-06-01")["close"]
    hedge = float(np.polyfit(ko, pep, 1)[0])
    z = pairs.zscore(ko, pep, hedge)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.6, 6.2), sharex=True,
                                   height_ratios=[1.15, 1])
    ax1.plot(ko.index, ko / ko.iloc[0] * 100, color=S1, lw=2, label="KO (indexed)")
    ax1.plot(pep.index, pep / pep.iloc[0] * 100, color=S2, lw=2, label="PEP (indexed)")
    ax1.text(ko.index[-1], (ko / ko.iloc[0] * 100).iloc[-1], "  KO",
             fontsize=8, color=INK2, va="center")
    ax1.text(pep.index[-1], (pep / pep.iloc[0] * 100).iloc[-1], "  PEP",
             fontsize=8, color=INK2, va="center")
    titled(ax1, "Pairs bot — a cointegrated pair and its tradeable spread (ch04)",
           f"PEP ~ {hedge:.2f} x KO + stationary noise; trade the spread, not the direction")
    ax1.legend(loc="upper left", frameon=False, fontsize=8)
    ax1.set_ylabel("indexed = 100")
    style(ax1)

    ax2.plot(z.index, z, color=S1, lw=1.6, label="spread Z-score (60d)")
    ax2.axhline(0, color=AXIS, lw=0.9)
    for level in (2, -2):
        ax2.axhline(level, color=INK2, lw=1, ls=(0, (4, 3)))
    ax2.text(z.index[2], 2.15, "entry: Z > +2 (short rich / long cheap)",
             fontsize=7.8, color=INK2)
    ax2.text(z.index[2], -2.55, "entry: Z < -2 (inverse legs)",
             fontsize=7.8, color=INK2)
    ax2.fill_between(z.index, 2, np.maximum(z, 2), color=CRIT, alpha=0.10)
    ax2.fill_between(z.index, -2, np.minimum(z, -2), color=CRIT, alpha=0.10)
    ax2.set_ylabel("Z")
    style(ax2)
    caption(fig)
    save(fig, "pairs_zscore.png")


def chart_earnings():
    event_date = pd.Timestamp("2025-02-06")  # ACME beat-and-raise fixture
    bars = data.get_bars("ACME", start="2025-01-10", end="2025-03-07")["close"]
    hold = bars.loc[event_date:].iloc[:earnings.HOLD_DAYS + 1]

    events = data.load_fixture("transcripts")
    classified = scored = 0
    for event in events:
        c = earnings.classify_transcript(event["transcript"])
        classified += 1
        if earnings.score_classification(c)[0] != "skip":
            scored += 1

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.6, 6.2),
                                   height_ratios=[1.25, 1])
    ax1.plot(bars.index, bars, color=INK2, lw=1.6, label="ACME close")
    ax1.axvline(event_date, color=S1, lw=1.4, ls=(0, (4, 3)))
    ax1.text(event_date, bars.max(), "  earnings call\n  (Claude reads the transcript)",
             fontsize=7.8, color=INK2, va="top")
    ax1.axvspan(hold.index[0], hold.index[-1], color=S2, alpha=0.14)
    ax1.text(hold.index[-1], hold.iloc[-1], "  5-day drift hold\n  (hard time-stop)",
             fontsize=7.8, color=INK2, va="center")
    titled(ax1, "Earnings bot — trade the post-announcement drift, not the gap (ch05)",
           "one classified event from the bundled fixtures; deterministic scorer sizes the entry")
    style(ax1)

    funnel(ax2, ["transcripts fetched", "classified by Claude (strict JSON)",
                 "scorer: direction != skip (3-of-4 rule)", "paper orders placed"],
           [len(events), classified, scored, scored])
    ax2.set_title("the deterministic pipeline over the bundled fixtures",
                  loc="left", fontsize=9, color=INK2, pad=8)
    caption(fig)
    save(fig, "earnings_pipeline.png")


def chart_news():
    headlines = data.load_fixture("headlines")
    by_day: dict[str, list[dict]] = {}
    for item in headlines:
        by_day.setdefault(item["ts"][:10], []).append(item)
    seen = novel = classified = gated = 0
    points = []  # (impact, confidence, traded)
    hashes: list[str] = []
    for day in sorted(by_day):
        state = news.AccountState()
        for item in by_day[day]:
            seen += 1
            if not news.is_novel(item["headline"], hashes):
                continue
            hashes.append(news._headline_hash(item["headline"]))
            novel += 1
            c = news.classify_headline(item["headline"])
            classified += 1
            ok = news.should_trade(c, state)
            if ok:
                gated += 1
                state.open_news_positions += 1
            points.append((c["impact"], c["confidence"], ok))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.6, 6.4),
                                   height_ratios=[1, 1.2])
    funnel(ax1, ["headlines seen", "survive novelty filter",
                 "classified by Claude", "pass the deterministic gate"],
           [seen, novel, classified, gated])
    titled(ax1, "News bot — filter, classify, gate (ch06)",
           "Claude classifies; Python decides. The gate is the architecture.")

    rng = np.random.default_rng(11)
    for impact, conf, traded in points:
        jx, jy = rng.uniform(-0.18, 0.18, 2)
        if traded:
            ax2.scatter(impact + jx, conf + jy, s=42, color=S1, zorder=5)
        else:
            ax2.scatter(impact + jx, conf + jy, s=30, facecolors="none",
                        edgecolors=MUTED, lw=1.2)
    ax2.scatter([], [], s=42, color=S1, label="traded")
    ax2.scatter([], [], s=30, facecolors="none", edgecolors=MUTED, lw=1.2,
                label="skipped by the gate")
    ax2.axhline(news.CONFIDENCE_FLOOR - 0.5, color=INK2, lw=1, ls=(0, (4, 3)))
    ax2.text(1.0, news.CONFIDENCE_FLOOR - 0.42, "gate: confidence >= 7",
             fontsize=7.8, color=INK2, va="bottom")
    ax2.set_xlabel("impact (1-10)")
    ax2.set_ylabel("confidence (1-10)")
    ax2.set_xlim(0.5, 10)
    ax2.set_ylim(2.5, 10)
    ax2.legend(loc="lower right", frameon=False, fontsize=8)
    style(ax2, grid_axis="both")
    caption(fig)
    save(fig, "news_pipeline.png")


def chart_flow():
    events = data.load_fixture("flow_events")
    clean = [e for e in events if flow.is_clean_directional(e)[0]]
    iv_ok = [e for e in clean if flow.iv_filter_ok(e["iv_percentile"])]
    sized = [e for e in iv_ok
             if int(flow.position_size_by_delta(100_000, e["delta"])
                    * flow.dte_size_multiplier(e["dte"])) >= 1]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.6, 6.0),
                                   height_ratios=[1, 0.9])
    funnel(ax1, ["whale prints on the tape", "clean directional (no spreads/LEAPs/<$50k)",
                 "IV percentile < 80 (crush filter)", "sized >= 1 contract (delta budget x DTE)"],
           [len(events), len(clean), len(iv_ok), len(sized)])
    titled(ax1, "Flow bot — four Greek gates between the whale and the mirror (ch07)",
           "the gamma cap then bounds the whole portfolio; the bot takes the minimum of the caps")

    dte = np.arange(0, 121)
    mult = [flow.dte_size_multiplier(int(d)) for d in dte]
    ax2.step(dte, mult, where="post", color=S1, lw=2)
    ax2.set_ylim(0, 1.15)
    ax2.set_xlabel("days to expiry")
    ax2.set_ylabel("size multiplier")
    ax2.axvspan(0, 14, color=CRIT, alpha=0.07)
    ax2.text(7, 0.32, "weeklies:\n25% size\n(theta bleeds fast)", fontsize=7.8,
             color=INK2, ha="center")
    ax2.text(70, 1.04, "standard & LEAPs: full size", fontsize=7.8, color=INK2)
    style(ax2)
    caption(fig)
    save(fig, "flow_gates.png")


def chart_cash_carry():
    hist = data.get_funding_history("binance", "BTC", months=10)
    rate = hist["fundingRate"] * 100  # per-8h %, display units
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    ax.plot(rate.index, rate, color=S1, lw=1.1, label="BTC perp funding (binance)")
    ax.axhline(0.03, color=GOOD, lw=1.2, ls=(0, (4, 3)))
    ax.axhline(0.005, color=MUTED, lw=1.1, ls=(0, (4, 3)))
    ax.axhline(0, color=AXIS, lw=0.9)
    ax.text(rate.index[3], 0.032, "entry floor: +0.03%/8h (~33% annualized)",
            fontsize=7.8, color=INK2, va="bottom")
    ax.text(rate.index[3], 0.007, "exit: below 0.005%/8h", fontsize=7.8,
            color=INK2, va="bottom")
    above = rate >= 0.03
    ax.fill_between(rate.index, 0.03, rate.where(above, 0.03),
                    color=S2, alpha=0.25, label="collecting funding (short perp / long spot)")
    inv = rate.loc["2025-06-09":"2025-06-13"]
    ax.annotate("funding inverts ->\ncircuit breaker unwinds immediately",
                xy=(inv.idxmin(), inv.min()), xytext=(rate.index[len(rate) // 2],
                rate.min() * 0.75), fontsize=7.8, color=INK2,
                arrowprops={"arrowstyle": "->", "color": CRIT, "lw": 1.4})
    titled(ax, "Cash-and-carry bot — paid by crowded longs, out on inversion (ch08)",
           "delta-neutral: the position collects the shaded funding, not the price move")
    ax.set_ylabel("funding rate per 8h window (%)")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    style(ax)
    caption(fig)
    save(fig, "cash_carry_funding.png")


def chart_allocator():
    from backtest import common

    names = ["trend", "pairs", "earnings", "news", "flow", "cash_carry"]
    window = pd.bdate_range(data.SIM_START, data.SIM_END)[-150:]
    ctx = common.MarketCtx(str(window[0].date()), str(window[-1].date()))
    runners = {n: common.RUNNERS[n]() for n in names}
    for date in ctx.dates:
        for runner in runners.values():
            runner.step(date, ctx)
    returns = pd.DataFrame({
        n: (pd.Series(r.daily, dtype=float).reindex(ctx.dates, fill_value=0.0)
            / common.BASE_CAPITAL)
        for n, r in runners.items()
    })
    from framework.allocator import risk_parity_weights

    vols = {n: max(float(returns[n].std()), 1e-5) for n in names}
    weights = risk_parity_weights(vols)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 4.6), width_ratios=[1, 1])
    order = sorted(names, key=lambda n: weights[n])
    y = np.arange(len(order))
    ax1.barh(y, [weights[n] * 100 for n in order], height=0.62, color=S1,
             edgecolor=SURFACE, linewidth=1)
    ax1.set_yticks(y, order)
    for yi, n in zip(y, order):
        ax1.text(weights[n] * 100, yi, f" {weights[n]:.0%}", va="center",
                 fontsize=8.4, color=INK2)
    ax1.set_xlabel("capital weight (inverse 60d vol)")
    ax1.set_title("Risk-parity weights — low-vol strategies get more notional",
                  loc="left", fontsize=9.5, color=INK, pad=10)
    style(ax1, grid_axis="x")

    corr = returns.corr().to_numpy().copy()
    np.fill_diagonal(corr, np.nan)  # self-correlation carries no information
    cmap = LinearSegmentedColormap.from_list("div", [S1, "#f0efec", "#e34948"])
    cmap.set_bad("#f0efec")
    ax2.imshow(corr, cmap=cmap, vmin=-1, vmax=1)
    ax2.set_xticks(range(len(names)), names, rotation=30, ha="right", fontsize=7.4)
    ax2.set_yticks(range(len(names)), names, fontsize=7.4)
    for i in range(len(names)):
        for j in range(len(names)):
            label = "—" if i == j else f"{corr[i, j]:+.2f}"
            ax2.text(j, i, label, ha="center", va="center", fontsize=6.8,
                     color=MUTED if i == j else INK)
    ax2.set_title("90-day correlation — pairs > 0.70 for 30 days get dropped",
                  loc="left", fontsize=9.5, color=INK, pad=10)
    for side in ("top", "right", "left", "bottom"):
        ax2.spines[side].set_visible(False)
    fig.suptitle("Allocator — six bots, one risk-disciplined portfolio (ch09)",
                 x=0.045, y=0.985, ha="left", fontsize=11.5,
                 fontweight="semibold", color=INK)
    fig.subplots_adjust(top=0.82, bottom=0.20, wspace=0.42)
    caption(fig)
    fig.savefig(OUT / "allocator_dashboard.png", dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print("  wrote docs/images/allocator_dashboard.png")


def chart_vrp():
    spx = 5000.0
    width = vrp.SPREAD_WIDTH_PCT * spx
    credit = vrp.CREDIT_FRACTION * width
    short_k, long_k = spx, spx * (1 - vrp.SPREAD_WIDTH_PCT)
    prices = np.linspace(spx * 0.88, spx * 1.06, 400)
    payoff = (credit - np.clip(short_k - prices, 0, None)
              + np.clip(long_k - prices, 0, None)) * 100  # per spread

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    ax.plot(prices, payoff, color=S1, lw=2.4, label="P&L at expiry (per spread)")
    ax.axhline(0, color=AXIS, lw=0.9)
    ax.fill_between(prices, 0, payoff, where=payoff > 0, color=GOOD, alpha=0.08)
    ax.fill_between(prices, 0, payoff, where=payoff < 0, color=CRIT, alpha=0.08)
    for strike, label in ((long_k, "long put (5% OTM)\ncaps the loss"),
                          (short_k, "short put (ATM)\ncollects the premium")):
        ax.axvline(strike, color=MUTED, lw=1, ls=(0, (4, 3)))
        ax.text(strike, payoff.max() * 1.12, label, fontsize=7.6, color=INK2,
                ha="center", va="bottom")
    breakeven = short_k - credit
    ax.scatter([breakeven], [0], s=44, color=INK, zorder=5)
    ax.text(breakeven, payoff.min() * 0.18, f"breakeven {breakeven:,.0f}",
            fontsize=7.8, color=INK2, ha="center")
    ax.text(prices[-1], credit * 100, f"  max profit = credit (${credit * 100:,.0f})",
            fontsize=7.8, color=INK2, va="center", ha="right")
    ax.text(prices[0], payoff.min(), f"max loss = width - credit "
            f"(${(width - credit) * 100:,.0f}), sized to 1% of capital  ",
            fontsize=7.8, color=INK2, va="bottom")
    titled(ax, "VRP bench — defined-risk put spread, never naked (Appendix B1)",
           "sell insurance when it's overpriced (IV pct < 30 or VIX < 18); "
           "the long leg caps the tail")
    ax.set_xlabel("SPX at expiry")
    ax.set_ylabel("P&L ($)")
    ax.set_ylim(payoff.min() * 1.35, payoff.max() * 1.45)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    style(ax)
    caption(fig)
    save(fig, "vrp_payoff.png")


def chart_sector():
    ranked = sector_rotate.rank_sectors(pd.Timestamp(data.SIM_END))
    names = [n for n, _ in ranked][::-1]
    scores = [s * 100 for _, s in ranked][::-1]
    colors = [S1 if n in [x for x, _ in ranked[:3]] else AXIS for n in names]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    y = np.arange(len(names))
    ax.barh(y, scores, height=0.62, color=colors, edgecolor=SURFACE, linewidth=1)
    ax.set_yticks(y, names)
    for yi, s in zip(y, scores):
        ax.text(s + (1 if s >= 0 else -1), yi, f"{s:+.0f}%", va="center",
                ha="left" if s >= 0 else "right", fontsize=8.2, color=INK2)
    ax.axvline(0, color=AXIS, lw=0.9)
    titled(ax, "Sector rotation bench — the 12-1 momentum ranking (Appendix B3)",
           "trailing 12-month return excluding the last month; "
           "hold the top 3 (blue) equal-weight, rebalance monthly")
    ax.set_xlabel("12-1 momentum (%)")
    style(ax, grid_axis="x")
    caption(fig)
    save(fig, "sector_momentum.png")


CHARTS = {
    "trend": chart_trend, "pairs": chart_pairs, "earnings": chart_earnings,
    "news": chart_news, "flow": chart_flow, "cash_carry": chart_cash_carry,
    "allocator": chart_allocator, "vrp": chart_vrp, "fx_trend": chart_fx,
    "sector_rotate": chart_sector,
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for name, fn in CHARTS.items():
        if only and name not in only:
            continue
        print(f"[charts] {name}")
        fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
