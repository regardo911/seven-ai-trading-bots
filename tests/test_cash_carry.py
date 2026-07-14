"""ch08: entry threshold math, three-condition exit, allocation caps."""

from strategies import cash_carry as cc


def test_annualized_entry_floor_math():
    # ch08: 0.03% x 3 settlements x 365 = 32.85% annualized.
    assert abs(cc.annualized(0.0003) - 0.3285) < 1e-9


def _snap(rate: float, exchange="binance", symbol="BTC"):
    return {"fundingRate": rate, "exchange": exchange,
            "symbol": f"{symbol}/USDT:USDT", "indexPrice": 60_000.0}


def test_entry_requires_threshold():
    assert cc.signal(_snap(0.0002)) is None
    order = cc.signal(_snap(0.0004))
    assert order is not None
    assert order.meta["basis_trade"] is True
    assert order.meta["legs"]["perp"]["side"] == "sell"


def test_no_duplicate_position_per_market():
    open_positions = [{"exchange": "binance", "symbol": "BTC", "notional": 10_000}]
    assert cc.signal(_snap(0.0004), open_positions) is None


def test_exchange_allocation_cap():
    # 50% of default 100K capital = 50K max on one exchange.
    open_positions = [
        {"exchange": "binance", "symbol": "ETH", "notional": 25_000},
        {"exchange": "binance", "symbol": "SOL", "notional": 24_000},
    ]
    assert cc.signal(_snap(0.0004), open_positions) is None


def test_should_unwind_three_conditions_plus_breaker():
    pos = {"notional": 10_000}
    assert cc.should_unwind(pos, funding_rate=0.0004, basis=0.002) is None
    assert cc.should_unwind(pos, 0.00004, 0.002) == "funding_mean_reverted"
    assert cc.should_unwind(pos, 0.0004, 0.0003) == "basis_converged"
    assert cc.should_unwind(pos, -0.0001, 0.002) == "inversion_circuit_breaker"
