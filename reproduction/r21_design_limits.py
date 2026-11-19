"""Limits of the designs: what the best possible design achieves, and an ablation.

  minrange   The smallest possible worst-unit carry-over range in the scalability problems
             where perfect carry-over balance is impossible (t = 3 and t = 5), proven by an ILP:
             session balance required, minimize R >= max - min of the allowed-pair counts in
             every unit (all subjects and each group).
  noeven     The worked example with LIBRA's evenness tier switched off (carry-over only kept within
             its target bands), 24 seeds, default settings: within-site carry-over range and
             efficiency with a carry-over term (M2), for range-2 versus range-3 designs. Each run in
             a fresh process.
  skeletons  How many optimal skeletons exist in configurations A and C (session and carry-
             over balance perfect, spread at its proven minimum), counted up to relabelling with
             the app's own listing (one hour cap per configuration).
  floors     The lowest possible accuracy of the per-transition observer (G2) after one
             observed session, given the session counts of each ILP design: an integer program
             over transition tables with that design's margins. Reported next to the achieved G2.

Outputs results/r21_minrange.csv, r21_noeven.csv, r21_skeletons.csv, r21_floors.csv
Usage: python r21_design_limits.py [part ...]   (default: all parts)
"""
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd



# ----------------------------------------------------------------------------- minrange
def min_range(t, N, groups, limit=900):
    from common import Config, ilp_spec
    from randomizer import solver as S
    sizes = (N,) if groups == 1 else (N // 2, N - N // 2)
    spec = ilp_spec(Config("mr", t, sizes), 1, 60)
    spec.deterministic = False
    ctx = S._prepare(spec, np.random.default_rng(1))
    levels = {"period": "required", "carryover": "off", "cooccurrence": "off", "spread": "off"}
    model, form, _ = S._build(ctx, ctx.members, ctx.units, levels)
    R = model.add_vars(1, cost=1.0)
    for u in ctx.units:
        if u.kind == "block":
            continue
        lo, hi = model.add_vars(2)
        for a, b in ctx.allowed_pairs:
            idx, coef = S._concat(form.transition(c, j, a, b) for c in u.cells for j in range(len(ctx.adj)))
            model.add_row(np.r_[idx, hi], np.r_[coef, -1.0], -S.INF, 0.0)      # count <= hi
            model.add_row(np.r_[idx, lo], np.r_[coef, -1.0], 0.0, S.INF)       # count >= lo
        model.add_row([R[0], hi, lo], [1.0, -1.0, 1.0], 0.0, S.INF)            # R >= hi - lo
    cost = np.zeros(model.n)
    cost[R] = 1.0
    t0 = time.time()
    x, text, opt = model.solve(cost, limit, 0.0, 1)
    return {"t": t, "N": N, "groups": groups, "min_worst_range": None if x is None else round(float(x[R][0])),
            "proven": bool(opt), "status": text, "seconds": round(time.time() - t0, 1)}


def part_minrange():
    from common import RESULTS
    sc = pd.read_csv(RESULTS / "scalability.csv") if (RESULTS / "scalability.csv").exists() else None
    cases = [(t, N, k) for t in (3, 5) for N in (2 * t, 3 * t, 4 * t + 2) for k in (1, 2)]
    rows = []
    for t, N, k in cases:
        r = min_range(t, N, k)
        if sc is not None:
            hit = sc[(sc.t == t) & (sc.N == N) & (sc.strata == k)]
            r["achieved_worst_range"] = int(hit.carry_range_worst.iloc[0]) if len(hit) else None
        print(r, flush=True)
        rows.append(r)
    pd.DataFrame(rows).to_csv(RESULTS / "r21_minrange.csv", index=False)


# ----------------------------------------------------------------------------- noeven
def noeven_worker(seed):
    """One solve without the evenness tier (in a fresh process, so the change stays local)."""
    from r15_human_example import spec_for
    from randomizer import solve
    from randomizer import solver as S
    S.TIERS = [x for x in S.TIERS if x[0] != "carryover_even"]
    res = solve(spec_for(seed))
    return seed, res.assign, bool(res.proven_optimal)


def part_noeven():
    from common import RESULTS, a_efficiency
    from r15_human_example import SITES, allowed
    pairs = allowed()
    rows = []
    with mp.get_context("spawn").Pool(6, maxtasksperchild=1) as pool:
        for s, D, proven in sorted(pool.imap_unordered(noeven_worker, range(1, 25))):
            rng_site = []
            for site in (0, 1):
                X = D[SITES == site]
                M = np.zeros((5, 5), int)
                for k in range(4):
                    np.add.at(M, (X[:, k], X[:, k + 1]), 1)
                v = [M[a, b] for a, b in pairs]
                rng_site.append(max(v) - min(v))
            rows.append({"seed": s, "variant": "no evenness tier", "range_site1": rng_site[0],
                         "range_site2": rng_site[1], "worst_range": max(rng_site), "proven": proven,
                         "eff_M2": a_efficiency(D, 5, True)[0], "eff_M1": a_efficiency(D, 5, False)[0]})
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "r21_noeven.csv", index=False)
    print(df.groupby("worst_range")[["eff_M1", "eff_M2"]].agg(["count", "mean", "min", "max"]).round(4), flush=True)


