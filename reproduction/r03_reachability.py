"""Reachability and uniformity of the random choice among
equally good designs, on cases large enough to have "interior" optimal designs.

The argument: maximizing a random linear objective over the optimal set returns an
extreme point of its convex hull, so an optimal design whose count vector is a convex combination
of other optimal designs can never be selected (by an exact solve).

Cases (single stratum, enumerable): t = 3 with N = 12 (carry-over balance achievable) and N = 15
(not achievable). For each: enumerate the tool's optimal set (a06.enumerate_optimal), then
  app    the app's solve() (final random pick = random objective over the capped model)
  walk   the research random walk (ext_solver.walk_pick)
with 300 seeds each (3 s limit, fresh processes). Report the share of the optimal set reached,
a chi-square test of uniformity, and, for every optimal design never reached, whether its count
vector is a convex combination of the other optimal designs (an LP feasibility check).

Output: results/r03_reachability.csv (printed)
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import multiprocessing as mp

import numpy as np
import pandas as pd
from scipy import optimize, stats

from a06_randomization_validity import enumerate_optimal
from common import RESULTS, Config, ilp_spec

SEEDS = 300
LIMIT = 3


def task(args):
    t, N, variant, seed = args
    cfg = Config("enum", t, (N,))
    if variant == "app":
        from randomizer import solve
        return solve(ilp_spec(cfg, seed, LIMIT)).assign
    from ext_solver import Options, solve_ext
    return solve_ext(ilp_spec(cfg, seed, LIMIT), Options(walk_pick=True)).assign


def interior(v, others):
    """Is v a convex combination of the vectors in `others`?"""
    if len(others) == 0:
        return False
    A = np.vstack([np.array(others).T, np.ones(len(others))])
    b = np.r_[v, 1.0]
    res = optimize.linprog(np.zeros(len(others)), A_eq=A, b_eq=b, bounds=(0, None), method="highs")
    return res.status == 0


def main():
    rows = []
    for t, N in ((3, 12), (3, 15)):
        opt, n_bal, seqs = enumerate_optimal(t, N)
        index = {s: i for i, s in enumerate(seqs)}
        opt_vecs = {k: np.frombuffer(k, dtype=np.int8).astype(float) for k in opt}
        inside = {k: interior(v, [w for kk, w in opt_vecs.items() if kk != k]) for k, v in opt_vecs.items()}
        for variant in ("app", "walk"):
            with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
                outs = pool.map(task, [(t, N, variant, s) for s in range(1, SEEDS + 1)], chunksize=1)
            keys = [np.bincount([index[tuple(r)] for r in D], minlength=len(seqs)).astype(np.int8).tobytes()
                    for D in outs]
            freq = pd.Series(keys).value_counts()
            observed = np.array([freq.get(k, 0) for k in opt])
            reached = observed > 0
            chi = stats.chisquare(observed) if len(opt) > 1 else None
            ks = list(opt)
            rec = {"t": t, "N": N, "variant": variant, "period_balanced_designs": n_bal,
                   "optimal_designs": len(opt), "interior_optimal_designs": int(sum(inside.values())),
                   "all_outputs_optimal": all(k in opt for k in keys),
                   "share_reached": reached.mean(),
                   "interior_reached": int(sum(reached[i] for i, k in enumerate(ks) if inside[k])),
                   "extreme_reached": int(sum(reached[i] for i, k in enumerate(ks) if not inside[k])),
                   "chi2_p": None if chi is None else chi.pvalue,
                   "max_over_expected": observed.max() / (SEEDS / len(opt))}
            rows.append(rec)
            print(rec, flush=True)
    pd.DataFrame(rows).to_csv(RESULTS / "r03_reachability.csv", index=False)


if __name__ == "__main__":
    main()
