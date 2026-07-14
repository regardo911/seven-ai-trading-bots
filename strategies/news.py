"""Strategy 4 — News sentiment with Claude (Chapter 6, the load-bearing chapter).

    Claude builds the bot. Deterministic Python rules execute the bot.
    The human owns the strategy.

Three stages: a deterministic novelty filter (rejects 70-80% of headlines
before Claude ever sees them), a Claude classification into a constrained JSON
schema, and a deterministic gate + sizing layer. Claude classifies; Python
decides. This is the most Claude-intensive strategy in the book (~20
inferences/trade ≈ $0.36, ch11).

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import pandas as pd

from framework import claude, cli, data, discord
from framework.brokers import Order, broker_for
from framework.metrics import inference_tracker
from strategies.trend import atr

CONFIDENCE_FLOOR = 7      # the gate is the architecture; don't lower it (ch06)
MAX_OPEN_POSITIONS = 3    # one Fed surprise affects all of them (ch06)
DRAWDOWN_BREAKER = 0.05   # 5% MTD circuit breaker (ch06 gate)
RISK_PCT = 0.005          # 0.5% - news is whipsaw-prone (ch06)
STOP_ATR_MULT = 1.5       # tighter than trend's 3x: short-duration trades
SOFT_STOP_HOURS = 2       # close at 2h unless the move has developed
HARD_STOP_HOURS = 24
MOVE_DEVELOPED = 0.005    # +0.5% at the 2h mark extends to 24h (ch06 step 6)

#: The constrained asset list — the bot does not invent assets (ch06).
ASSET_SYMBOLS = {"SPY": "SPY", "QQQ": "QQQ", "EUR/USD": "EURUSD",
                 "GLD": "GLD", "BTC": "BTC"}

# ch06 prompt template, verbatim.
PROMPT = """Classify this market-moving headline.

Return a JSON object with EXACTLY these fields:
{
  "impact": <integer 1-10>,
  "direction": "long" | "short" | "skip",
  "asset": "SPY" | "QQQ" | "EUR/USD" | "GLD" | "BTC" | "none",
  "confidence": <integer 1-10>,
  "rationale": "<one sentence>"
}

- "impact" is the expected magnitude of market reaction, 10 = Fed-decision-level.
- "direction" is the trade direction; "skip" means do not trade.
- "asset" is the most-liquid instrument expressing the view.
- "confidence" is your confidence in the classification.
- "rationale" is one sentence; this is for your audit trail, not the trade.

Return JSON only.

