# Book reconciliations — where this code differs from the book's snippets, and why

The book ships **illustrative snippets**, not a runnable framework. This
repository is the runnable expansion. Wherever the code intentionally differs
from a printed snippet, it is because the snippet contradicts the book's own
prose or its worked example — and every such call is listed here, in the open.
When a snippet and the book's worked answer disagree, **the worked answer
wins**, and the code says so at the point it matters.

## The two book bugs this code corrects

1. **ch03 Donchian window (bug as printed).** The printed snippet computes the
   rolling max *including the current bar*, so `close > donchian_high_20` can
   never fire (a close is never greater than a window that already contains its
   own high). The prose says "the highest high of the **prior** 20 trading
   days," so the code shifts the rolling max by one bar (`.shift(1)`) — see
   `strategies/trend.py`.
2. **ch07 delta budget (internal inconsistency).** The printed formula multiplies
   the budget by 100 and yields `0.4 → int → 0` contracts, yet the chapter states
   the worked answer "**four contracts**" twice. The code honors the worked
   example: the budget is 200 delta points per $10k at the 0.20 setting, and the
   bot takes the **minimum** of the caps (delta budget ∧ gamma headroom ∧ DTE
   multiplier ∧ 5% premium gross) — see `strategies/flow.py`.

## Offline simplifications (so the repo runs with zero keys and zero network)

3. **Option P&L is approximated** where the offline design can't call an options
   feed: earnings/flow option P&L uses a delta + theta approximation with a
   premium floor; earnings ATM premium ≈ 3.5% of spot; the VRP spread credit ≈
   30% of width. Real Greeks need an options feed this repo intentionally does
   not depend on. Referenced from `strategies/earnings.py`, `strategies/flow.py`,
   and `strategies/bench/vrp.py`.
4. **Synthetic data stands in for vendors.** `framework/data.py` generates
   deterministic, seeded, regime-aware OHLCV for the book's five named regimes
   (KO/PEP, GLD/SLV, XLE/USO are constructed cointegrated so ch04 always has a
   live example), a synthetic VIX with a 2020-style spike, and perp funding
   histories with a deliberate mid-2025 inversion (so the ch08 circuit breaker
   demonstrably fires). OHLCV is generated at import; the text fixtures
   (headlines/transcripts/flow) are committed JSON.
5. **News novelty hash** approximates "top-5 nouns and verbs" with a
   stopword-filtered top-5 content-token hash — the "simple hash" ch06 itself
   recommends starting with. Because the fixture stream is curated, the CLI notes
   that a raw production feed would reject ~70–80% of headlines.
6. **News same-bar round trips** emit both an entry and an exit intent, which is
   what makes the ch09 netting events observable at daily-bar granularity in the
   allocator demo.
7. **Basis-trade order shape.** ch08's `signal()` returns a single `Order` whose
   `meta` carries both legs — the book's signature is `Optional[Order]` while the
   trade itself has two legs (spot long + perp short).
8. **Live-order paths.** All three broker live calls — Alpaca (alpaca-py), IBKR
   (ib_async), crypto (ccxt) — are implemented behind lazy imports and the full
   ch02 safety gate, and are exercised by positive armed-live tests using fake
   adapters (no network, no credentials). Real trading still needs
   Gateway/credentials/SDKs, and the IBKR futures contract month + listing
   exchange must be confirmed per Appendix A5. Paper mode — the default and
   primary supported surface — never touches any of them.
9. **Fees the book refuses to hard-code** (the Alpaca option contract fee, etc.)
   are read from env/config with loud "verify at the source" comments;
   `VERIFIED_ALPACA_OPTION_FEE` keeps the book's name.

## The bundled backtest numbers are synthetic

`make realism` (`backtest_all --realism-pass`) on the bundled synthetic data
shows the ch11 lesson working: trend ~121 trades (gross Sharpe ~1.08 → net
~0.84), and cash-carry ~202 trades (gross Sharpe ~7.3 → net ~−0.2 — the realism
layer eating small funding cycles is exactly the point). Win rates, EVs, and
regime tables land in `backtest/results/`.

**Every number in this repository is computed on synthetic sample data. It is
illustrative of the mechanics only — not real, not historical, not predictive.
See [DISCLAIMER.md](../DISCLAIMER.md).**
