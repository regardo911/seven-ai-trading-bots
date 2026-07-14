"""Root conftest: makes top-level packages importable and enforces the
offline test contract — tests must pass with no API keys in the environment."""

import os

import pytest

_KEYS = [
    "ANTHROPIC_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "DISCORD_WEBHOOK_URL",
    "BINANCE_API_KEY",
    "BINANCE_SECRET_KEY",
    "BYBIT_API_KEY",
    "BYBIT_SECRET_KEY",
    "FMP_API_KEY",
    "UNUSUAL_WHALES_API_KEY",
]


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    """Strip every provider credential so the offline paths are what's tested."""
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture(autouse=True)
def _reset_live_mode():
    """live_mode must never leak across tests."""
    import framework

    framework.live_mode = False
    yield
    framework.live_mode = False


@pytest.fixture()
def clean_env():
    env = {k: v for k, v in os.environ.items() if k not in _KEYS}
    return env
