# Changelog

All notable changes to this project are documented here.

## [0.1.2] — 2026-07-14

### Added
- **Staged first-run path.** `START_HERE.md` plus new `make` targets: `check`
  (chassis smoke test), `demo-ch03` (`examples/demo_ch03.py` — one trend BUY and
  one WAIT day, with the numbers behind each), `demo-ch09`
  (`examples/demo_ch09.py` — the allocator with a per-strategy cap and a
  concentration warning), and `realism` (gross-to-net across all strategies).
  Your first success now teaches one clear mechanic instead of the whole portfolio.
- **Positive armed-live routing tests** (`tests/test_live_routing.py`): with
  live mode armed in source, orders route to the broker SDKs, proven against fake
  adapters — no network, no credentials.

### Changed
- **Live routing is now wired end to end.** `broker_for()` threads the paper flag,
  so an *armed* `--live` run actually reaches the live order path (it was
  unreachable before); `IBKRBroker` now implements the `ib_async` live path
  (previously a raised placeholder). Paper mode remains the default and can still
  never go live by accident.
- **`make demo`** (the book's Appendix A4 all-bots command) now prints a
  plumbing-check-only banner; prefer the staged targets above for a first read.
- **Docs:** corrected the runtime-inference framing in `docs/architecture.md`
  (five bots make zero inference on the trade path; the two per-trade callers are
  PEAD and News; the allocator is weekly governance only). Every strategy chart
  gained a "what to notice / what would break this" caption, and the allocator
  chart calls out concentration risk.

## [0.1.1] — 2026-07-06

### Added
- Visual explanation for every strategy: 10 charts in `docs/images/` (validated
  accessible palette, generated from the synthetic demo data), embedded in every
  `docs/strategies/*.md`, regenerable via `tools/generate_docs_charts.py`
  (`pip install -e ".[viz]"`).

### Changed
- Project branding now references [youcanbuildthings.com](https://youcanbuildthings.com/books/claude-7-trading-bots)
  (README, LICENSE, packaging metadata, GitHub About).
- README references DISCLAIMER.md exactly once (the top callout).

## [0.1.0] — 2026-07-06

Initial public release — the reference implementation promised by Appendix A4 of
*Use Claude to Build 7 AI Trading Bots*.

### Added
- Unified framework chassis (ch02): `live_mode` safety flag, broker abstraction
  (Alpaca / IBKR / crypto), Claude SDK wrapper with offline stub, Discord notifier,
  metrics, synthetic regime-aware data layer.
- All seven strategies: trend (ch03), pairs (ch04), earnings PEAD (ch05), news
  sentiment (ch06), options flow with Greeks (ch07), crypto cash-and-carry (ch08),
  portfolio allocator (ch09).
- Three bench strategies (Appendix B): volatility risk premium, FX trend,
  sector momentum rotation.
- Walk-forward backtest template (ch10), realism layer (ch11), per-strategy
  backtests with per-regime breakdowns, `framework.backtest_all` orchestrator.
- Offline-first design: zero API keys required; deterministic synthetic fixtures.
- Docs: per-strategy guides, per-prompt guides, architecture, hallucination checklist.
- Tests (offline, deterministic), GitHub Actions CI, examples, Makefile.
