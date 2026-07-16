# Seven AI Trading Bots

**Seven trading bots, one disciplined chassis. Claude builds the bot; deterministic Python rules execute; you own the strategy.**

Companion reference implementation for the book [**Use Claude to Build 7 AI Trading Bots**](https://youcanbuildthings.com/books/claude-7-trading-bots) (AI Trading Bot Playbooks, Book 2) from [youcanbuildthings.com](https://youcanbuildthings.com), the repository its Appendix A4 points to.

[![ci](https://github.com/regardo911/seven-ai-trading-bots/actions/workflows/ci.yml/badge.svg)](https://github.com/regardo911/seven-ai-trading-bots/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![style](https://img.shields.io/badge/style-ruff-261230)
![mode](https://img.shields.io/badge/default-paper--mode-success)
![advice](https://img.shields.io/badge/⚠_not_financial_advice-educational_only-red)

> **⚠️ Not financial advice.** This is educational software. Trading involves substantial
> risk of loss, backtests here run on **synthetic sample data**, and nothing in this
> repository is a recommendation to trade anything. Paper (simulated) mode is the default
> everywhere; live trading requires deliberate code-level opt-in and is entirely at your own
> risk. **Read [DISCLAIMER.md](DISCLAIMER.md) before doing anything else.**

**7 strategies · 3 bench swaps · 5 market regimes · walk-forward + realism layer · runs offline with zero API keys**

---

## 60-second quickstart

No API keys. No brokerage account. No network beyond `pip`. Full walk-through
with expected output: **[START_HERE.md](START_HERE.md)**.

```bash
git clone https://github.com/regardo911/seven-ai-trading-bots
cd seven-ai-trading-bots
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # minimal offline core; or `pip install -r requirements.txt` for the full book stack

make check        # 1. is the chassis wired? (Appendix A7 smoke test)
make demo-ch03    # 2. read ONE mechanic: a trend BUY day and a WAIT day, with the numbers
make demo-ch09    # 3. the allocator, honestly captioned (synthetic weights are not an edge)
make realism      # 4. gross-to-net: what fees, slippage, and inference cost do to every edge
make test         # 5. the full offline suite
```

`make check` proves the chassis in three lines:

```
PASS
{'account_number': 'PA1234567', 'cash': '100000.00', 'buying_power': '200000.00', ...}
[discord:offline] framework smoke-test: ok
```

Then `make demo-ch03` shows the Chapter 3 rule making one clear decision each way:

```
[SIGNAL]   2021-11-15  close 610.06  |  prior-20d high 599.28  |  200-day SMA 530.72
           -> close cleared BOTH gates, so the rule fires: BUY 36 SPY
[NO SIGNAL] 2022-06-01  close 477.28  |  prior-20d high 529.73  |  200-day SMA 577.63
           -> close did NOT clear the prior-20d high and/or the 200-SMA, so the rule says WAIT
```

That is the whole idea in one screen: Claude built the rule, deterministic
Python decides BUY vs WAIT, and you can read exactly why. `make demo` runs all
seven bots at once (the book's Appendix A4 command), a full plumbing check, but
its numbers are **synthetic sample data, not an edge**; prefer the staged path
above for your first read.

## The seven bots

| # | Bot | Chapter | What it does | Claude live? | Docs |
|---|-----|---------|--------------|--------------|------|
| 1 | **Trend** | ch03 | Donchian-20 breakouts + 200-SMA filter + 3×ATR(14) trail on SPY/QQQ/ES/GC | No | [docs](docs/strategies/trend.md) |
| 2 | **Pairs** | ch04 | Engle-Granger cointegration, Z ±2 entries, 20-day time-stop, VIX-30 filter | No | [docs](docs/strategies/pairs.md) |
| 3 | **Earnings (PEAD)** | ch05 | Claude reads the transcript → deterministic 5-field scorer → 5-day drift hold | ~1 call/event | [docs](docs/strategies/earnings.md) |
| 4 | **News** | ch06 | novelty filter → Claude classifies → deterministic gate (confidence ≥7 AND account state) | heavy | [docs](docs/strategies/news.md) |
| 5 | **Flow** | ch07 | whale-mirror gated by delta budget, gamma cap, IV-crush filter, theta sweep | No | [docs](docs/strategies/flow.md) |
| 6 | **Cash-and-carry** | ch08 | delta-neutral funding-rate arb on Binance/Bybit perps with an inversion circuit breaker | No | [docs](docs/strategies/cash_carry.md) |
| 7 | **Allocator** | ch09 | risk-parity sizing, 90-day correlation drops, drawdown breakers, intent netting | governance only | [docs](docs/strategies/allocator.md) |

**Bench (Appendix B, for the ch12 rotation):** [volatility risk premium](docs/strategies/vrp.md) · [FX trend](docs/strategies/fx_trend.md) · [sector momentum rotation](docs/strategies/sector_rotate.md)

## Architecture

> **Claude builds the bot. Deterministic Python rules execute the bot. The human owns the strategy.**

Claude classifies context (headlines, transcripts) into strict JSON. Python
computes everything numeric: `position size = risk dollars / stop distance`,
stops, gates, netting. Five of the seven bots make **zero** inference calls on
the runtime trade path; the two that call Claude per trade, **PEAD** (ch05) and
**News** (ch06), have their token cost (~$0.018/inference) netted out of every
backtest by the realism layer. The allocator (ch09) uses Claude only in weekly
governance review, off the trade path. Full picture with diagram:
[docs/architecture.md](docs/architecture.md).

```
strategies/{trend,pairs,earnings,news,flow,cash_carry}.py   + bench/
framework/{brokers,claude,discord,data,allocator,walk_forward,realism,attribution,metrics}.py
backtest/{common,trend,pairs,earnings,news,flow,cash_carry}.py -> results/*.json
```

## Run each bot (Appendix A3 commands)

```bash
python -m strategies.trend      --paper --instruments SPY,QQQ,ES,GC
python -m strategies.pairs      --paper --basket sectors
python -m strategies.earnings   --paper --transcript-provider fmp
python -m strategies.news       --paper --feeds bloomberg,reuters,fed
python -m strategies.flow       --paper --flow-provider unusualwhales
python -m strategies.cash_carry --paper --exchanges binance,bybit --instruments BTC,ETH,SOL
python -m framework.allocator   --paper --strategies all --capital 100000

# backtests (per-regime tables; add the ch11 realism pass across all six):
python -m strategies.trend --backtest --regime-breakdown
python -m framework.backtest_all --realism-pass --regime-breakdown

# the ch10 independent-verification tool:
python tools/hallucination_check.py backtest/results/sample_trend.json
```

Every command runs offline against deterministic synthetic fixtures. Backtest
JSONs land in `backtest/results/` clearly labeled
`"synthetic_data": true`: **illustrative mechanics, not performance claims.**

## Going live safely (read this twice)

This repo **cannot** go live by accident:

1. `framework.live_mode` defaults to `False`. Every order path checks it.
2. The only way to flip it is a **code change**:
   `framework.set_live_mode(True, confirm="I_HAVE_REVIEWED_THIS")`: not a
   config file, not an env var, not a CLI flag. `--live` alone prints a warning
   and exits.
3. Real credentials (`.env`) and the optional broker SDKs
   (`pip install -e ".[brokers,llm]"`) are separate, additional steps.

The book's chapter 12 ladder is the process: **Stage 1** paper-only, all 7,
30 days → **Stage 2** live at 1% of target capital → **Stage 3** 5% →
**Stage 4** 25% for 60 days → **Stage 5** full capital with monthly review,
each rung with explicit go/no-go criteria (trade counts, Sharpe floors,
live-vs-paper gap ≤ 25%, breaker drills). Skipping rungs is how paper heroes
blow up live accounts. Your capital, your jurisdiction, your decision.

## Configuration

Copy `.env.example` → `.env`. **Every variable is optional**: the demo needs none.

| Variable | Unlocks | Without it |
|---|---|---|
| `ANTHROPIC_API_KEY` | real Claude classification (ch05/ch06) | deterministic offline stub (announced) |
| `ALPACA_API_KEY/SECRET_KEY` | real Alpaca paper account | built-in simulated $100k ledger |
| `DISCORD_WEBHOOK_URL` | real trade notifications | console echo |
| `BINANCE/BYBIT_API_KEY/...` | live funding snapshots (ch08) | synthetic funding history |
| `FMP_API_KEY`, `UNUSUAL_WHALES_API_KEY` | real transcript/flow feeds | committed fixtures |
| `ALPACA_OPTION_FEE_PER_CONTRACT` | your verified fee (ch11 refuses to hard-code it) | 0.65 placeholder |

`--live-data` on any CLI swaps synthetic bars for yfinance daily bars (needs
`pip install -e ".[data]"`).

## Testing & CI

```bash
make test    # 79 offline, deterministic tests - no keys, no network
make lint    # ruff
```

CI (GitHub Actions, Python 3.11/3.12) installs **only the core deps** and runs
the full suite plus the offline demo, proving the zero-key claim on every push.
The test suite includes a no-network guard, a `--live`-is-refused test, and the
book's worked examples as assertions (8 shares; 4 contracts; $0.36/trade).

## Errata & reconciliation

The printed book is a fixed snapshot; this repo is live. Where the two disagree,
**[ERRATA.md](ERRATA.md) is the tie-breaker**: confirmed corrections to the
book (the ch03 Donchian window, the ch07 delta-budget formula, the ch06/ch11
runtime-inference count) plus the places this repo has moved past the pages.
Repo code changes are in [CHANGELOG.md](CHANGELOG.md).

## Contributing

Fixes and clarity welcome; new strategies are out of scope. This mirrors the
book on purpose. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Further reading (Appendix C)

- [ccxt documentation](https://github.com/ccxt/ccxt), authoritative for the crypto wiring
- [QuantConnect LEAN](https://github.com/quantconnect/Lean), the natural upgrade path if you outgrow this chassis
- Marcos López de Prado, *Advances in Financial Machine Learning*, the walk-forward authority (ch10)
- Rob Hyndman, [*Forecasting: Principles and Practice*](https://otexts.com/fpp3/): free, the time-series methodology bible
- [Anthropic's Claude docs](https://docs.claude.com) + [MCP](https://modelcontextprotocol.io), pricing/models/SDK shift; check periodically
- r/algotrading · r/quant · Quantitative Finance Stack Exchange · NBER/SSRN for bench-strategy research

## License

[MIT](LICENSE) © 2026 [youcanbuildthings.com](https://youcanbuildthings.com)

---

*This project is educational software accompanying a book. It is **not**
financial advice, **not** a trading service, and **not** a performance claim;
all bundled results are computed on synthetic sample data. Markets can take
your money faster than any book can explain why.*
