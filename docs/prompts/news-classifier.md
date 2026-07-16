# Prompt: Market Headline Classifier (Chapter 6)

**Used by:** `strategies/news.py::classify_headline` · **Model:** `claude-sonnet-4-6` · **max_tokens:** 200

## The prompt (book-verbatim)

```text
Classify this market-moving headline.

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
```

## Why it's built this way

- **The asset list is closed.** Five liquid instruments the framework already
  routes (SPY/QQQ/GLD → Alpaca, EUR/USD → IBKR, BTC → ccxt). Constraining the
  schema prevents Claude from suggesting trades the chassis can't place.
  Adding coverage is a code change, not a classification.
- **`rationale` is for the audit trail, not the trade.** Nothing downstream
  parses it; it exists so a human can review why the bot acted.
- **The gate lives outside the prompt.** `should_trade()` (deterministic)
  enforces confidence ≥ 7, direction ≠ skip, asset ≠ none, ≤ 3 open positions,
  MTD drawdown ≤ 5%. Claude classifies; Python decides.

## Offline stub behavior

Without `ANTHROPIC_API_KEY`, the stub maps keywords → asset (Fed/CPI → SPY,
gold → GLD, bitcoin → BTC, euro/ECB → EUR/USD, tech → QQQ), scores direction
from bullish/bearish cue counts, and grades impact (Fed-level cues score
highest). Deterministic, schema-identical, announced once.

## Cost (ch11 math, the numbers the book insists on)

~5,000 input + 200 output tokens → **$0.018 per inference** (not $0.025, not
$0.05). A production news trade involves ~20 inferences (entry + re-evals over
the 2–24h window) → **$0.36 per trade**. At 50–100 inferences/day that's
$1–2/day: small absolutely, decisive on thin edges. The realism layer nets it
out of every backtest here.

---
*Educational reference. Not financial advice. See [DISCLAIMER.md](../../DISCLAIMER.md).*
