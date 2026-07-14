"""Chapter 9 lab — the allocator, with the caveat the raw demo hides.

The Chapter 9 allocator sizes six bots by risk parity (inverse volatility). On
SYNTHETIC data, whichever bot happens to have the lowest fake volatility gets
the biggest weight — which can look like the allocator "found" a winner. It
didn't. This lab runs the allocator, then prints the concentration its weights
imply, applies an illustrative per-strategy cap, and says plainly that any
apparent edge here is a synthetic-data artifact.

Everything here is SYNTHETIC SAMPLE DATA. See DISCLAIMER.md.

Run: `python examples/demo_ch09.py`  (or `make demo-ch09`)
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from framework.allocator import Allocator  # noqa: E402

CONCENTRATION_CAP = 0.40  # flag/curb any single strategy above 40% of capital


def _capped(weights: dict[str, float], cap: float) -> dict[str, float]:
    """Enforce a hard per-strategy cap: clamp anything over `cap` and hand the
    excess to the under-cap strategies proportionally, repeating until nothing
    exceeds the cap. This is the sizing discipline a real allocator needs and
    risk-parity-on-synthetic-vol lacks (a single renormalize would re-inflate
    the capped name straight back over the cap)."""
    w = dict(weights)
    for _ in range(len(w)):
        excess = sum(v - cap for v in w.values() if v > cap)
        if excess <= 1e-12:
            break
        for k, v in w.items():
            if v > cap:
                w[k] = cap
        pool = sum(v for v in w.values() if v < cap) or 1.0
        for k, v in w.items():
            if v < cap:
                w[k] = v + excess * v / pool
    return w


def main() -> int:
    print("== Chapter 9 lab: the portfolio allocator ==")
    print("Synthetic sample data — the weights below are MECHANICS, not an edge.\n")

    result = Allocator(capital=100_000.0).run()  # prints the ch09 dashboard
    weights = result["weights"]
    top, top_w = max(weights.items(), key=lambda kv: kv[1])

    print("\n-- how concentrated is that? --")
    capped = _capped(weights, CONCENTRATION_CAP)
    for name in weights:
        bar = "#" * round(weights[name] * 40)
        print(f"  {name:<11} raw {weights[name]:>5.0%}  capped {capped[name]:>5.0%}  {bar}")

    if top_w > CONCENTRATION_CAP:
        print(f"\n!!  CONCENTRATION: risk parity put {top_w:.0%} of capital in "
              f"'{top}'. On synthetic data that is an ARTIFACT of one bot's fake\n"
              f"    low volatility, not a real edge. A live allocator needs "
              f"real-vol inputs AND a per-strategy cap (shown above). Do NOT read\n"
              f"    this as 'trust {top}'.")
    else:
        print(f"\n    Top weight: '{top}' at {top_w:.0%} — under the "
              f"{CONCENTRATION_CAP:.0%} flag, but still synthetic.")

    print("\nNext: `make realism` — watch these gross numbers shrink after fees, "
          "slippage, latency, and Claude inference cost. That degradation is the "
          "lesson, not the weights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