# ----------------------------------------------------------------------------- skeletons
def count_skeletons(cfg_name, spread_cap, hours=1.0):
    from common import CONFIGS, ilp_spec
    from randomizer import solver as S
    S.ENUM_MAX_FAMILIES = 10 ** 7
    spec = ilp_spec(CONFIGS[cfg_name], 1, 60)
    spec.deterministic = False
    ctx = S._prepare(spec, np.random.default_rng(1))
    levels = {"period": "required", "carryover": "required", "cooccurrence": "off", "spread": "preferred"}
    model, form, _ = S._build(ctx, ctx.members, ctx.units, levels)
    c = sum(model.tier_cost(("spread", k)) for k in ("group", "overall"))
    nz = np.flatnonzero(c)
    model.add_row(nz, c[nz], -S.INF, spread_cap + 1e-6)
    t0 = time.time()
    sols, fam, complete = S._enumerate_optimal(model, form, ctx, ctx.members, True, 1,
                                               time.time() + hours * 3600, lambda m: None)
    return {"config": cfg_name, "spread_cap": spread_cap, "skeletons": len(sols), "designs": int(sum(fam)),
            "complete": bool(complete), "seconds": round(time.time() - t0, 1)}


def part_skeletons():
    from common import RESULTS
    # proven spread minima (r09): A 1; C 6 (2 x 3 per group, ILP attains it in every run)
    rows = []
    for c, cap in (("A", 1), ("C", 6)):
        r = count_skeletons(c, cap)
        print(r, flush=True)
        rows.append(r)
    pd.DataFrame(rows).to_csv(RESULTS / "r21_skeletons.csv", index=False)


# ----------------------------------------------------------------------------- floors
def g2_floor(D, t, j=0):
    """Smallest sum over rows of the largest entry of a transition table with D's margins at change j."""
    from randomizer import solver as S
    rows, cols = np.bincount(D[:, j], minlength=t), np.bincount(D[:, j + 1], minlength=t)
    pairs = [(a, b) for a in range(t) for b in range(t) if a != b]
    m = S._Model()
    y = m.add_vars(len(pairs), integer=True)
    for a in range(t):
        m.add_row([y[q] for q, (x, _) in enumerate(pairs) if x == a], 1.0, rows[a], rows[a])
        m.add_row([y[q] for q, (_, z) in enumerate(pairs) if z == a], 1.0, cols[a], cols[a])
    top = m.add_vars(t, cost=1.0)
    for q, (a, b) in enumerate(pairs):
        m.add_row([top[a], y[q]], [1.0, -1.0], 0.0, S.INF)
    x, _, _ = m.solve(m.cost, 30, 0.0, 1)
    return float(np.round(x[top]).sum() / len(D))


def part_floors():
    from common import CONFIGS, RESULTS, guess_accuracy, load_pool
    rows = []
    for c in "ABCD":
        cfg = CONFIGS[c]
        for i, D in enumerate(load_pool(c, "ilp")):
            rows.append({"config": c, "design": i, "G2_after1": guess_accuracy(D, cfg.t)["G2"][0],
                         "G2_floor": g2_floor(D, cfg.t)})
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "r21_floors.csv", index=False)
    print(df.groupby("config")[["G2_after1", "G2_floor"]].agg(["mean", "min", "max"]).round(3), flush=True)


PARTS = {"minrange": part_minrange, "noeven": part_noeven, "skeletons": part_skeletons,
         "floors": part_floors}

if __name__ == "__main__":
    for name in (sys.argv[1:] or list(PARTS)):
        print(f"=== {name}", flush=True)
        PARTS[name]()
