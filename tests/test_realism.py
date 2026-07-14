"""ch11: commissions per broker per asset, and the $0.018 inference math."""

import pytest

from framework import realism


def test_commission_book_mappings():
    assert realism.commission("alpaca", "equity", 100, 10_000) == 0.0
    assert realism.commission("binance", "spot", 0, 10_000) == 10.0     # 0.1%
    assert realism.commission("binance", "futures", 0, 10_000) == 4.0   # 0.04%
    assert realism.commission("ibkr", "equity_lite", 100, 10_000) == 0.0
    assert realism.commission("ibkr", "equity_pro_fixed", 100, 0) == 0.5


def test_commission_unknown_raises():
    with pytest.raises(ValueError, match="unknown broker/asset"):
        realism.commission("robinhood", "equity", 1, 1)


def test_inference_cost_book_numbers():
    # ch11: $0.018/inference; a 20-inference news trade costs $0.36, not $0.50.
    assert realism.inference_cost(1) == pytest.approx(0.018)
    assert realism.inference_cost(20) == pytest.approx(0.36)
    assert realism.inference_cost(10, model="opus") == pytest.approx(0.306)


def test_apply_realism_reduces_gross():
    trade = realism.Trade(strategy="news", asset_class="equity_liquid",
                          broker="alpaca", asset_type="equity",
                          qty=50, notional=10_000, inference_count=20)
    net = realism.apply_realism(50.0, trade)
    assert net < 50.0
    costs = realism.trade_costs(trade)
    assert costs["slippage"] == pytest.approx(20.0)  # 0.20% conservative ceiling
    assert costs["inference"] == pytest.approx(0.36)


def test_unknown_asset_class_raises():
    with pytest.raises(ValueError, match="unknown asset class"):
        realism.slippage_cost("beanie_babies", 1_000)
