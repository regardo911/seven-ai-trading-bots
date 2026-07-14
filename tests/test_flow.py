"""ch07: the four Greek layers, including the book's worked sizing example."""

from strategies import flow


def test_delta_budget_matches_book_worked_example():
    # ch07: 0.50-delta contract on a $10K account at the 0.20 budget -> 4.
    assert flow.position_size_by_delta(10_000, 0.50) == 4


def test_dte_size_multiplier_tiers():
    assert flow.dte_size_multiplier(7) == 0.25    # weeklies at 25%
    assert flow.dte_size_multiplier(45) == 1.0
    assert flow.dte_size_multiplier(180) == 1.0


def test_gamma_cap_scales_with_capital():
    # cap = 50 per $100K: five 10-gamma-point positions saturate it.
    assert flow.gamma_cap_ok([10, 10, 10, 10], 9.9, 100_000)
    assert not flow.gamma_cap_ok([10, 10, 10, 10], 10.1, 100_000)


def test_iv_crush_filter_symmetric_at_80():
    assert flow.iv_filter_ok(79.9)
    assert not flow.iv_filter_ok(80.0)


def test_clean_directional_prefilters():
    base = {"both_sides": False, "notional": 100_000, "dte": 45}
    assert flow.is_clean_directional(base)[0]
    assert not flow.is_clean_directional({**base, "both_sides": True})[0]
    assert not flow.is_clean_directional({**base, "notional": 45_000})[0]
    assert not flow.is_clean_directional({**base, "dte": 240})[0]


def test_signal_mirrors_clean_event():
    event = {"ts": "2025-01-08", "ticker": "SPY", "side": "call", "dte": 45,
             "notional": 2_000_000, "delta": 0.52, "gamma": 0.045,
             "theta": -0.28, "premium": 6.4, "iv_percentile": 42,
             "both_sides": False}
    order = flow.signal(event, account_equity=100_000)
    assert order is not None
    assert order.meta["option_type"] == "call"
    assert order.qty >= 1


def test_theta_sweep_close():
    assert flow.should_close({}, theta_per_day=-0.6,
                             progress_toward_strike=0.2, dte=30) == "theta_sweep"
    assert flow.should_close({}, theta_per_day=-0.6,
                             progress_toward_strike=0.7, dte=30) is None
    assert flow.should_close({}, theta_per_day=-0.1,
                             progress_toward_strike=0.0, dte=2) == "final_dte_stop"
