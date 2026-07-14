"""ch06: novelty hashing, and every clause of the deterministic gate."""

from strategies import news


def test_novelty_rejects_syndicated_duplicate():
    first = "Fed officials signal rates will stay on hold as inflation cools toward target"
    wire_pickup = ("Fed officials signal rates on hold as inflation cools "
                   "toward target, patience stressed")
    seen = [news._headline_hash(first)]
    assert not news.is_novel(wire_pickup, seen)
    assert news.is_novel("Gold surges to record high on safe-haven flows", seen)


def _c(**kw):
    base = {"impact": 8, "direction": "long", "asset": "SPY",
            "confidence": 8, "rationale": "test"}
    base.update(kw)
    return base


def test_gate_confidence_floor():
    assert not news.should_trade(_c(confidence=6), news.AccountState())
    assert news.should_trade(_c(confidence=7), news.AccountState())


def test_gate_skip_and_none_asset():
    assert not news.should_trade(_c(direction="skip"), news.AccountState())
    assert not news.should_trade(_c(asset="none"), news.AccountState())


def test_gate_position_cap():
    state = news.AccountState(open_news_positions=3)
    assert not news.should_trade(_c(), state)


def test_gate_drawdown_breaker():
    state = news.AccountState(equity_drawdown=0.06)  # >5% MTD
    assert not news.should_trade(_c(), state)


def test_order_sizing_uses_atr_stop():
    order = news.build_order(_c(), asof="2025-06-12")
    assert order is not None
    assert order.symbol == "SPY" and order.side == "buy"
    assert order.meta["stop_distance"] > 0
