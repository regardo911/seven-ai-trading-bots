"""Appendix B bench strategies: entries, exits, ranking."""

import pandas as pd

from framework import data
from strategies.bench import sector_rotate, vrp


def test_vrp_exit_rules():
    position = {"long_strike": 5000.0}
    assert vrp.should_close(position, spx=5400, dte=30,
                            captured_profit_pct=0.6) == "profit_take"
    assert vrp.should_close(position, spx=5400, dte=4,
                            captured_profit_pct=0.1) == "dte_exit"
    assert vrp.should_close(position, spx=4900, dte=30,
                            captured_profit_pct=0.1) == "long_strike_breached"
    assert vrp.should_close(position, spx=5400, dte=30,
                            captured_profit_pct=0.1) is None


def test_vrp_respects_spread_cap():
    assert not vrp.entry_ok(pd.Timestamp("2025-06-02"), open_spreads=3, vix=12.0)


def test_sector_rotation_ranks_and_rebalances():
    asof = pd.Timestamp(data.SIM_END)
    ranked = sector_rotate.rank_sectors(asof)
    assert len(ranked) == 11
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)
    orders = sector_rotate.signal(asof, holdings=[])
    assert len(orders) == 3
    assert all(o.side == "buy" for o in orders)
