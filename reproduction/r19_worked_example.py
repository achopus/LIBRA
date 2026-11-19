"""Worked example (r15) with LIBRA in both final-choice modes: Variety (the default) and
Speed. 24 seeds, 60 s, reproducible mode (the default), one solve per fresh process.
Output: results/r19_worked_example.csv"""
import multiprocessing as mp
import sys
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parent
sys.path.insert(0, str(ANALYSIS))
OUT = ANALYSIS / "results"

import pandas as pd  # noqa: E402


def task(args):
    seed, mode = args
    import r15_human_example as r
    from randomizer import solve
    spec = r.spec_for(seed)
    spec.randomization = mode
    res = solve(spec)
    info = dict(res.randomization)
    return {"mode": mode, "seed": seed, "proven": res.proven_optimal, "seconds": res.solve_seconds,
            "method": info.get("method"), "designs": info.get("designs"), **r.metrics(res.assign),
            "key": repr(sorted(map(tuple, res.assign[:15]))) + repr(sorted(map(tuple, res.assign[15:])))}


if __name__ == "__main__":
    tasks = [(s, m) for m in ("variety", "speed") for s in range(1, 25)]
    rows = []
    from common import WORKERS
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        for row in pool.imap_unordered(task, tasks, chunksize=1):
            rows.append(row)
            print(row["mode"], row["seed"], row["method"], row["designs"], round(row["seconds"], 1), flush=True)
    df = pd.DataFrame(rows).sort_values(["mode", "seed"])
    df.to_csv(OUT / "r19_worked_example.csv", index=False)
    for m, g in df.groupby("mode"):
        print("\n==", m, "distinct designs:", g.key.nunique(), "methods:", g.method.value_counts().to_dict())
        cols = ["seconds", "proven", "carry_range[site1]", "carry_range[site2]", "spread_dev[all]",
                "period_dev[site1]", "violations[all]", "G2_1", "G3_2", "G3_2_by_site", "eff_M2", "eff_M1"]
        print(g[cols].astype(float).agg(["mean", "std", "min", "max"]).T.round(3).to_string())
        print("runs with range 2 at both sites:",
              int(((g["carry_range[site1]"] == 2) & (g["carry_range[site2]"] == 2)).sum()))
