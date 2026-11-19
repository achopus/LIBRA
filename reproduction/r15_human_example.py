"""A worked example from human experimental psychology.

Design: 30 participants tested at two sites (15 per site), five conditions (CONTROL, EASY, MEDIUM,
HARD, DUAL), one per session over five sessions. Rule: the two most demanding conditions (HARD and
DUAL) never occur in consecutive sessions, in either order. Counterbalancing within each site.
The app's own solve() with default settings (60 s), 24 seeds, one solve per fresh process.

Comparison: how often designs from the conventional pools of configuration B (same size and
grouping) satisfy the rule by chance (rejection sampling).

Metrics (per site and overall): period imbalance, carry-over deviation and range over the 18
allowed ordered pairs, spread deviation, A-efficiency under M2, observers G2 (after one session)
and G3 after two sessions, pooled and conditional on site.

Output: results/r15_human_example.csv (per seed), results/r15_human_summary.csv,
        results/r15_example_schedule.csv (seed 1, long format: one row per participant x session)
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import math
import multiprocessing as mp

import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, a_efficiency, guess_accuracy, load_pool

COND = ["CONTROL", "EASY", "MEDIUM", "HARD", "DUAL"]
FORBID = [("HARD", "DUAL"), ("DUAL", "HARD")]
SEEDS = range(1, 25)
LIMIT = __import__('common').BENCH_SECONDS
SITES = np.repeat([0, 1], 15)


def spec_for(seed):
    from randomizer import DesignSpec
    subj = pd.DataFrame({"participant": [f"P{i + 1:02d}" for i in range(30)],
                         "site": ["Site 1"] * 15 + ["Site 2"] * 15})
    return DesignSpec(subjects=subj, id_column="participant", strata=["site"], treatments=COND,
                      n_periods=5, period_name="Session", forbidden_transitions=FORBID,
                      seed=seed, time_limit=LIMIT)


def task(seed):
    from randomizer import solve
    from randomizer.export import long_format
    res = solve(spec_for(seed))
    lf = long_format(res) if seed == 1 else None
    return seed, res.assign, dict(res.levels), bool(res.proven_optimal), res.solve_seconds, lf


def allowed():
    h, d = COND.index("HARD"), COND.index("DUAL")
    return [(a, b) for a in range(5) for b in range(5) if a != b and (a, b) not in ((h, d), (d, h))]


def band_dev(x, target):
    lo, hi = math.floor(target + 1e-9), math.ceil(target - 1e-9)
    x = np.asarray(x)
    return float(np.clip(x - hi, 0, None).sum() + np.clip(lo - x, 0, None).sum())


def unit_metrics(D):
    N, p = D.shape
    pairs = allowed()
    pc = np.stack([np.bincount(D[:, k], minlength=5) for k in range(p)])
    C = np.zeros((5, 5), int)
    Cj = np.zeros((p - 1, 5, 5), int)
    for k in range(p - 1):
        np.add.at(C, (D[:, k], D[:, k + 1]), 1)
        np.add.at(Cj[k], (D[:, k], D[:, k + 1]), 1)
    vals = np.array([C[a, b] for a, b in pairs])
    return {"period_dev": band_dev(pc, N / 5),
            "carry_dev": band_dev(vals, N * (p - 1) / len(pairs)),
            "carry_range": int(vals.max() - vals.min()),
            "spread_dev": sum(band_dev([Cj[k, a, b] for a, b in pairs], N / len(pairs)) for k in range(p - 1)),
            "violations": int(sum(C[a, b] for a in range(5) for b in range(5) if a != b and (a, b) not in pairs))}


def metrics(D):
    out = {}
    for name, rows in (("all", np.arange(30)), ("site1", np.arange(15)), ("site2", np.arange(15, 30))):
        for k, v in unit_metrics(D[rows]).items():
            out[f"{k}[{name}]"] = v
    g = guess_accuracy(D, 5)
    out["G2_1"], out["G3_2"] = g["G2"][0], g["G3"][1]
    out["G3_2_by_site"] = np.mean([guess_accuracy(D[SITES == s], 5)["G3"][1] for s in (0, 1)])
    out["eff_M2"] = a_efficiency(D, 5, True)[0]
    out["eff_M1"] = a_efficiency(D, 5, False)[0]
    return out


def satisfies(D):
    h, d = COND.index("HARD"), COND.index("DUAL")
    a, b = D[:, :-1], D[:, 1:]
    return not np.any(((a == h) & (b == d)) | ((a == d) & (b == h)))


def main():
    rows, lf = [], None
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        for seed, A, levels, proven, secs, l in pool.imap_unordered(task, SEEDS, chunksize=1):
            rows.append({"seed": seed, "proven": proven, "seconds": secs,
                         **{f"level_{k}": v for k, v in levels.items()}, **metrics(A),
                         "key": repr(sorted(map(tuple, A[:15]))) + repr(sorted(map(tuple, A[15:])))})
            if l is not None:
                lf = l
            print("seed", seed, flush=True)
    df = pd.DataFrame(rows).sort_values("seed")
    df.drop(columns="key").to_csv(RESULTS / "r15_human_example.csv", index=False)
    summ = df.drop(columns=["key", "seed"]).select_dtypes("number").agg(["mean", "std", "min", "max"]).T
    summ["distinct_designs"] = df.key.nunique()
    summ.to_csv(RESULTS / "r15_human_summary.csv")
    print(summ.round(3).to_string())
    print("levels:", df.filter(like="level_").drop_duplicates().to_dict("records"))
    if lf is not None:
        lf.to_csv(RESULTS / "r15_example_schedule.csv", index=False)
    rej = []
    for m in ("simple", "latin", "williams", "rerand", "classical"):
        pool = load_pool("B", m)
        rej.append({"method": m, "n": len(pool), "satisfy": int(sum(satisfies(D) for D in pool))})
    print(pd.DataFrame(rej).to_string(index=False))
    pd.DataFrame(rej).to_csv(RESULTS / "r15_rejection.csv", index=False)


if __name__ == "__main__":
    main()
