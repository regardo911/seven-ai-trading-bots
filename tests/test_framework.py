"""The ch02 safety rule: live requires a deliberate, confirmed code change."""

import pytest

import framework
from framework.brokers import AlpacaBroker


def test_live_mode_defaults_false():
    assert framework.live_mode is False


def test_set_live_mode_requires_confirmation():
    with pytest.raises(RuntimeError, match="explicit confirmation"):
        framework.set_live_mode(True)
    with pytest.raises(RuntimeError):
        framework.set_live_mode(True, confirm="yes please")
    assert framework.live_mode is False


def test_set_live_mode_with_confirmation():
    framework.set_live_mode(True, confirm="I_HAVE_REVIEWED_THIS")
    assert framework.live_mode is True
    framework.set_live_mode(False)
    assert framework.live_mode is False


def test_live_broker_refused_without_live_mode():
    with pytest.raises(RuntimeError, match="live_mode is False"):
        AlpacaBroker(paper=False)
