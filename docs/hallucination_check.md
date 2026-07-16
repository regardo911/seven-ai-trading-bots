# The Claude-Hallucination Detection Checklist (Chapter 10)

> "It looked great until I got Claude to admit it was inserting imaginary
> volatility numbers," the named failure mode this checklist prevents

Run all 8 items on every strategy **before** it touches the ch12 paper-to-live
ladder. A backtest that passes is honest; one that fails any item has a known
bias to fix first. Items 3–4 are automated here:

```bash
python tools/hallucination_check.py backtest/results/sample_trend.json
```

(the tool recomputes Sharpe / drawdown / win rate / EV from the raw arrays in
plain NumPy, deliberately independent code, and diffs them against the
reported metrics.)

## The checklist (book-verbatim)

1. **Did Claude introduce any numerical constant in the strategy code?**
   If yes, find the source. If the source is "Claude suggested it," replace it
   with a published default or run a real grid search.
2. **Did Claude write any of the backtest simulation loop?** Read it
   line-by-line. Every bar reference must be `data[i]`, never `data[i+1]` —
   one leaked bar of foresight makes any equity curve gorgeous.
3. **Was the equity curve reproduced by an independent calculation** (separate
   Claude session, or hand-coded NumPy)? If not, do that now. *(automated)*
4. **Is every reported metric checkable against a 3-line NumPy computation?**
   If yes, run the check. If no, the metric is suspect. *(automated)*
5. **Were open positions included at mark-to-market?** Closed-only equity
   curves understate drawdown and overstate Sharpe.
6. **Was the strategy backtested across all five named regime windows plus
   current data?** (This repo's backtests print the per-regime table.)
7. **At least 100 trades?** Below that, the backtest is hypothesis-generating,
   not edge-confirming (Wilson intervals on 82 trades span ~0.41–0.62).
8. **For LLM-classified strategies (news, PEAD): post-training-cutoff data
   only?** Pre-cutoff results are biased upward — Claude has memorized the
   corpus.

## Related discipline in this repo

- Win rate is never the headline metric: expected value per trade is
  (`expected_value_per_trade` in every results JSON; the 68%-win-rate paradox
  is a losing bot).
- Walk-forward only, never k-fold, for anything time-series
  (`framework/walk_forward.py`).
- Edge decay: rolling 90-day Sharpe < 0.5× the baseline → half-size; two
  consecutive months below → rotate a bench in (Appendix B).

---
*Educational reference. Not financial advice. See [DISCLAIMER.md](../DISCLAIMER.md).*
