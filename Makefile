.PHONY: install install-core check demo-ch03 demo-ch09 realism demo test lint backtest clean

# Full install (book Appendix A2 pins). For the minimal offline core only,
# use `make install-core`.
install:
	pip install -r requirements.txt

install-core:
	pip install -e ".[dev]"

# ---------------------------------------------------------------------------
# First run? Do these in order. All offline — no API keys, no network.
# START_HERE.md walks the same path with the expected output.
#   make check       # is the chassis wired?  (Appendix A7 smoke test)
#   make demo-ch03   # read ONE mechanic: a signal day and a no-signal day
#   make demo-ch09   # the ch09 allocator alone, with a concentration warning
#   make realism     # gross-to-net: what fees/slippage/inference do to edges
#   make test        # the full offline suite
# ---------------------------------------------------------------------------

check:
	python examples/smoke_test.py

demo-ch03:
	python examples/demo_ch03.py

demo-ch09:
	python examples/demo_ch09.py

# The ch11 realism layer across all six strategies (Appendix A6).
realism:
	python -m framework.backtest_all --realism-pass --regime-breakdown

# Everything in one pass (book Appendix A4: "run make demo on the whole
# framework"). This proves the plumbing end to end; the synthetic numbers it
# prints are for PLUMBING ONLY, not an edge — for your FIRST read prefer
# `make demo-ch03`, which teaches one clear mechanic.
demo:
	@echo "-- make demo runs all 7 bots on SYNTHETIC data: a plumbing check, not an edge."
	@echo "-- First time here? 'make check && make demo-ch03' teaches one clear mechanic."
	python examples/smoke_test.py
	python -m strategies.trend --paper --instruments SPY,QQQ,ES,GC
	python -m framework.allocator --paper --strategies all --capital 100000

test:
	pytest -q

lint:
	ruff check .

# Alias kept for the book's Appendix A6 command surface.
backtest: realism

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ build dist *.egg-info
