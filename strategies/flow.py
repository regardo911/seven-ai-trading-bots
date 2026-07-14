"""Strategy 5 — Options flow whale-mirror with Greeks (Chapter 7).

Mirroring the whale's position without mirroring the Greeks discipline is how
retail bleeds to theta. Four Greek-aware layers gate every mirror: a delta
budget per position, a portfolio gamma cap, an IV-crush filter, and
theta-decay / DTE management. Claude is OFFLINE at runtime — Greeks are
arithmetic (ch06 placement table).

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
Paper mode by default; live requires the ch02 set_live_mode() code change.
"""

from __future__ import annotations

from typing import Optional

from framework import cli, data, discord
from framework.brokers import Order, broker_for

DELTA_BUDGET_PER_10K = 0.20    # layer 1 (ch07)
GAMMA_CAP_PER_100K = 50.0      # layer 2: sum |gamma points| cap per $100K
IV_PERCENTILE_MAX = 80.0       # layer 3: skip mirrors above the 80th pct
THETA_CLOSE = -0.5             # layer 4: close at -$0.5/day bleed...
PROGRESS_TO_STRIKE = 0.50      # ...unless underlying moved 50% toward strike
MIN_NOTIONAL = 50_000.0        # ignore prints too small to be informative
MAX_DTE = 180                  # >6 months out = LEAP-buying patterns, skip
FINAL_DTE_STOP = 2             # hard time-stop in the contract's last 2 days
MAX_PORTFOLIO_OPTIONS_PCT = 0.05  # 5% of equity in open options notional


def position_size_by_delta(
    account_equity: float,
    delta_per_contract: float,
    delta_budget_per_10k: float = DELTA_BUDGET_PER_10K,
    underlying_price: float = 100.0,
) -> int:
    """Layer 1: the delta budget — 0.50-delta on a $10K account -> 4 contracts.

    Note: ch07's printed snippet multiplies the budget by 100, which yields
    0.4 -> int -> 0 contracts and contradicts the chapter's own worked answer
    ("Four contracts. The bot does not exceed it."), stated twice. This
    implementation honors the canonical worked example (budget = 200 delta
    points per $10K at the 0.20 budget). See docs/book-reconciliations.md.
    """
    delta_points_budget = (account_equity / 10000.0) * delta_budget_per_10k * 1000.0
    max_contracts = int(delta_points_budget / (delta_per_contract * 100.0))
    return max_contracts


def gamma_cap_ok(open_gammas: list[float], new_gamma_points: float,
                 account_equity: float) -> bool:
    """Layer 2 (ch07): sum |gamma| across open positions < 50 per $100K."""
    cap = GAMMA_CAP_PER_100K * (account_equity / 100_000.0)
    return sum(abs(g) for g in open_gammas) + abs(new_gamma_points) < cap


def iv_filter_ok(iv_percentile: float) -> bool:
    """Layer 3 (ch07): the filter applies symmetrically to calls and puts."""
    return iv_percentile < IV_PERCENTILE_MAX


def dte_size_multiplier(dte: int) -> float:
    """Layer 4 sizing tiers (ch07, verbatim): weeklies at 25% of normal."""
    if dte < 14:
        return 0.25
    if dte > 90:
        return 1.0
    return 1.0


def is_clean_directional(event: dict) -> tuple[bool, str]:
    """Pre-filter (ch07 BUILD STEP 3): only mirror prints that look like
    clean directional bets, not spreads/hedges/LEAP accumulation."""
    if event.get("both_sides"):
        return False, "both-sides print (likely a spread, not direction)"
    if event["notional"] < MIN_NOTIONAL:
        return False, f"notional ${event['notional']:,.0f} < ${MIN_NOTIONAL:,.0f}"
    if event["dte"] > MAX_DTE:
        return False, f"dte {event['dte']} > {MAX_DTE} (LEAP pattern)"
    return True, "clean directional"


