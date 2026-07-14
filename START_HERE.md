# Start here

New to this repo? Do these five steps in order. Every one runs **offline** — no
API keys, no brokerage account, no network beyond `pip`. The goal is that your
*first* success teaches one clear mechanic, not the whole factory at once.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # minimal offline core (or `pip install -r requirements.txt` for the full book stack)
```

### 1. Is the chassis wired? — `make check`
Runs the Appendix A7 smoke test. You should see `PASS`, a paper account dict
(`'account_number': 'PA1234567'`, `'cash': '100000.00'`), and
`[discord:offline] framework smoke-test: ok`. If those three are right, every
strategy will run.

### 2. Read ONE mechanic — `make demo-ch03`
The Chapter 3 trend bot on synthetic SPY history, showing **one BUY day and one
WAIT day** with the exact three numbers behind each (close, prior-20-day high,
200-day SMA). This is the whole idea of the book in one screen: Claude built the
rule; deterministic Python decides BUY vs WAIT; you can read exactly why. Most
days are WAIT days — that is the strategy.

### 3. See why "the allocator found an edge" is a trap — `make demo-ch09`
The Chapter 9 allocator on all six bots. It prints the risk-parity weights, then
**warns you** that on synthetic data the biggest weight is an artifact of one
bot's fake low volatility, not a real edge — and shows what a per-strategy cap
would do instead. Read the caption, not the P&L.

### 4. Watch edges shrink — `make realism`
The Chapter 11 realism layer across all strategies: gross vs net after fees,
slippage, latency, and Claude inference cost. This is the most important lesson
in the repo — a "great" gross backtest can be a losing strategy after costs.

### 5. Prove it holds — `make test`
The full offline suite (no keys, no network), including a no-network guard, the
`--live`-is-refused safety test, positive armed-live routing tests (fake
adapters), and the book's worked examples as assertions (8 shares, 4 contracts,
$0.36/trade).

---

## Then: read a strategy from its chapter

Each bot maps to one chapter and has a `strategies/<name>.py` module, a
`docs/strategies/<name>.md` guide (with a chart and a "what to notice / what
would break this" caption), and a paper CLI. Start from the chapter you care
about — you do **not** need to understand the whole repo first:

| Start at | Bot | Chapter | Paper command |
|---|---|---|---|
| here | Trend | ch03 | `python -m strategies.trend --paper --instruments SPY,QQQ,ES,GC` |
| | Pairs | ch04 | `python -m strategies.pairs --paper --basket sectors` |
| | Earnings (PEAD) | ch05 | `python -m strategies.earnings --paper --transcript-provider fmp` |
| | News | ch06 | `python -m strategies.news --paper --feeds bloomberg,reuters,fed` |
| | Flow | ch07 | `python -m strategies.flow --paper --flow-provider unusualwhales` |
| | Cash-and-carry | ch08 | `python -m strategies.cash_carry --paper --exchanges binance,bybit` |
| | Allocator | ch09 | `python -m framework.allocator --paper --strategies all --capital 100000` |

`make demo` runs all seven at once — it is the book's Appendix A4 command and a
full plumbing check, but the numbers it prints are **synthetic sample data, not
an edge**. Prefer steps 2–4 above for your first read.

## Going live is a deliberate, separate decision

Paper mode is the default everywhere. Live trading is unreachable by accident:
`framework.live_mode` is `False` and can only be flipped by a **code change**
(`framework.set_live_mode(True, confirm="I_HAVE_REVIEWED_THIS")`), then real
credentials, then the optional broker SDKs. `--live` alone prints a warning and
exits. See the README's "Going live safely" section and DISCLAIMER.md.

**Nothing here is financial advice.** All bundled results are computed on
synthetic sample data. Read [DISCLAIMER.md](DISCLAIMER.md) before doing anything.
