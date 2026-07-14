"""Discord webhook notifier — the book's entire day-one monitoring stack (ch02).

    "Do not invent a SDK. There is no discord-sdk-trader package.
     There is requests.post." — ch02

Without ``DISCORD_WEBHOOK_URL`` configured, notifications print to the console
so the offline demo works with zero setup. Returns ``None`` either way (the
Appendix A7 smoke test prints that ``None``).

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

import os

import requests


def notify(message: str) -> None:
    """Post ``message`` to the configured webhook, or echo it offline."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print(f"[discord:offline] {message}")
        return None
    # Discord caps `content` at 2000 chars (ch02).
    requests.post(webhook_url, json={"content": message[:2000]}, timeout=10)
    return None
