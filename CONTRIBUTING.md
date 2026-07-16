# Contributing

Thanks for your interest! This repository is the companion reference implementation for the book
*Use Claude to Build 7 AI Trading Bots*. That shapes what contributions fit.

## Scope

**Welcome:**
- Bug fixes, correctness fixes, and clearer error messages
- Documentation improvements and typo fixes
- Test coverage and CI improvements
- Compatibility fixes when a pinned dependency ships a breaking change

**Out of scope (please don't open PRs for these):**
- New strategies, indicators, or "improvements" beyond the book's 7 core + 3 bench strategies.
  This repo intentionally mirrors the book; the book itself warns that every overlay you add is
  an overfit waiting to happen.
- Anything that weakens the safety defaults (paper-mode default, `set_live_mode` confirmation,
  no-single-flag-goes-live rule).
- Committing real credentials, real account data, or non-synthetic market data.

## Development setup

```bash
git clone https://github.com/regardo911/seven-ai-trading-bots
cd seven-ai-trading-bots
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # core + pytest + ruff (offline-capable)
make test                      # must pass with NO network and NO API keys
make lint
```

The test suite is deliberately offline and deterministic. If your change makes a test require
network access or an API key, the change is wrong for this repo.

Extending the internals? Skim [GOTCHAS.md](GOTCHAS.md) first: the traps we already hit.

## Pull requests

1. One logical change per PR.
2. `make lint && make test` green.
3. If you touch strategy logic, cite the book chapter/section your change is faithful to.
4. Keep the educational disclaimers intact.

## Conduct

Be kind, be specific, assume good faith.

---

*Everything here is educational. Nothing is financial advice: see [DISCLAIMER.md](DISCLAIMER.md).*
