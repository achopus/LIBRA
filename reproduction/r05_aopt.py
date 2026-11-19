"""How much efficiency do the balance criteria leave on the table?

For each configuration, an exchange search maximizes A-efficiency under the model with first-order
carry-over (M2) directly, over all complete crossover designs (every subject receives each
treatment once; no balance constraints): random restarts, each a first-improvement local search
over swaps of two periods within one subject's order, plus random restarts of single subjects.
Designs in which some contrast is not estimable are rejected. 120 s per configuration.

Compared with the ILP's M2 efficiency and Williams squares, with the balance of the
A-optimal design found.

Output: results/r05_aopt.csv (printed)
"""
import multiprocessing as mp
import time

import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, a_efficiency, design_metrics, model_matrix, units_of

SECONDS = 120


def estimable(D, t):
    X, tr = model_matrix(D, t, True)
    B = np.zeros((X.shape[1], t - 1))
    B[tr, :] = np.eye(t - 1)
    return bool(np.allclose(np.linalg.pinv(X) @ X @ B, B, atol=1e-8))


def eff(D, t):
    return a_efficiency(D, t, True)[0] if estimable(D, t) else -1.0


def search(c):
    cfg = CONFIGS[c]
    t, N = cfg.t, cfg.N
    rng = np.random.default_rng(5)
    best, bestD = -1.0, None
    t0 = time.time()
    while time.time() - t0 < SECONDS:
        D = np.stack([rng.permutation(t) for _ in range(N)])
        cur = eff(D, t)
        improved = True
        while improved and time.time() - t0 < SECONDS:
            improved = False
            for i in rng.permutation(N):
                for a in range(t):
                    for b in range(a + 1, t):
                        E = D.copy()
                        E[i, [a, b]] = E[i, [b, a]]
                        e = eff(E, t)
                        if e > cur + 1e-12:
                            D, cur, improved = E, e, True
        if cur > best:
            best, bestD = cur, D.copy()
    m = design_metrics(bestD, cfg)
    units = [n for n, _ in units_of(cfg)]
    return {"config": c, "aopt_eff_M2": best, "aopt_eff_M1": a_efficiency(bestD, t, False)[0],
            "aopt_period_dev": sum(m[f"period_dev[{u}]"] for u in units),
            "aopt_carry_range_worst": max(m[f"carry_range[{u}]"] for u in units)}


def main():
    with mp.get_context("spawn").Pool(5) as pool:
        rows = pool.map(search, list(CONFIGS))
    eff_tab = pd.read_csv(RESULTS / "efficiency_per_design.csv")
    ref = eff_tab.groupby(["config", "method"]).eff_M2.mean().unstack()
    df = pd.DataFrame(rows)
    df["ilp_eff_M2"] = df.config.map(ref["ilp"])
    df["williams_eff_M2"] = df.config.map(ref["williams"])
    df["ilp_share_of_aopt"] = df.ilp_eff_M2 / df.aopt_eff_M2
    df.to_csv(RESULTS / "r05_aopt.csv", index=False)
    print(df.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
