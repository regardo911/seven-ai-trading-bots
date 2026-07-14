"""Strategy 6 — Crypto cash-and-carry funding-rate arbitrage (Chapter 8).

Delta-neutral: long spot + short perp of equal notional, collecting the
funding payments crowded longs pay every 8 hours. Entry above 0.03%/window,
exit when funding mean-reverts, the basis converges, or funding inverts (the
circuit breaker — unwind immediately, no waiting). Claude is OFFLINE at
runtime — this is pure exchange data and arithmetic.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

from typing import Optional

from framework import cli, discord
from framework.brokers import CryptoBroker, Order

INSTRUMENTS = ["BTC", "ETH", "SOL"]
EXCHANGES = ["binance", "bybit"]
ENTRY_THRESHOLD = 0.0003     # 0.03% per 8h window (~32.85% annualized, ch08)
EXIT_THRESHOLD = 0.00005     # 0.005% per window: not worth the capital lock-up
BASIS_EXIT = 0.0005          # unwind when perp-spot basis <= 5 bps
MARGIN_MULT = 2.0            # 2-3x margin on the short leg, never higher (ch08)
SHORT_STOPOUT = 0.50         # close if short-leg MTM loss > 50% of posted margin
MAX_PER_EXCHANGE = 0.50      # never >50% of strategy capital on one venue
MAX_PER_INSTRUMENT = 0.33    # never >33% of an exchange's share in one name
LEG_FILL_WINDOW_SECONDS = 30  # both legs fill within 30s or abort (ch08)


def annualized(funding_rate: float) -> float:
    """0.03% x 3 settlements x 365 days = 32.85% — the entry-floor math (ch08)."""
    return funding_rate * 3 * 365


def open_basis_trade(exchange: CryptoBroker, symbol_spot: str, symbol_perp: str,
                     notional: float) -> dict:
    """ch08 BUILD STEP mechanics with the verified ccxt method names:
    fetch_ticker / create_order(symbol, type, side, amount, price)."""
    spot_qty = notional / exchange.fetch_ticker(symbol_spot)["last"]
    perp_qty = notional / exchange.fetch_ticker(symbol_perp)["last"]
    exchange.create_order(symbol_spot, "market", "buy", spot_qty)   # spot leg
    exchange.create_order(symbol_perp, "market", "sell", perp_qty)  # perp short
    return {"spot_qty": spot_qty, "perp_qty": perp_qty, "notional": notional}


def allocation_ok(open_positions: list[dict], exchange: str, capital: float,
                  notional: float) -> bool:
    """The mechanical diversification rules — do not override them (ch08)."""
    on_exchange = sum(p["notional"] for p in open_positions
                      if p["exchange"] == exchange)
    return (on_exchange + notional) <= capital * MAX_PER_EXCHANGE


def signal(funding_snapshot: dict, open_positions: list[dict] | None = None,
           capital: float = 100_000.0) -> Optional[Order]:
    """ch08 BUILD STEP 2 contract: one refreshed snapshot in, one open-basis
    Order (meta carries both legs) or None out."""
    open_positions = open_positions or []
    rate = funding_snapshot["fundingRate"]
    exchange = funding_snapshot["exchange"]
    symbol = funding_snapshot["symbol"].split("/")[0]
    if rate <= ENTRY_THRESHOLD:
        return None
    if any(p["exchange"] == exchange and p["symbol"] == symbol
           for p in open_positions):
        return None
    exchange_budget = capital * MAX_PER_EXCHANGE
    notional = min(exchange_budget * MAX_PER_INSTRUMENT, capital * 0.15)
    if not allocation_ok(open_positions, exchange, capital, notional):
        return None
    qty = notional / funding_snapshot["indexPrice"]
    return Order(symbol, qty, "buy", meta={
        "basis_trade": True, "exchange": exchange, "notional": notional,
        "entry_funding": rate, "annualized": annualized(rate),
        "margin_posted": notional / MARGIN_MULT,
        "legs": {"spot": {"side": "buy", "qty": qty},
                 "perp": {"side": "sell", "qty": qty}},
    })


def should_unwind(position: dict, funding_rate: float,
                  basis: float) -> str | None:
    """Three-condition exit (ch08 BUILD STEP 5); inversion fires immediately."""
    if funding_rate < 0:
        return "inversion_circuit_breaker"
    if funding_rate < EXIT_THRESHOLD:
        return "funding_mean_reverted"
    if abs(basis) <= BASIS_EXIT:
        return "basis_converged"
    return None


# ------------------------------- CLI (A3) ----------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser(
        "strategies.cash_carry",
        "Cash-and-carry bot (ch08): funding-rate arb, delta-neutral, circuit-broken.",
    )
    parser.add_argument("--exchanges", default=",".join(EXCHANGES))
    parser.add_argument("--instruments", default=",".join(INSTRUMENTS))
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--funding-history", default="24mo")
    args = parser.parse_args(argv)
    cli.banner("cash-and-carry bot (ch08)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live

    exchanges = [e.strip().lower() for e in args.exchanges.split(",") if e.strip()]
    instruments = [i.strip().upper() for i in args.instruments.split(",") if i.strip()]

    if args.backtest:
        from backtest import cash_carry as cc_backtest

        months = int(args.funding_history.rstrip("mo") or 24)
        result = cc_backtest.run(months=months, exchanges=exchanges,
                                 instruments=instruments, write=True)
        cc_backtest.print_report(result, regime=True)
        return 0

    print("[cash-carry] scanning synthetic funding snapshots "
          "(exchange API keys unlock live snapshots; NEVER enable withdrawal "
          "permissions on those keys - ch08)")
    brokers = {e: CryptoBroker(exchange=e, paper=paper) for e in exchanges}
    open_positions: list[dict] = []
    for exchange_name, broker in brokers.items():
        for instrument in instruments:
            snap = broker.fetch_funding_rate(f"{instrument}/USDT:USDT")
            snap["exchange"] = exchange_name
            rate = snap["fundingRate"]
            print(f"[cash-carry] {exchange_name}:{instrument} funding "
                  f"{rate * 100:+.4f}%/8h (~{annualized(rate):+.1%} annualized)")
            order = signal(snap, open_positions)
            if order is not None:
                legs = open_basis_trade(broker, instrument,
                                        f"{instrument}/USDT:USDT",
                                        order.meta["notional"])
                open_positions.append({"exchange": exchange_name,
                                       "symbol": instrument,
                                       "notional": order.meta["notional"]})
                discord.notify(
                    f"cash-carry: opened {instrument} basis on {exchange_name} "
                    f"({legs['spot_qty']:.4f} spot long / perp short, "
                    f"funding {rate * 100:+.4f}%/8h)"
                )
    if not open_positions:
        print("[cash-carry] no market above the 0.03%/8h entry floor right now - "
              "the bot is patient by design (ch08)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
