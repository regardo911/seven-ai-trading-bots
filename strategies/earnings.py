"""Strategy 3 — Post-Earnings Announcement Drift with transcript NLP (Chapter 5).

Claude reads the earnings call transcript and returns a structured JSON
classification (the ONLY thing Claude does here); deterministic Python scores
it, chooses equity vs ATM option by IV-percentile, sizes the trade, and
enforces a hard 5-day time-stop. One inference per event (~$0.03-0.05, ch11).

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

import json

import pandas as pd

from framework import claude, cli, data, discord
from framework.brokers import Order, broker_for

# The book's honest-backtest marker (ch05): evaluate LLM-classified strategies
# on post-training-cutoff data only. The real cutoff for your model is on the
# Anthropic models page; the synthetic timeline uses 2025-01-01.
POST_CUTOFF_DATE = "2025-01-01"

HOLD_DAYS = 5             # hard time-stop at the close of day 5 (ch05)
EQUITY_STOP = 0.05        # -5% intraday stop on equity positions
OPTION_STOP = 0.50        # -50% stop on option positions
DEFAULT_RISK_PCT = 0.005  # 0.5%-1% band, scaled by magnitude (ch05)

# ch05 prompt template, verbatim.
PROMPT = """Read this earnings call transcript and classify the company's quarterly results.

Return a JSON object with EXACTLY these fields and no extra text:
{
  "headline_result": "beat" | "in_line" | "miss",
  "guidance_change": "raised" | "maintained" | "cut" | "withdrawn",
  "margin_direction": "expanding" | "flat" | "contracting",
  "sector_tone": "bullish" | "neutral" | "bearish",
  "confidence": <integer 1-10>
}

Rules:
- "headline_result" reflects EPS and revenue versus consensus from the call commentary.
- "guidance_change" reflects forward guidance for the next quarter or full year.
- "margin_direction" reflects gross or operating margin commentary.
- "sector_tone" reflects what management said about end-market conditions.
- "confidence" is your confidence in the classification, 10 = very confident, 1 = noisy/contradictory.

Return JSON only. No prose, no explanation, no markdown fences.

TRANSCRIPT:
"""

_REQUIRED_FIELDS = {"headline_result", "guidance_change", "margin_direction",
                    "sector_tone", "confidence"}


def classify_transcript(transcript_text: str) -> dict:
    """One Claude call, 200-token cap so prose can't wrap the JSON (ch05)."""
    response_text = claude.classify(PROMPT + transcript_text,
                                    model="claude-sonnet-4-6", max_tokens=200)
    classification = json.loads(response_text)
    missing = _REQUIRED_FIELDS - set(classification)
    if missing:
        raise ValueError(f"classification missing fields: {sorted(missing)}")
    return classification


def score_classification(c: dict) -> tuple[str, float]:
    """Returns (direction, magnitude) where direction is 'long', 'short', or 'skip'
    and magnitude is the position-size multiplier from 0 to 1. (ch05, verbatim.)"""
    if c["confidence"] < 7:
        return ("skip", 0.0)

    bullish_count = (
        (c["headline_result"] == "beat")
        + (c["guidance_change"] == "raised")
        + (c["margin_direction"] == "expanding")
        + (c["sector_tone"] == "bullish")
    )
    bearish_count = (
        (c["headline_result"] == "miss")
        + (c["guidance_change"] == "cut")
        + (c["margin_direction"] == "contracting")
        + (c["sector_tone"] == "bearish")
    )

    if bullish_count >= 3 and bearish_count == 0:
        return ("long", 1.0)
    if bullish_count >= 2 and bearish_count == 0:
        return ("long", 0.5)
    if bearish_count >= 3 and bullish_count == 0:
        return ("short", 1.0)
    if bearish_count >= 2 and bullish_count == 0:
        return ("short", 0.5)
    return ("skip", 0.0)


def choose_instrument(ticker: str, date: pd.Timestamp) -> tuple[str, float]:
    """IV-percentile rule (ch05): >50 equity, <30 ATM option, 30-50 equity.
    Pull the reading fresh at entry — IV moves intraday on earnings days."""
    ivp = data.iv_percentile(ticker, date)
    return ("option" if ivp < 30 else "equity", ivp)


