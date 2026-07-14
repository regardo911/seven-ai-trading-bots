"""Realism layer — the execution gap, priced in (ch11).

    "The execution gap kills 80 percent of bots. Not because the strategy was
     wrong. Because the backtest assumed every fill happened at the mid, every
     order executed in zero time, and every Claude inference was free." — ch11

``apply_realism`` nets slippage (by asset class, conservative upper end),
commissions (per broker per asset), a partial-fill penalty, a latency penalty,
and the Claude inference cost out of a trade's gross P&L. Every backtest in
this repository can be re-run through this layer via
``python -m framework.backtest_all --realism-pass``.

Educational reference implementation. Not financial advice. See DISCLAIMER.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Round-trip slippage by asset class (ch11 ranges; conservative UPPER end, on
# purpose: "strategies that perform well under the conservative default will
# perform better in production, not worse").
SLIPPAGE_BY_ASSET: dict[str, float] = {
    "equity_liquid": 0.0020,   # 0.05-0.20%  (SPY, QQQ, AAPL)
    "equity_midcap": 0.0100,   # 0.20-1.00%  (small/mid caps)
    "option": 0.0300,          # 1-3%        (liquid contracts)
    "crypto": 0.0050,          # 0.05-0.50%  (BTC/ETH/SOL majors)
    "futures": 0.0020,         # ES/GC treated like liquid equities (engineering default)
    "fx": 0.0010,              # majors; small spreads (engineering default)
}

# The book refuses to hard-code Alpaca's per-contract option fee ("verify the
# current schedule at the source"); 0.65 is the industry-typical placeholder.
VERIFIED_ALPACA_OPTION_FEE = float(os.environ.get("ALPACA_OPTION_FEE_PER_CONTRACT", "0.65"))

# ch11 headline number: Sonnet at ~5K input + 200 output tokens per inference.
INFERENCE_COST_PER_CALL = 0.018
OPUS_MULTIPLIER = 1.7


@dataclass
class Trade:
    """The realism layer's view of one round-trip trade."""

    strategy: str
    asset_class: str          # key into SLIPPAGE_BY_ASSET
    broker: str               # "alpaca" | "ibkr" | "binance"
    asset_type: str           # commission() asset_type
    qty: float
    notional: float
    inference_count: int = 0
    model: str = "sonnet"
    date: str | None = None   # close date (backtest cost attribution)


@dataclass
class RealismConfig:
    slippage: dict[str, float] = field(default_factory=lambda: dict(SLIPPAGE_BY_ASSET))
    alpaca_option_fee: float = VERIFIED_ALPACA_OPTION_FEE
    daily_vol: float = 0.010  # latency-penalty vol assumption


def commission(broker: str, asset_type: str, qty: int, notional: float) -> float:
    """Per-order commission, conservative side of every fee (ch11, verbatim map)."""
    if broker == "alpaca":
        if asset_type == "equity":
            return 0.0
        if asset_type == "option":
            return qty * VERIFIED_ALPACA_OPTION_FEE  # confirm at run time
        if asset_type == "crypto":
            return notional * 0.0025  # Alpaca crypto taker-side placeholder; verify
    if broker == "ibkr":
        if asset_type == "equity_lite":
            return 0.0
        if asset_type == "equity_pro_tiered":
            return qty * 0.0035  # conservative upper bound
        if asset_type == "equity_pro_fixed":
            return qty * 0.005
        if asset_type in ("futures", "fx"):
            return max(qty, 1) * 0.85  # per-contract engineering default; verify
    if broker in ("binance", "bybit"):
        if asset_type == "spot":
            return notional * 0.001    # 0.1% standard
        if asset_type == "futures":
            return notional * 0.0004   # ~0.04% taker, varies
    raise ValueError(f"unknown broker/asset: {broker}/{asset_type}")


def slippage_cost(asset_class: str, notional: float,
                  config: RealismConfig | None = None) -> float:
    table = (config or RealismConfig()).slippage
    if asset_class not in table:
        raise ValueError(f"unknown asset class: {asset_class}")
    return abs(notional) * table[asset_class]


def latency_penalty(notional: float, daily_vol: float = 0.010) -> float:
    """Small adverse-fill drift for the order's travel time — "1 to 5 dollars
    per $10K trade" (ch11); scaled mildly by volatility."""
    return abs(notional) * 0.0003 * min(max(daily_vol / 0.010, 0.5), 3.0)


def partial_fill_penalty(qty: float, notional: float) -> float:
    """Orders beyond ~1,000 shares walk the book (ch11): penalize the excess."""
    if qty <= 1000:
        return 0.0
    excess_fraction = (qty - 1000.0) / qty
    return abs(notional) * excess_fraction * 0.0015


def inference_cost(count: int, model: str = "sonnet") -> float:
    """Claude cost per trade: $0.018/inference on Sonnet, ~1.7x for Opus (ch11)."""
    multiplier = OPUS_MULTIPLIER if "opus" in model.lower() else 1.0
    return count * INFERENCE_COST_PER_CALL * multiplier


def trade_costs(trade: Trade, config: RealismConfig | None = None) -> dict:
    """Itemized round-trip friction for one trade."""
    cfg = config or RealismConfig()
    comm = 2.0 * commission(trade.broker, trade.asset_type,
                            int(max(trade.qty, 0)), trade.notional)
    return {
        "slippage": slippage_cost(trade.asset_class, trade.notional, cfg),
        "commission": comm,
        "latency": latency_penalty(trade.notional, cfg.daily_vol),
        "partial_fill": partial_fill_penalty(trade.qty, trade.notional),
        "inference": inference_cost(trade.inference_count, trade.model),
    }


def apply_realism(gross_pnl: float, trade: Trade,
                  config: RealismConfig | None = None) -> float:
    """Gross trade P&L in, realistic net P&L out (ch11's main function)."""
    return gross_pnl - sum(trade_costs(trade, config).values())
