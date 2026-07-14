"""Offline Claude stub: schema-valid, deterministic, keyless."""

import json

from framework import claude
from strategies.earnings import PROMPT as EARNINGS_PROMPT
from strategies.news import PROMPT as NEWS_PROMPT


def test_smoke_prompt_returns_pass():
    assert claude.classify("Reply with the single word PASS.") == "PASS"


def test_earnings_stub_schema_valid():
    text = ("We beat consensus and are raising guidance. Margin is expanding. "
            "Demand is strong demand across segments.")
    raw = claude.classify(EARNINGS_PROMPT + text)
    c = json.loads(raw)
    assert c["headline_result"] == "beat"
    assert c["guidance_change"] == "raised"
    assert c["margin_direction"] == "expanding"
    assert c["sector_tone"] == "bullish"
    assert 1 <= c["confidence"] <= 10


def test_news_stub_schema_valid():
    raw = claude.classify(NEWS_PROMPT + "Fed cuts rates, cites cooling inflation")
    c = json.loads(raw)
    assert c["direction"] in {"long", "short", "skip"}
    assert c["asset"] in {"SPY", "QQQ", "EUR/USD", "GLD", "BTC", "none"}
    assert 1 <= c["impact"] <= 10 and 1 <= c["confidence"] <= 10


def test_stub_is_deterministic():
    prompt = NEWS_PROMPT + "Gold surges to record high on safe-haven flows"
    assert claude.classify(prompt) == claude.classify(prompt)
