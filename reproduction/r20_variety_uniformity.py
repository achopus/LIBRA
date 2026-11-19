"""Is the default final choice (Variety) uniform? And how uneven is its fallback, the random walk?

Target: every acceptable allocation of orders to subjects equally likely. In a one-group
design a "design" here is the count vector over all orders (labels as given), and a design used with
counts n_s can be dealt to the N subjects in N! / prod_s n_s! ways, so its expected share of the draws
is proportional to that number.

Cases (default settings otherwise: reproducible mode, the given budget, final choice Variety):
  58     t = 4, N = 12, spread off: 58 designs with session and carry-over balance (as in r03b)
  S12    t = 4, N = 16, spread on: the designs with session, carry-over and spread all perfect
Variants:
  variety   the default (lists the designs and draws one); 12000 seeds
  walk      listing switched off, so the random walk is used (the fallback for large sets); 600 seeds

The expected counts differ a lot between designs (in case 58 from 0.04 to 50 per 1200 draws), so the
asymptotic chi-square p-value is unreliable. Reported as well: a Monte Carlo p-value of the same
chi-square statistic under exact multinomial sampling from the target (chi2_p_exact), and a chi-square
after pooling designs (in order of expected count) into bins of expected count >= 5 (chi2_p_pooled).

Output: results/r20_variety_uniformity.csv (one row per case and variant),
        results/r20_counts.csv (observed and expected count of every design)
Usage: python r20_variety_uniformity.py [variety_seeds] [time_limit]
       R20_VARIANTS=variety python r20_variety_uniformity.py   (rerun some variants; rows of the
                                                                 others are kept from the last run)"""
import math
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parent
sys.path.insert(0, str(ANALYSIS))
OUT = ANALYSIS / "results"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12000
WALK_SEEDS = 600
LIMIT = float(sys.argv[2]) if len(sys.argv) > 2 else 20
CASES = {"58": (4, 12, False), "S12": (4, 16, True)}
VARIANTS = os.environ.get("R20_VARIANTS", "variety,walk").split(",")
RUN_CASES = os.environ.get("R20_CASES", ",".join(CASES)).split(",")   # rerun some cases only


def case_cfg(name):
    from common import Config
    t, n, _ = CASES[name]
    return Config(f"r20_{name}", t, (n,))


def task(args):
    name, variant, seed = args
    from common import ilp_spec
    from randomizer import solve
    from randomizer import solver as S
    spec = ilp_spec(case_cfg(name), seed, LIMIT, spread=CASES[name][2])
    spec.randomization = "variety"
    if variant == "walk":
        S.ENUM_MAX_RELABELLINGS = 0          # no listing: the random walk is used
    res = solve(spec)
    return res.assign, {**res.randomization, "cap_hit": res.reproducible is False}, res.solve_seconds


def enumerate_set(name):
    """All count vectors meeting every criterion that the case requires perfectly."""
    from common import ilp_spec
    from randomizer import solver as S
    spread = CASES[name][2]
    spec = ilp_spec(case_cfg(name), 1, 60, spread=spread)
    ctx = S._prepare(spec, np.random.default_rng(1))
    levels = {"period": "required", "carryover": "required", "cooccurrence": "off",
              "spread": "required" if spread else "off"}
    model, form, _ = S._build(ctx, ctx.members, ctx.units, levels)
    n_idx = form.m[0]
    sols = []
    while len(sols) < 5000:
        x, status, _ = model.solve(np.zeros(model.n), 120, 1.0, 1)
        if x is None:
            break
        v = np.round(x[n_idx]).astype(int)
        sols.append(v)
        z = model.add_vars(len(n_idx), ub=1.0, integer=True)
        for s in range(len(n_idx)):
            model.add_row(np.r_[n_idx[s], z[s]], np.r_[1.0, -(v[s] + 1.0)], 0.0, S.INF)
        model.add_row(z, 1.0, 1.0, S.INF)
    assert "nfeasible" in status, f"enumeration of {name} not complete ({status})"
    return np.array(sols), [tuple(s) for s in ctx.seqs]


