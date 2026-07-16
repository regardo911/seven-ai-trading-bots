# Errata & reconciliation

The printed book is a fixed snapshot; this repository is live and gets
maintained. When the two disagree, **this file is the tie-breaker.** It has two
parts: **corrections**, where the book is simply wrong, and **reconciliation**,
where the repo has moved past the pages and you just need the two lined up. Code
changes to the repo are logged in [`CHANGELOG.md`](CHANGELOG.md).

---

## Corrections (the printed book is wrong)

### Chapters 6 & 11: which bots call Claude at runtime, the book contradicts itself

Chapter 6 (§"where each of the seven") says the two runtime-inference strategies
are "**news, allocator**." Chapter 11 says "**Two (PEAD, allocator)** use Claude
lightly. One (**news**) uses Claude heavily," which names *three* bots, not two,
and disagrees with Chapter 6 about which two. Both cannot be right.

The correct classification is the one Chapter 9 itself states ("the allocator
does not use Claude on the runtime hot path for trade decisions… governance and
supervision, not the millisecond-by-millisecond trade execution"):

- **Two** bots call Claude on the runtime **trade path**: **PEAD** (ch05, ~1
  inference per earnings event) and **News** (ch06, heavy).
- The **allocator** (ch09) calls Claude *only* in weekly governance review, off
  the trade path, so it makes **zero per-trade inferences**.
- **Five of the seven** therefore have zero trade-path inference: trend, pairs,
  flow, cash-and-carry, and the allocator.

`docs/architecture.md` in this repo carries the corrected table and prose.

### Chapter 3: the Donchian entry can never fire as printed

The printed snippet computes the rolling max **including the current bar**, so
`close > donchian_high_20` is never true (a close can't exceed a window that
already contains its own high). The chapter's prose is right, "the highest high
of the **prior** 20 trading days," so the code shifts the rolling max by one bar
(`.shift(1)`). See `strategies/trend.py`.

### Chapter 7: the delta-budget formula yields zero, but the worked answer is four

The printed sizing formula multiplies the budget by 100 and yields
`0.4 → int → 0` contracts, yet the chapter states the worked answer "**four
contracts**" twice. The code honors the worked example: the budget is 200 delta
points per $10k at the 0.20 setting, and the bot takes the **minimum** of the
caps (delta budget ∧ gamma headroom ∧ DTE multiplier ∧ 5% premium gross). See
`strategies/flow.py`.

---

## Reconciling the book with the current repo

These are not book errors. They are places where a runnable, offline,
zero-key repository necessarily differs from the book's illustrative snippets.
When a snippet and the book's own worked example disagree, the worked example
wins, and the code says so at the point it matters.

### Option P&L is approximated where there is no options feed

Earnings/flow option P&L uses a delta + theta approximation with a premium floor;
earnings ATM premium ≈ 3.5% of spot; the VRP spread credit ≈ 30% of width. Real
Greeks need an options feed this repo intentionally does not depend on.
Referenced from `strategies/earnings.py`, `strategies/flow.py`, and
`strategies/bench/vrp.py`.

### Synthetic data stands in for vendors

`framework/data.py` generates deterministic, seeded, regime-aware OHLCV for the
book's five named regimes (KO/PEP, GLD/SLV, XLE/USO are constructed cointegrated
so ch04 always has a live example), a synthetic VIX with a 2020-style spike, and
perp funding histories with a deliberate mid-2025 inversion (so the ch08 circuit
breaker demonstrably fires). OHLCV is generated at import; the text fixtures
(headlines/transcripts/flow) are committed JSON.

### News novelty hash

Approximates "top-5 nouns and verbs" with a stopword-filtered top-5
content-token hash, the "simple hash" ch06 itself recommends starting with.
Because the fixture stream is curated, the CLI notes that a raw production feed
would reject ~70–80% of headlines.

### News same-bar round trips

Emit both an entry and an exit intent, which is what makes the ch09 netting
events observable at daily-bar granularity in the allocator demo.

### Basis-trade order shape

ch08's `signal()` returns a single `Order` whose `meta` carries both legs, the
book's signature is `Optional[Order]` while the trade itself has two legs (spot
long + perp short).

### Live-order paths

All three broker live calls, Alpaca (alpaca-py), IBKR (ib_async), crypto
(ccxt), are implemented behind lazy imports and the full ch02 safety gate, and
are exercised by positive armed-live tests using fake adapters (no network, no
credentials). Real trading still needs Gateway/credentials/SDKs, and the IBKR
futures contract month + listing exchange must be confirmed per Appendix A5.
Paper mode, the default and primary supported surface, never touches any of
them.

### Fees the book refuses to hard-code

The Alpaca option contract fee and similar are read from env/config with loud
"verify at the source" comments; `VERIFIED_ALPACA_OPTION_FEE` keeps the book's
name.

---

**Every number in this repository is computed on synthetic sample data. It is
illustrative of the mechanics only: not real, not historical, not predictive.
See [DISCLAIMER.md](DISCLAIMER.md).**
