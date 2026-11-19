"""Replication of the exchangeability test on a fresh, larger pool (new seeds, short time limit),
for the configurations/variants that gave small p-values in a06b.

Output results/validity_exchangeability_replication.csv
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import multiprocessing as mp
import sys

import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, ilp_spec
import a06b_exchangeability as x


def task(args):
    c, seed, spread = args
    from randomizer import solve
    return solve(ilp_spec(CONFIGS[c], seed, 5, spread)).assign


def main(n=120):
    cases = [("B", True), ("D", False), ("A", True)]
    rows = []
    for c, spread in cases:
        with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
            designs = np.stack(pool.map(task, [(c, 5000 + s, spread) for s in range(n)]))
        cfg = CONFIGS[c]
        rng = np.random.default_rng(11)
        obs = x.stat(designs, cfg.t)
        null = np.array([x.stat(x.symmetrize(designs, cfg, rng), cfg.t) for _ in range(1999)])
        rows.append({"config": c, "method": "ilp" if spread else "ilp_nospread", "designs": n,
                     "time_limit": 5, "statistic": round(obs, 1), "null_mean": round(null.mean(), 1),
                     "mc_p_value": (1 + (null >= obs).sum()) / 2000})
        print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(RESULTS / "validity_exchangeability_replication.csv", index=False)


if __name__ == "__main__":
    main()
