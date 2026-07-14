"""ch05: deterministic scorer (verbatim thresholds) + offline pipeline."""

import pandas as pd

from strategies import earnings


def _c(**kw):
    base = {"headline_result": "in_line", "guidance_change": "maintained",
            "margin_direction": "flat", "sector_tone": "neutral", "confidence": 9}
    base.update(kw)
    return base


def test_low_confidence_always_skips():
    c = _c(headline_result="beat", guidance_change="raised",
           margin_direction="expanding", confidence=6)
    assert earnings.score_classification(c) == ("skip", 0.0)


def test_three_bullish_zero_bearish_full_size():
    c = _c(headline_result="beat", guidance_change="raised",
           margin_direction="expanding")
    assert earnings.score_classification(c) == ("long", 1.0)


def test_two_bullish_half_size():
    c = _c(headline_result="beat", guidance_change="raised")
    assert earnings.score_classification(c) == ("long", 0.5)


def test_mixed_signals_skip():
    c = _c(headline_result="beat", guidance_change="cut",
           margin_direction="expanding", sector_tone="bearish")
    assert earnings.score_classification(c) == ("skip", 0.0)


def test_three_bearish_full_short():
    c = _c(headline_result="miss", guidance_change="cut",
           margin_direction="contracting")
    assert earnings.score_classification(c) == ("short", 1.0)


def test_offline_pipeline_end_to_end():
    date = pd.Timestamp("2025-02-06")  # ACME beat-and-raise fixture
    orders = earnings.signal(date)
    assert len(orders) == 1
    order = orders[0]
    assert order.symbol == "ACME"
    assert order.meta["direction"] == "long"
    assert order.meta["instrument"] in {"equity", "option"}
    assert order.meta["hold_days"] == 5