HEADLINE:
"""

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "to", "as", "at", "by", "for", "and",
    "or", "is", "are", "was", "be", "with", "after", "amid", "over", "from",
    "its", "it", "this", "that", "new", "says", "say",
}


def _headline_hash(headline: str) -> str:
    """Approximate the book's hash: lowercase, strip punctuation, top-5
    content tokens by frequency (nouns/verbs approximated via stopword
    filtering — the simple version ch06 says to start with)."""
    tokens = re.findall(r"[a-z']+", headline.lower())
    content = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]
    counts: dict[str, int] = {}
    for tok in content:
        counts[tok] = counts.get(tok, 0) + 1
    top5 = sorted(counts, key=lambda t: (-counts[t], t))[:5]
    return hashlib.md5(" ".join(sorted(top5)).encode()).hexdigest()


def is_novel(headline: str, recent: list[str]) -> bool:
    """Stage 1, deterministic: reject anything seen in the last 24h (ch06)."""
    return _headline_hash(headline) not in recent


def classify_headline(headline: str) -> dict:
    """Stage 2, Claude: constrained-schema classification (ch06)."""
    response = claude.classify(PROMPT + headline, model="claude-sonnet-4-6",
                               max_tokens=200)
    classification = json.loads(response)
    for field_name in ("impact", "direction", "asset", "confidence"):
        if field_name not in classification:
            raise ValueError(f"classification missing '{field_name}'")
    return classification


@dataclass
class AccountState:
    """The account inputs to the deterministic gate (ch06)."""

    open_news_positions: int = 0
    equity_drawdown: float = 0.0  # month-to-date, as a positive fraction


def should_trade(c: dict, account_state: AccountState) -> bool:
    """Stage 3, deterministic gate (ch06, verbatim conditions).

    Claude classified. Python decides. None of these checks are Claude's
    responsibility — that is the architecture holding."""
    if c["confidence"] < CONFIDENCE_FLOOR:
        return False
    if c["direction"] == "skip":
        return False
    if c["asset"] == "none":
        return False
    if account_state.open_news_positions >= MAX_OPEN_POSITIONS:
        return False
    if account_state.equity_drawdown > DRAWDOWN_BREAKER:
        return False
    return True


def build_order(c: dict, asof: pd.Timestamp,
                account_equity: float = 100_000.0) -> Order | None:
    """Sizing is arithmetic: risk dollars / (1.5 x ATR14 stop distance)."""
    symbol = ASSET_SYMBOLS[c["asset"]]
    bars = data.get_bars(symbol, end=str(pd.Timestamp(asof).date()))
    stop_distance = STOP_ATR_MULT * atr(bars.tail(40))
    if stop_distance <= 0:
        return None
    risk_dollars = account_equity * RISK_PCT
    qty = risk_dollars / stop_distance
    qty = int(qty) if symbol not in ("BTC",) else round(qty, 4)
    if not qty:
        return None
    side = "buy" if c["direction"] == "long" else "sell"
    return Order(symbol, qty, side, meta={
        "asset": c["asset"], "impact": c["impact"], "confidence": c["confidence"],
        "stop_distance": stop_distance, "soft_stop_hours": SOFT_STOP_HOURS,
        "hard_stop_hours": HARD_STOP_HOURS, "entry": float(bars["close"].iloc[-1]),
    })


def signal(headlines: list[dict], state: AccountState | None = None,
           recent_hashes: list[str] | None = None,
           account_equity: float = 100_000.0) -> tuple[list[Order], dict]:
    """Full pipeline over a batch of headlines. Returns (orders, stats)."""
    state = state or AccountState()
    recent = list(recent_hashes or [])
    orders: list[Order] = []
    stats = {"seen": 0, "novel": 0, "classified": 0, "gated_in": 0}
    for item in headlines:
        stats["seen"] += 1
        headline = item["headline"]
        if not is_novel(headline, recent):
            continue
        recent.append(_headline_hash(headline))
        stats["novel"] += 1
        try:
            c = classify_headline(headline)
        except (json.JSONDecodeError, ValueError):
            continue  # malformed responses happen occasionally (ch06 step 3)
        stats["classified"] += 1
        if not should_trade(c, state):
            continue
        order = build_order(c, pd.Timestamp(item["ts"]), account_equity)
        if order is not None:
            stats["gated_in"] += 1
            state.open_news_positions += 1
            orders.append(order)
    stats["recent_hashes"] = recent
    return orders, stats


# ------------------------------- CLI (A3) ----------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser(
        "strategies.news",
        "News bot (ch06): novelty filter -> Claude classify -> deterministic gate.",
    )
    parser.add_argument("--feeds", default="bloomberg,reuters,fed")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--inference-cost-track", action="store_true")
    args = parser.parse_args(argv)
    cli.banner("news sentiment bot (ch06)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live

    if args.backtest:
        from backtest import news as news_backtest

        result = news_backtest.run(write=True)
        news_backtest.print_report(result, regime=True)
        return 0

    feeds = {f.strip().lower() for f in args.feeds.split(",")}
    headlines = [h for h in data.load_fixture("headlines")
                 if h["source"].lower() in feeds]
    print(f"[news] replaying {len(headlines)} fixture headlines from "
          f"{sorted(feeds)} (offline feed)")
    inference_tracker.reset()
    orders, stats = signal(headlines)
    for order in orders:
        broker_for(order.symbol, paper=paper).place_order(order.symbol, order.qty,
                                             order.side, "market")
        discord.notify(f"news: {order.side} {order.qty} {order.symbol} "
                       f"impact={order.meta['impact']} "
                       f"conf={order.meta['confidence']}")
    rejected = stats["seen"] - stats["novel"]
    print(f"[news] novelty filter rejected {rejected}/{stats['seen']} "
          f"({rejected / max(stats['seen'], 1):.0%}); "
          f"classified {stats['classified']}; entered {stats['gated_in']} "
          "(fixture stream is pre-curated; a raw production feed rejects "
          "70-80% here, ch06)")
    cost = inference_tracker.snapshot()
    print(f"[news] inference: {cost['count']} calls, ~${cost['cost_usd']:.4f} "
          "(tracked per ch11 - the news bot must clear its own token cost)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
