"""Every main-table metric per design, so the tables can report means with SDs, plus the full-list
observer conditional on stratum.

Methods: all pools (conventional and classical: 200 designs; ILP variants and both annealers: 60).
Metrics per design (definitions as in the paper):
  period_dev, spread_dev  summed over all units (all subjects and each stratum)
  carry_range             worst unit
  G1, G2                  after one observed period; G3 after one and two observed periods
  G3s_1, G3s_2            full-list observer who also sees the subject's stratum (uses only the rows
                          of that stratum); size-weighted mean over strata. Equals G3 with one stratum.
  mi                      per-change mutual information
  eff_M1, eff_M2          A-efficiency
  skeleton                canonical form (designs equal up to relabelling and within-stratum order)

Output: results/r16_per_design.csv, results/r16_summary.csv (mean, sd; skeletons among first 60)
"""
import hashlib
import multiprocessing as mp

import numpy as np
import pandas as pd

from a06_randomization_validity import canonical
from common import CONFIGS, RESULTS, a_efficiency, design_metrics, guess_accuracy, load_pool, units_of

METHODS = ["simple", "latin", "williams", "williams_best", "rerand", "classical", "sa", "sa_ws", "ilp_nospread", "ilp"]


def evaluate(D, cfg):
    units = [u for u, _ in units_of(cfg)]
    m = design_metrics(D, cfg)
    g = guess_accuracy(D, cfg.t)
    out = {"period_dev": sum(m[f"period_dev[{u}]"] for u in units),
           "carry_range": max(m[f"carry_range[{u}]"] for u in units),
           "spread_dev": sum(m[f"spread_dev[{u}]"] for u in units),
           "G1": g["G1"][0], "G2": g["G2"][0], "G3_1": g["G3"][0],
           "G3_2": g["G3"][1] if cfg.t > 3 else np.nan,
           "mi": m["mi_per_change"],
           "eff_M1": a_efficiency(D, cfg.t, False)[0], "eff_M2": a_efficiency(D, cfg.t, True)[0]}
    gs = [(len(rows), guess_accuracy(D[rows], cfg.t)) for _, rows in units_of(cfg)[1:]] or [(cfg.N, g)]
    out["G3s_1"] = sum(n * h["G3"][0] for n, h in gs) / cfg.N
    out["G3s_2"] = sum(n * h["G3"][1] for n, h in gs) / cfg.N if cfg.t > 3 else np.nan
    out["skeleton"] = hashlib.md5(repr(canonical(D, cfg)).encode()).hexdigest()[:16]
    return out


def task(args):
    c, m = args
    try:
        pool = load_pool(c, m)
    except FileNotFoundError:
        return []
    return [{"config": c, "method": m, "design": i, **evaluate(D, CONFIGS[c])} for i, D in enumerate(pool)]


def main():
    tasks = [(c, m) for c in CONFIGS for m in METHODS]
    rows = []
    with mp.get_context("spawn").Pool(10) as pool:
        for r in pool.imap_unordered(task, tasks, chunksize=1):
            rows += r
            if r:
                print(r[0]["config"], r[0]["method"], len(r), flush=True)
    per = pd.DataFrame(rows).sort_values(["config", "method", "design"])
    per.to_csv(RESULTS / "r16_per_design.csv", index=False)
    num = per.drop(columns=["skeleton", "design"])
    summ = num.groupby(["config", "method"]).agg(["mean", "std"])
    summ.columns = [f"{a}_{b}" for a, b in summ.columns]
    summ["n"] = per.groupby(["config", "method"]).size()
    summ["skeletons60"] = per[per.design < 60].groupby(["config", "method"]).skeleton.nunique()
    summ = summ.reset_index()
    summ.to_csv(RESULTS / "r16_summary.csv", index=False)
    cols = ["config", "method", "n", "carry_range_mean", "period_dev_mean", "spread_dev_mean", "spread_dev_std",
            "G2_mean", "G3_2_mean", "G3s_2_mean", "eff_M2_mean", "skeletons60"]
    print(summ[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
