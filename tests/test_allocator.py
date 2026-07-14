"""ch09 mechanics: risk parity, breakers, netting, correlation monitor."""

import numpy as np
import pandas as pd

from framework.allocator import (
    Intent,
    StrategyState,
    correlation_check,
    drawdown_circuit,
    net_intents,
    risk_parity_weights,
)


def test_risk_parity_inverse_vol():
    # ch09 worked example: lowest-vol strategy gets the most capital.
    vols = {"trend": 0.0088, "pairs": 0.0038, "earnings": 0.0076,
            "news": 0.0101, "flow": 0.0113, "cash_carry": 0.0025}
    weights = risk_parity_weights(vols)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["cash_carry"] == max(weights.values())
    assert weights["flow"] == min(weights.values())


def test_drawdown_circuit_thresholds():
    def state(mtd_pct, sharpe=1.0):
        return StrategyState(mtd_pnl=mtd_pct * 10_000,
                             month_start_equity=10_000,
                             rolling_90d_sharpe=sharpe)

    assert drawdown_circuit(state(-0.05)) == 1.0
    assert drawdown_circuit(state(-0.16)) == 0.5          # -15% MTD: half size
    assert drawdown_circuit(state(-0.26, sharpe=0.3)) == 0.0  # -25%: zero
    assert drawdown_circuit(state(-0.26, sharpe=0.6)) == 1.0  # recovered


def test_net_intents_book_example():
    # ch09: long 100 SPY + short 60 SPY -> ONE net buy-40 order.
    intents = [Intent("trend", "SPY", 100, "buy"),
               Intent("news", "SPY", 60, "sell")]
    orders = net_intents(intents)
    assert len(orders) == 1
    assert (orders[0].symbol, orders[0].qty, orders[0].side) == ("SPY", 40, "buy")


def test_net_intents_full_cancel():
    intents = [Intent("a", "QQQ", 50, "buy"), Intent("b", "QQQ", 50, "sell")]
    assert net_intents(intents) == []


def test_correlation_check_flags_persistent_pairs():
    rng = np.random.default_rng(7)
    base = rng.normal(0, 0.01, 260)
    df = pd.DataFrame({
        "a": base,
        "b": base + rng.normal(0, 0.001, 260),   # ~identical -> flagged
        "c": rng.normal(0, 0.01, 260),           # independent -> clean
    }, index=pd.bdate_range("2024-01-01", periods=260))
    flagged = correlation_check(df, threshold=0.70, window_days=30)
    assert ("a", "b") in flagged
    assert all("c" not in pair for pair in flagged)
