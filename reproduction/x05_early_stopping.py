"""Robustness to early stopping and dropout, computed from the benchmark pools (no solving).

Every design comes from the pools of a02 (LIBRA) and r02/r12 (annealers), so the numbers describe
the procedure as implemented in the app. The question whether nested balance can be met at all is
answered by the certificate t5n15_nested.mps (r08, r22) and x02_feasibility.py.

Per design (configurations A-D; first 60 designs of each pool):
  prefix_dev_total  carry-over deviation from the ideal band within the first k periods, summed over
                    k = 2..p-1 and over all units (all subjects and each group)
  eff_M2_stop_3     A-efficiency under the model with carry-over if the study stops after period 3
  eff_M2_drop       mean A-efficiency under that model when 20% of subjects leave after a random
                    period (30 patterns, the same for every method)

Output: results/x05_early_stopping.csv (summary), results/x05_early_stopping_per_design.csv
"""
import pandas as pd

from common import CONFIGS, RESULTS, load_pool
from x02_nested import evaluate

CFGS = ["A", "B", "C", "D"]
METHODS = ["williams", "williams_best", "classical", "sa_ws", "ilp_nospread", "ilp"]
PER_POOL = 60


def main():
    rows = []
    for c in CFGS:
        for m in METHODS:
            try:
                pool = load_pool(c, m)
            except FileNotFoundError:
                continue
            for i, D in enumerate(pool[:PER_POOL]):
                rows.append(evaluate(c, m, i + 1, D, {}))
    per = pd.DataFrame(rows)
    per.to_csv(RESULTS / "x05_early_stopping_per_design.csv", index=False)
    cols = ["prefix_dev_total", "eff_M2_stop_3", "eff_M2_drop", "eff_M2", "spread_dev_total"]
    g = per.groupby(["config", "variant"], sort=False)[cols]
    summ = g.mean().join(g.std(), rsuffix="_sd").reset_index()
    summ.to_csv(RESULTS / "x05_early_stopping.csv", index=False)
    print(summ.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