def evaluate_gates(event: dict, account_equity: float = 100_000.0,
                   open_gammas: list[float] | None = None) -> dict:
    """Run all four Greek layers and report each result (ch07 CHECKPOINT)."""
    open_gammas = open_gammas or []
    clean, why = is_clean_directional(event)
    gates: dict = {"clean_directional": (clean, why)}
    if not clean:
        gates["verdict"] = "skip"
        return gates

    ivp = event.get("iv_percentile", data.iv_percentile(event["ticker"],
                                                        event["ts"]))
    gates["iv_crush"] = (iv_filter_ok(ivp), f"IV percentile {ivp:.0f}")

    # "The bot takes the minimum of the caps." (ch07 risk framing)
    by_delta = int(position_size_by_delta(account_equity, event["delta"])
                   * dte_size_multiplier(event["dte"]))
    gates["delta_budget"] = (by_delta >= 1,
                             f"{by_delta} contracts after "
                             f"{dte_size_multiplier(event['dte']):.2f} DTE mult")

    gamma_headroom = (GAMMA_CAP_PER_100K * (account_equity / 100_000.0)
                      - sum(abs(g) for g in open_gammas))
    by_gamma = int(gamma_headroom / (event["gamma"] * 100.0)) \
        if event["gamma"] > 0 else by_delta
    gates["gamma_cap"] = (by_gamma >= 1,
                          f"headroom fits {max(by_gamma, 0)} contracts")

    contracts = max(min(by_delta, by_gamma), 0)
    passed = all(ok for ok, _ in
                 (gates["clean_directional"], gates["iv_crush"],
                  gates["delta_budget"], gates["gamma_cap"])) and contracts >= 1
    gates["verdict"] = "mirror" if passed else "skip"
    gates["contracts"] = contracts
    return gates


def signal(flow_event: dict, account_equity: float = 100_000.0,
           open_gammas: list[float] | None = None) -> Optional[Order]:
    """ch07 BUILD STEP 2 contract: one flow event in, one Order or None out."""
    gates = evaluate_gates(flow_event, account_equity, open_gammas)
    if gates["verdict"] != "mirror":
        return None
    contracts = gates["contracts"]
    return Order(flow_event["ticker"], contracts, "buy", meta={
        "instrument": "option",
        "option_type": flow_event["side"],       # mirror the whale's direction
        "dte": flow_event["dte"],
        "delta": flow_event["delta"], "gamma": flow_event["gamma"],
        "theta": flow_event["theta"],
        "premium": flow_event.get("premium", 4.20),
        "source_notional": flow_event["notional"],
    })


def should_close(position: dict, theta_per_day: float,
                 progress_toward_strike: float, dte: int) -> str | None:
    """Managed exits (ch07 BUILD STEP 6): theta sweep + final-2-days stop."""
    if dte <= FINAL_DTE_STOP:
        return "final_dte_stop"
    if theta_per_day <= THETA_CLOSE and progress_toward_strike < PROGRESS_TO_STRIKE:
        return "theta_sweep"
    return None


# ------------------------------- CLI (A3) ----------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = cli.build_parser(
        "strategies.flow",
        "Flow-mirror bot (ch07): delta budget, gamma cap, IV-crush filter, theta sweep.",
    )
    parser.add_argument("--flow-provider", default="unusualwhales",
                        help="flow feed (offline fixture events used without an API key)")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--layers", default="all",
                        help="'all' or subset of delta,gamma,iv,theta,dte for ablation")
    args = parser.parse_args(argv)
    cli.banner("options flow bot (ch07)")
    paper = cli.guard_live(args)  # True unless an *armed* --live routes live

    if args.backtest:
        from backtest import flow as flow_backtest

        result = flow_backtest.run(layers=args.layers, write=True)
        flow_backtest.print_report(result, regime=True)
        return 0

    print(f"[flow] provider={args.flow_provider} (offline fixture flow events; "
          "set UNUSUAL_WHALES_API_KEY to wire the real feed)")
    events = data.load_fixture("flow_events")
    open_gammas: list[float] = []
    mirrored = 0
    for event in events:
        gates = evaluate_gates(event, open_gammas=open_gammas)
        detail = "; ".join(
            f"{name}={'PASS' if value[0] else 'REJECT'} ({value[1]})"
            for name, value in gates.items() if isinstance(value, tuple)
        )
        print(f"[flow] {event['ticker']} {event['side']} dte={event['dte']} "
              f"-> {gates['verdict'].upper()} | {detail}")
        order = signal(event, open_gammas=open_gammas)
        if order is not None:
            broker_for(order.symbol, paper=paper).place_order(order.symbol, order.qty,
                                                 order.side, "market")
            open_gammas.append(order.meta["gamma"] * order.qty * 100.0)
            discord.notify(f"flow: mirror {order.qty}x {order.symbol} "
                           f"{order.meta['option_type']} dte={order.meta['dte']}")
            mirrored += 1
    print(f"[flow] events: {len(events)}, mirrored: {mirrored}, "
          f"rejected: {len(events) - mirrored} "
          "(the IV filter should reject 30-50% - that's the honesty check, ch07)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
