"""The nine Appendix A3 commands run offline, keyless, exit 0 (spec §3)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

COMMANDS = [
    (["strategies.trend", "--paper", "--instruments", "SPY,QQQ,ES,GC"], "trend"),
    (["strategies.trend", "--backtest", "--regime-breakdown"], "trend backtest"),
    (["strategies.pairs", "--paper", "--basket", "sectors"], "pairs"),
    (["strategies.earnings", "--paper", "--transcript-provider", "fmp"],
     "fixtures processed"),
    (["strategies.news", "--paper", "--feeds", "bloomberg,reuters,fed"],
     "novelty filter"),
    (["strategies.flow", "--paper", "--flow-provider", "unusualwhales"],
     "events:"),
    (["strategies.cash_carry", "--paper", "--exchanges", "binance,bybit",
      "--instruments", "BTC,ETH,SOL"], "funding"),
    (["framework.allocator", "--paper", "--strategies", "all",
      "--capital", "100000"], "PORTFOLIO DASHBOARD"),
    (["framework.backtest_all", "--realism-pass", "--regime-breakdown"],
     "SUMMARY"),
]


@pytest.mark.parametrize("argv,expect", COMMANDS,
                         ids=[" ".join(c[0][:1]) + ("-bt" if "--backtest" in c[0]
                              or "backtest_all" in c[0][0] else "")
                              for c in COMMANDS])
def test_cli_offline(argv, expect, clean_env):
    proc = subprocess.run(
        [sys.executable, "-m", *argv],
        cwd=ROOT, env=clean_env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert expect.lower() in (proc.stdout + proc.stderr).lower()


def test_live_flag_alone_is_refused(clean_env):
    proc = subprocess.run(
        [sys.executable, "-m", "strategies.trend", "--live"],
        cwd=ROOT, env=clean_env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 2
    assert "live_mode is False" in proc.stdout
