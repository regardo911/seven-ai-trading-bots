"""Unified framework chassis — Chapter 2 of *Use Claude to Build 7 AI Trading Bots*.

The single most important safety rule in the book lives here: the framework has
one ``live_mode`` boolean, it defaults to ``False``, and the only way to flip it
is a deliberate **code-level** call with an explicit confirmation string — not a
config file, not an environment variable, not a CLI flag.

    "Every strategy reads ``framework.live_mode`` and refuses to call broker
    order endpoints if it is False." — ch02

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

live_mode = False


def set_live_mode(value: bool, confirm: str = "") -> None:
    """Flip the framework-level live flag (ch02, verbatim mechanism).

    Yes, requiring ``confirm="I_HAVE_REVIEWED_THIS"`` is intentionally
    annoying. It should be.
    """
    if value and confirm != "I_HAVE_REVIEWED_THIS":
        raise RuntimeError("live_mode requires explicit confirmation")
    global live_mode
    live_mode = value
