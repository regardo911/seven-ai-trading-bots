# Disclaimer

> **⚠️ Not financial advice.** This repository is **educational software** that accompanies the
> book *Use Claude to Build 7 AI Trading Bots*. It is provided for learning and research only.
> Nothing here is financial, investment, tax, or legal advice, and nothing here is a
> recommendation to buy, sell, or hold any security, derivative, cryptocurrency, or other
> instrument. Trading and investing carry substantial risk of loss, including the loss of more
> than your initial capital when using margin, futures, options, or leveraged crypto. Past or
> backtested performance — including any figures produced by this code on synthetic sample
> data — does **not** predict future results and is **not** indicative of any real trading
> outcome. The authors and contributors make **no warranty** of any kind and accept **no
> liability** for any loss arising from use of this software. **The software defaults to paper
> (simulated) mode; enabling live trading is entirely at your own risk.** You are solely
> responsible for your own decisions, for complying with the laws and regulations of your
> jurisdiction, and for the terms of any broker, exchange, or data/API provider you connect.
> Consult a licensed professional before making financial decisions.

## Additional notes

- **Synthetic data.** Every backtest and demo in this repository runs, by default, on
  deterministic **synthetic sample data** generated locally (see `framework/data.py`). All
  reported numbers are illustrative of the *mechanics* only. They are not real market results,
  not historical results, and not forecasts.
- **Paper mode is the default everywhere.** No code path in this repository places a real order
  unless you (1) edit source to call `framework.set_live_mode(True, confirm="I_HAVE_REVIEWED_THIS")`,
  (2) supply real broker credentials, and (3) pass `--live` explicitly. All three are deliberate
  acts. See “Going live safely” in the README.
- **Third-party services.** Broker, exchange, market-data, and model APIs referenced here
  (Alpaca, Interactive Brokers, Binance, Bybit, Anthropic, etc.) have their own terms, fees, and
  risk disclosures. Verify current fees and terms at the source; this repository deliberately
  reads such values from configuration instead of hard-coding them.
- **No warranty & no maintenance promise.** Per the MIT license, the software is provided
  “as is”. The book describes this mirror as “a starting point for your own framework, not a
  maintained library you depend on.”