def build_order(ticker: str, direction: str, magnitude: float, date: pd.Timestamp,
                account_equity: float = 100_000.0,
                risk_pct: float = DEFAULT_RISK_PCT) -> Order | None:
    """Deterministic sizing — Claude never touches this arithmetic (ch06 rule)."""
    instrument, ivp = choose_instrument(ticker, date)
    bars = data.get_bars(ticker, end=str(date.date()))
    price = float(bars["close"].iloc[-1])
    risk_dollars = account_equity * risk_pct * magnitude
    side = "buy" if direction == "long" else "sell"
    meta = {"instrument": instrument, "iv_percentile": ivp, "hold_days": HOLD_DAYS,
            "direction": direction, "entry": price}

    if instrument == "equity":
        stop_distance = EQUITY_STOP * price
        qty = int(risk_dollars / stop_distance)
        if qty < 1:
            return None
        meta["stop"] = price * (1 - EQUITY_STOP if direction == "long"
                                else 1 + EQUITY_STOP)
        return Order(ticker, qty, side, meta=meta)

    # ATM option ~30 DTE. Premium approximated as a fixed fraction of spot for
    # the synthetic demo (documented simplification; see docs/book-reconciliations.md).
    premium = 0.035 * price
    contracts = int(risk_dollars / (OPTION_STOP * premium * 100))
    if contracts < 1:
        return None
    meta.update({"premium": premium, "contracts": contracts, "dte": 30,
                 "option_type": "call" if direction == "long" else "put"})
    return Order(ticker, contracts, "buy", meta=meta)  # long the call/put


def signal(date: pd.Timestamp, account_equity: float = 100_000.0,
           events: list[dict] | None = None) -> list[Order]:
    """ch05 BUILD STEP 2 contract: runs once per evening after the close."""
    date = pd.Timestamp(date)
    if events is None:
        events = [e for e in data.load_fixture("transcripts")
                  if e["date"] == str(date.date())]
    orders: list[Order] = []
    for event in events:
        try:
            classification = classify_transcript(event["transcript"])
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"[earnings] {event['ticker']}: malformed classification "
                  f"({exc}) - skipped")
            continue
        direction, magnitude = score_classification(classification)
        if direction == "skip":
            continue
        order = build_order(event["ticker"], direction, magnitude, date,
                            account_equity)
        if order is not None:
            order.meta["classification"] = classification
            orders.append(order)
    return orders


# ------------------------------- CLI (A3) ----------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser(
        "strategies.earnings",
        "PEAD bot (ch05): transcript -> Claude JSON -> deterministic score -> trade.",
    )
    parser.add_argument("--transcript-provider", default="fmp",
                        help="transcript API (fmp default; offline fixtures used "
                             "when no FMP_API_KEY is set)")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--post-cutoff-only", action="store_true")
    args = parser.parse_args(argv)
    cli.banner("earnings drift bot (ch05)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live

    if args.backtest:
        from backtest import earnings as earnings_backtest

        result = earnings_backtest.run(post_cutoff_only=args.post_cutoff_only,
                                       write=True)
        earnings_backtest.print_report(result, regime=True)
        return 0

    print(f"[earnings] provider={args.transcript_provider} "
          "(offline fixture transcripts in use - set FMP_API_KEY to wire a real feed)")
    events = data.load_fixture("transcripts")
    placed = 0
    for event in events:
        date = pd.Timestamp(event["date"])
        for order in signal(date, events=[event]):
            c = order.meta["classification"]
            broker_for(order.symbol, paper=paper).place_order(order.symbol, order.qty,
                                                 order.side, "market")
            discord.notify(
                f"earnings: {order.meta['direction']} {order.symbol} "
                f"[{order.meta['instrument']}] conf={c['confidence']} "
                f"ivp={order.meta['iv_percentile']:.0f}"
            )
            placed += 1
    print(f"[earnings] fixtures processed: {len(events)}, paper trades placed: {placed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
