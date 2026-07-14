"""Framework smoke test — Appendix A7, verbatim shape.

Expected output (offline, no keys):
    PASS
    {'account_number': 'PA1234567', 'cash': '100000.00', ...}
    [discord:offline] framework smoke-test: ok
    None

"If any of those three outputs is wrong, the chassis is not wired correctly
and no strategy will run." — Appendix A7
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from framework import brokers, claude, discord  # noqa: E402

print(claude.classify("Reply with the single word PASS."))
alpaca = brokers.AlpacaBroker(paper=True)
print(alpaca.get_account_info())
print(discord.notify("framework smoke-test: ok"))
