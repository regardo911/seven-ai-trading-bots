"""Claude SDK wrapper with a deterministic offline stub (ch02 / ch05 / ch06).

With ``ANTHROPIC_API_KEY`` set (and the ``anthropic`` package installed) the
``classify()`` helper calls the real API exactly as the book wires it. Without
a key — the default, keyless experience — a deterministic keyword-based stub
returns plausible, schema-valid classifications so the earnings and news
pipelines run end to end offline. The stub announces itself once per process.

The architecture rule this module serves (ch06): Claude classifies; it never
computes position sizes, stops, or orders. Those are deterministic Python.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

import json
import os
import re

from framework.metrics import inference_tracker

_stub_notice_shown = False


def _stub_notice() -> None:
    global _stub_notice_shown
    if not _stub_notice_shown:
        print("[claude:offline-stub] no ANTHROPIC_API_KEY set - using the "
              "deterministic offline classifier (schema-valid, keyword-based).")
        _stub_notice_shown = True


def classify(prompt: str, model: str = "claude-sonnet-4-6", max_tokens: int = 200) -> str:
    """Send ``prompt`` to Claude (or the offline stub) and return raw text.

    Mirrors the book's helper: ``max_tokens`` is capped small on purpose so a
    structured-output prompt cannot grow prose around its JSON (ch05).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            from anthropic import Anthropic
        except ImportError:
            print("[claude] ANTHROPIC_API_KEY is set but the 'anthropic' package "
                  "is not installed (pip install 'seven-ai-trading-bots[llm]'). "
                  "Falling back to the offline stub.")
        else:  # pragma: no cover - live API path, exercised manually
            client = Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            inference_tracker.record(model, len(prompt) // 4, len(text) // 4)
            return text
    _stub_notice()
    text = _offline_classify(prompt)
    inference_tracker.record(model, len(prompt) // 4, len(text) // 4)
    return text


# ------------------------------ offline stub -------------------------------

def _offline_classify(prompt: str) -> str:
    if "single word PASS" in prompt:
        return "PASS"
    if '"headline_result"' in prompt:
        return _classify_transcript(prompt.split("TRANSCRIPT:")[-1])
    if '"impact"' in prompt:
        return _classify_headline(prompt.split("HEADLINE:")[-1])
    return "PASS"


def _count_hits(text: str, words: list[str]) -> int:
    return sum(1 for w in words if re.search(r"\b" + re.escape(w), text))


def _classify_transcript(text: str) -> str:
    t = text.lower()
    if "missed" in t or re.search(r"\bmiss\b", t):
        headline = "miss"
    elif "beat" in t:
        headline = "beat"
    else:
        headline = "in_line"

    if "withdraw" in t:
        guidance = "withdrawn"
    elif "raising" in t or "raised" in t or "raise" in t:
        guidance = "raised"
    elif "cutting" in t or re.search(r"\bcut\b", t) or "lowered" in t:
        guidance = "cut"
    else:
        guidance = "maintained"

    if "expand" in t:
        margin = "expanding"
    elif "contract" in t or "compress" in t:
        margin = "contracting"
    else:
        margin = "flat"

    bull = _count_hits(t, ["strong demand", "record", "accelerat", "tailwind", "upbeat"])
    bear = _count_hits(t, ["soft", "weak", "headwind", "cautious", "slowdown"])
    tone = "bullish" if bull > bear else "bearish" if bear > bull else "neutral"

    cues = sum([headline != "in_line", guidance != "maintained",
                margin != "flat", tone != "neutral"])
    mixed = (headline == "beat" and guidance == "cut") or (bull > 0 and bear > 0)
    confidence = 5 if mixed else min(5 + cues, 9)

    return json.dumps({
        "headline_result": headline, "guidance_change": guidance,
        "margin_direction": margin, "sector_tone": tone, "confidence": confidence,
    })


_ASSET_CUES = [
    (["nasdaq", "tech ", "chip", "semiconductor", "software", " ai "], "QQQ"),
    (["gold"], "GLD"),
    (["bitcoin", "btc", "crypto"], "BTC"),
    (["euro", "ecb", "eurozone"], "EUR/USD"),
    (["fed", "fomc", "rate", "cpi", "inflation", "jobs", "payroll", "tariff",
      "treasury", "gdp"], "SPY"),
]
_BULL = ["cuts", "cut rates", "cool", "cooled", "cools", "beat", "beats", "surge",
         "rally", "rallies", "dovish", "record inflow", "strong", "soft landing",
         "falls below", "eases"]
_BEAR = ["hike", "hikes", "raises rates", "hot", "hotter", "miss", "misses",
         "plunge", "selloff", "sell-off", "hawkish", "sticky", "weak", "jumps",
         "spikes", "warns", "escalat"]


def _classify_headline(text: str) -> str:
    t = " " + text.lower().strip() + " "
    asset = "none"
    for cues, mapped in _ASSET_CUES:
        if any(c in t for c in cues):
            asset = mapped
            break

    bull = _count_hits(t, _BULL)
    bear = _count_hits(t, _BEAR)
    direction = "long" if bull > bear else "short" if bear > bull else "skip"
    if asset == "none":
        direction = "skip"

    impact = 5
    if any(w in t for w in ["fed", "fomc", "rate decision", "rate cut", "rate hike"]):
        impact += 3
    elif any(w in t for w in ["cpi", "inflation", "jobs", "payroll"]):
        impact += 2
    if any(w in t for w in ["record", "surge", "plunge"]):
        impact += 1
    if any(w in t for w in ["celebrity", "rumor", "denies", "movie"]):
        impact = 3
    impact = min(impact, 9)

    if direction == "skip":
        confidence = 4
    elif impact >= 7:
        confidence = 8
    else:
        confidence = 6

    return json.dumps({
        "impact": impact, "direction": direction, "asset": asset,
        "confidence": confidence,
        "rationale": "offline stub: keyword-based classification for the demo",
    })
