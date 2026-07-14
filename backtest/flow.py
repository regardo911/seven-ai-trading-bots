"""Flow-mirror backtest (ch07 BUILD STEP 8): supports per-layer ablation via
``--layers`` ("run with and without each Greek layer to measure the impact").

Synthetic sample data; illustrative mechanics only. Not financial advice.
"""

from __future__ import annotations

from backtest import common

print_report = common.print_report


def run(layers: str = "all", write: bool = True) -> dict:
    runner = common.FlowRunner(layers=layers)
    result = common.run_runner(runner)
    result["params"]["layers"] = layers
    if write:
        common.save_json("flow", result)
    return result


if __name__ == "__main__":
    print_report(run(), regime=True)
