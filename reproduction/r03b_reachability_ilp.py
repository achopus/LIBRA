"""Reachability, larger case: t = 4, N = 12, one stratum.

With spread switched off (an option of the tool) the tool locks period and carry-over balance as
hard constraints (both achievable) and has no penalties left, so its final random pick maximizes a
random linear objective over the whole feasible set. (With spread on, only 2 designs are optimal.) We enumerate that set exactly with no-good cuts (count vectors over the 24 orders), classify
each design as an extreme point or an interior point (a convex combination of the others), and run
  app    the app's solve(), 600 seeds
  walk   the research random walk (ext_solver.walk_pick), 600 seeds
to see which designs each can return and how evenly.

Output: results/r03b_reachability.csv (printed)
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import multiprocessing as mp
import time

import highspy
import numpy as np
import pandas as pd
from scipy import stats

from common import RESULTS, Config, ilp_spec
from r03_reachability import interior

T, N, SEEDS, LIMIT = 4, 12, 600, 3
MAX_SOLS = 3000
CFG = Config("enum12", T, (N,))


def enumerate_set():
    """All count vectors satisfying period, carry-over and spread balance (hard)."""
    from randomizer import solver as S
    from ext_solver import _build
    spec = ilp_spec(CFG, 1, 60, spread=False)
    ctx = S._prepare(spec, np.random.default_rng(1))
    levels = {"period": "required", "carryover": "required", "cooccurrence": "off", "spread": "off"}
    model, form, _ = _build(ctx, ctx.members, ctx.units, levels)
    n_idx = form.m[0]
    nS = len(n_idx)
    sols = []
    t0 = time.time()
    while len(sols) < MAX_SOLS:
        x, status, _ = model.solve(np.zeros(model.n), 60, 1.0, 1)
        if x is None:
            break
        v = np.round(x[n_idx]).astype(int)
        sols.append(v)
        # no-good cut: some order must be used more often than in v (totals are fixed)
        z = model.add_vars(nS, ub=1.0, integer=True)
        for s in range(nS):                     # n_s - (v_s + 1) z_s >= 0
            model.add_row(np.r_[n_idx[s], z[s]], np.r_[1.0, -(v[s] + 1.0)], 0.0, S.INF)
        model.add_row(z, 1.0, 1.0, S.INF)
    print(f"enumerated {len(sols)} designs in {time.time() - t0:.0f} s ({status})", flush=True)
    return np.array(sols), [tuple(s) for s in ctx.seqs]


def task(args):
    variant, seed = args
    if variant == "app":
        from randomizer import solve
        return solve(ilp_spec(CFG, seed, LIMIT, spread=False)).assign
    from ext_solver import Options, solve_ext
    return solve_ext(ilp_spec(CFG, seed, LIMIT, spread=False), Options(walk_pick=True)).assign


def main():
    sols, seqs = enumerate_set()
    index = {s: i for i, s in enumerate(seqs)}
    keys = [v.tobytes() for v in sols.astype(np.int8)]
    inside = np.array([interior(sols[i].astype(float), np.delete(sols, i, 0).astype(float)) for i in range(len(sols))])
    print(f"optimal designs: {len(sols)}, interior: {inside.sum()}", flush=True)
    rows = []
    for variant in ("app", "walk"):
        with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
            outs = pool.map(task, [(variant, s) for s in range(1, SEEDS + 1)], chunksize=1)
        got = [np.bincount([index[tuple(r)] for r in D], minlength=len(seqs)).astype(np.int8).tobytes() for D in outs]
        freq = pd.Series(got).value_counts()
        observed = np.array([freq.get(k, 0) for k in keys])
        reached = observed > 0
        rec = {"variant": variant, "optimal_designs": len(sols), "interior_designs": int(inside.sum()),
               "outputs_in_set": float(np.mean([g in set(keys) for g in got])),
               "share_reached": reached.mean(), "extreme_reached": f"{reached[~inside].sum()}/{(~inside).sum()}",
               "interior_reached": f"{reached[inside].sum()}/{inside.sum()}",
               "chi2_p": stats.chisquare(observed).pvalue if len(sols) > 1 else None,
               "max_over_expected": observed.max() / (SEEDS / len(sols))}
        rows.append(rec)
        print(rec, flush=True)
    pd.DataFrame(rows).to_csv(RESULTS / "r03b_reachability.csv", index=False)


if __name__ == "__main__":
    main()
