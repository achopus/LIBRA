"""Scalability: run time and achieved balance over a grid of design sizes.

Grid: t = 3..8 treatments; N = 2t, 3t, 4t + 2 subjects; 1 or 2 strata (equal halves).
Each run: default settings (reproducible mode, effort 60 s), fresh process, one solver thread;
4 runs in parallel.

Outputs results/scalability.csv, figures/fig_scalability.png
"""
import multiprocessing as mp
import time

import numpy as np
import pandas as pd

from common import FIGURES, RESULTS, Config, design_metrics, ilp_spec, units_of
import plotstyle as ps

TIME_LIMIT = 60


def task(args):
    t, N, k = args
    from randomizer import solve
    sizes = (N,) if k == 1 else (N // 2, N - N // 2)
    cfg = Config("grid", t, sizes)
    t0 = time.time()
    res = solve(ilp_spec(cfg, seed=1, time_limit=TIME_LIMIT))
    m = design_metrics(res.assign, cfg)
    units = [n for n, _ in units_of(cfg)]
    return {"t": t, "N": N, "strata": k, "seconds": time.time() - t0, "status": res.status,
            "proven_optimal": res.proven_optimal, "formulation": res.formulation,
            "work_seconds": res.work_seconds, "reproducible": res.reproducible,
            "checks": str(res.checks), "choice": res.randomization.get("method"),
            **{f"level_{a}": b for a, b in res.levels.items()},
            "period_dev": sum(m[f"period_dev[{u}]"] for u in units),
            "carry_range_worst": max(m[f"carry_range[{u}]"] for u in units),
            "spread_dev_all": m["spread_dev[all]"]}


def main():
    tasks = [(t, N, k) for t in range(3, 9) for N in (2 * t, 3 * t, 4 * t + 2) for k in (1, 2)]
    with mp.get_context("spawn").Pool(4, maxtasksperchild=1) as pool:
        rows = []
        for r in pool.imap_unordered(task, tasks):
            rows.append(r)
            print(r, flush=True)
    df = pd.DataFrame(rows).sort_values(["t", "N", "strata"])
    df.to_csv(RESULTS / "scalability.csv", index=False)
    print(df.to_string(index=False))
    figure(df)


def figure(df):
    ps.apply()
    ps.plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 7.5})   # drawn at printed size
    fig, axes = ps.plt.subplots(1, 2, figsize=(6.2, 2.6))
    for k, marker in ((1, "o"), (2, "s")):
        g = df[df.strata == k]
        sc = axes[0].scatter(g.N, g.seconds, c=g.t, cmap="viridis", marker=marker, s=18,
                             label="1 stratum" if k == 1 else "2 strata")
        axes[1].scatter(g.N, g.carry_range_worst, c=g.t, cmap="viridis", marker=marker, s=18)
    axes[0].axhline(TIME_LIMIT, color=ps.MUTED, lw=0.8, ls="--")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Subjects (N)"); axes[0].set_ylabel("Real time (s, log scale)")
    axes[0].set_title(f"Run time (budget {TIME_LIMIT}, dashed)")
    axes[1].set_xlabel("Subjects (N)"); axes[1].set_ylabel("Carry-over range, worst stratum")
    axes[1].set_title("Carry-over balance (0 = perfect)")
    axes[0].legend(fontsize=7)
    fig.colorbar(sc, ax=axes, label="Treatments (t)", shrink=0.9)
    fig.savefig(FIGURES / "fig_scalability.png", dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    main()
