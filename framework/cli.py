"""Shared CLI plumbing for the strategy modules (Appendix A3 command surface).

Every strategy CLI defaults to paper mode. Passing ``--live`` alone can never
place a real order: it prints the live-trading warning and exits unless
``framework.live_mode`` was already enabled in source via
``framework.set_live_mode(True, confirm="I_HAVE_REVIEWED_THIS")`` (ch02 rule).

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

import argparse

import framework

DISCLAIMER_LINE = (
    "[disclaimer] Educational software on synthetic sample data - paper mode. "
    "Not financial advice. See DISCLAIMER.md."
)

LIVE_WARNING = """
================================ LIVE TRADING =================================
!! You passed --live. Live trading risks real money. This project is
!! educational software and NOT financial advice (see DISCLAIMER.md).
!!
!! A CLI flag alone can NEVER go live (ch02 safety rule). Requirements:
!!   1. Edit your run script to call:
!!        framework.set_live_mode(True, confirm="I_HAVE_REVIEWED_THIS")
!!   2. Provide real broker credentials in the environment (.env).
!!   3. Re-run with --live.
===============================================================================
"""


def build_parser(prog: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "--paper",
        action="store_true",
        default=True,
        help="run in paper (simulated) mode — the default, always",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="request live mode (refused unless framework.set_live_mode was called in source)",
    )
    parser.add_argument(
        "--live-data",
        action="store_true",
        help="fetch real market data via yfinance instead of synthetic fixtures (optional)",
    )
    return parser


def guard_live(args: argparse.Namespace) -> bool:
    """Return True when running paper. Exits the process on an unarmed --live."""
    if not getattr(args, "live", False):
        return True
    print(LIVE_WARNING)
    if not framework.live_mode:
        print("[refused] framework.live_mode is False - staying safe, exiting.")
        raise SystemExit(2)
    return False


def banner(name: str) -> None:
    print(f"== {name} ==")
    print(DISCLAIMER_LINE)