def uniformity_tests(observed, share, sims=20000, seed=0):
    """Asymptotic, Monte Carlo (exact multinomial) and pooled chi-square p-values."""
    from scipy import stats
    n = int(observed.sum())
    exp = share * n
    stat = float(((observed - exp) ** 2 / exp).sum())
    p_asym = float(stats.chi2.sf(stat, len(exp) - 1))
    sim = np.random.default_rng(seed).multinomial(n, share, size=sims)
    sim_stat = ((sim - exp) ** 2 / exp).sum(axis=1)
    p_exact = float((1 + np.sum(sim_stat >= stat - 1e-9)) / (sims + 1))
    order = np.argsort(exp)                 # pool the smallest expected counts into bins of >= 5
    bins, cur = [], []
    for i in order:
        cur.append(i)
        if exp[cur].sum() >= 5:
            bins.append(cur)
            cur = []
    if cur:
        if bins:
            bins[-1] = bins[-1] + cur
        else:
            bins.append(cur)
    ob = np.array([observed[b].sum() for b in bins])
    eb = np.array([exp[b].sum() for b in bins])
    p_pool = float(stats.chisquare(ob, eb).pvalue) if len(bins) > 1 else float("nan")
    return stat, p_asym, p_exact, p_pool, len(bins)


def main():
    from common import WORKERS
    from r03_reachability import interior
    rows, count_rows = [], []
    for name in RUN_CASES:
        sols, seqs = enumerate_set(name)
        N = CASES[name][1]
        index = {s: i for i, s in enumerate(seqs)}
        keys = [v.astype(np.int8).tobytes() for v in sols]
        alloc = np.array([math.factorial(N) / np.prod([math.factorial(k) for k in v]) for v in sols])
        expected_share = alloc / alloc.sum()
        inside = np.array([interior(sols[i].astype(float), np.delete(sols, i, 0).astype(float))
                           for i in range(len(sols))])
        print(f"{name}: {len(sols)} designs, {inside.sum()} interior", flush=True)
        for variant in VARIANTS:
            t0 = time.time()
            n_seeds = SEEDS if variant == "variety" else WALK_SEEDS   # the walk uses its full budget
            # the walk runs thousands of solves per seed, and HiGHS slows down over many solves in
            # one process, so every walk seed gets a fresh process
            per_child = 20 if variant == "variety" else 1
            with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=per_child) as pool:
                outs = pool.map(task, [(name, variant, s) for s in range(1, n_seeds + 1)], chunksize=1)
            got = [np.bincount([index[tuple(r)] for r in D], minlength=len(seqs)).astype(np.int8).tobytes()
                   for D, _, _ in outs]
            freq = pd.Series(got).value_counts()
            observed = np.array([freq.get(k, 0) for k in keys])
            reached = observed > 0
            exp = expected_share * observed.sum()
            stat, p_asym, p_exact, p_pool, n_bins = uniformity_tests(observed, expected_share)
            rec = {"case": name, "variant": variant, "t": CASES[name][0], "N": N, "spread": CASES[name][2],
                   "designs": len(sols), "interior": int(inside.sum()), "seeds": n_seeds, "budget": LIMIT,
                   "methods": pd.Series([i.get("method") for _, i, _ in outs]).value_counts().to_dict(),
                   "cap_hit": int(sum(i.get("cap_hit", False) for _, i, _ in outs)),
                   "outputs_in_set": float(np.mean([g in set(keys) for g in got])),
                   "reached": f"{reached.sum()}/{len(sols)}",
                   "interior_reached": f"{reached[inside].sum()}/{inside.sum()}",
                   "min_expected": float(exp.min()), "chi2": stat, "chi2_p": p_asym,
                   "chi2_p_exact": p_exact, "chi2_p_pooled": p_pool, "pooled_bins": n_bins,
                   "max_over_expected": float((observed / exp).max()) if observed.sum() else float("nan"),
                   "mean_seconds": float(np.mean([s for _, _, s in outs])), "wall_seconds": time.time() - t0}
            print(rec, flush=True)
            rows.append(rec)
            count_rows = [{"case": name, "variant": variant, "design": i, "interior": bool(inside[i]),
                            "allocations": alloc[i], "expected": exp[i], "observed": int(observed[i])}
                           for i in range(len(sols))]
            # saved after every variant, so an interrupted run keeps what it finished
            merge(pd.DataFrame([rec]), OUT / "r20_variety_uniformity.csv")
            merge(pd.DataFrame(count_rows), OUT / "r20_counts.csv")


def merge(new, path):
    """Replace the rows of the (case, variant) pairs just run; keep the others from the last run."""
    if path.exists():
        old = pd.read_csv(path, dtype={"case": str})
        done = set(zip(new["case"].astype(str), new["variant"]))
        old = old[[(str(c), v) not in done for c, v in zip(old["case"], old["variant"])]]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(path, index=False)


if __name__ == "__main__":
    main()
