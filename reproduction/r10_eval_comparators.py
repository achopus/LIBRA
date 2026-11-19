"""Evaluate the comparators of r02 on the paper's metrics.

Methods: classical (A, B), sa (A-E), next to ilp and williams from the main pools. Metrics as in
a03/a04: balance (period imbalance, carry-over range in the worst unit, spread deviation summed over
all units), predictability (G1, G2 after one period, G3 after two), per-change mutual information,
A-efficiency under M1 and M2, distinct skeletons.

Sensitivity: the same metrics for each of the 50 distinct carry-over-balanced 15 x 5 designs
(configuration A), each randomized once, to show how much a classical comparator depends on which
published balanced design is used.

Output: results/r10_comparators.csv, results/r10_balanced_family.csv (printed)
"""
import hashlib

import numpy as np
import pandas as pd

from a06_randomization_validity import canonical
from common import CONFIGS, POOLS, RESULTS, a_efficiency, design_metrics, guess_accuracy, load_pool, units_of
from r02_comparators import randomize_fixed

METHODS = ["williams", "classical", "sa", "ilp"]


def evaluate(D, cfg):
    units = [u for u, _ in units_of(cfg)]
    m = design_metrics(D, cfg)
    g = guess_accuracy(D, cfg.t)
    return {"period_dev": sum(m[f"period_dev[{u}]"] for u in units),
            "carry_range": max(m[f"carry_range[{u}]"] for u in units),
            "spread_dev": sum(m[f"spread_dev[{u}]"] for u in units),
            "G1": g["G1"][0], "G2": g["G2"][0], "G3_2": g["G3"][1] if cfg.t > 3 else np.nan,
            "mi": m["mi_per_change"], "eff_M1": a_efficiency(D, cfg.t, False)[0],
            "eff_M2": a_efficiency(D, cfg.t, True)[0],
            "skeleton": hashlib.md5(repr(canonical(D, cfg)).encode()).hexdigest()[:16]}


def main():
    rows = []
    for c, cfg in CONFIGS.items():
        for m in METHODS:
            try:
                pool = load_pool(c, m)[:60]
            except FileNotFoundError:
                continue
            for D in pool:
                rows.append({"config": c, "method": m, **evaluate(D, cfg)})
        print(c, flush=True)
    per = pd.DataFrame(rows)
    summ = per.drop(columns="skeleton").groupby(["config", "method"]).mean()
    summ["distinct_skeletons"] = per.groupby(["config", "method"]).skeleton.nunique()
    summ = summ.reset_index()
    summ.to_csv(RESULTS / "r10_comparators.csv", index=False)
    print(summ.round(3).to_string(index=False))

    fam = np.load(POOLS / "A_balanced_family.npz")["designs"]
    rng = np.random.default_rng(3)
    cfg = CONFIGS["A"]
    fr = pd.DataFrame([evaluate(randomize_fixed(D, cfg, rng), cfg) for D in fam]).drop(columns="skeleton")
    fr.to_csv(RESULTS / "r10_balanced_family.csv", index=False)
    print("\n50 balanced uniform 15 x 5 designs (configuration A):")
    print(fr.describe().loc[["mean", "min", "max"]].round(3).to_string())


if __name__ == "__main__":
    main()
