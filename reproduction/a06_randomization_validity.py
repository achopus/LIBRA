"""Randomization validity of the ILP procedure.

(a) Permutation tests under a restricted allocation. The global treatment F statistic is
    referred to three reference sets:
      pipeline - other designs produced by the same procedure (other seeds)       [valid by design]
      orbit    - the actual design with subjects re-shuffled within strata         [conditional test]
      naive    - unrestricted random treatment orders (as if simple randomization)  [mismatched]
    Type I error under the null, power under a dose-response effect.
(b) Exchangeability: P(subject i receives treatment a in period k) should be 1/t for all i, k, a.
(c) Diversity: distinct allocations and distinct design "skeletons" (up to relabelling of
    treatments and re-ordering of subjects within strata) among the procedure's outputs.
(d) Uniformity among optimal designs, on cases small enough to enumerate every design: is each
    optimal design produced equally often across seeds?

Outputs results/validity_*.csv
"""
import itertools
import multiprocessing as mp
import zlib

import numpy as np
import pandas as pd
from scipy import stats

from common import CONFIGS, RESULTS, Config, design_metrics, ilp_spec, load_pool, model_matrix

N_DATA = 1000


# ----------------------------------------------------------------------------- (a)
def f_stat(D, t, y):
    X, tr = model_matrix(D, t)
    Xr = np.delete(X, np.arange(tr.start, tr.stop), axis=1)
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    br = np.linalg.lstsq(Xr, y, rcond=None)[0]
    rss, rss_r = ((y - X @ b) ** 2).sum(), ((y - Xr @ br) ** 2).sum()
    return (rss_r - rss) / rss


def simulate(D, cfg, rng, effect):
    t = cfg.t
    tau = np.arange(t) / (t - 1) if effect else np.zeros(t)
    mean = 0.5 * cfg.strata[:, None] + 0.25 * np.arange(t)[None, :] + tau[D]
    return (mean + rng.normal(0, 1, (cfg.N, 1)) + rng.normal(0, 1, (cfg.N, t))).ravel()


def permutation_tests(c, rng, n_ref=59):
    cfg = CONFIGS[c]
    ilp, simple = load_pool(c, "ilp"), load_pool(c, "simple")
    rows = []
    for effect in (False, True):
        for r in range(N_DATA):
            j = rng.integers(len(ilp))
            D = ilp[j]
            y = simulate(D, cfg, rng, effect)
            T = f_stat(D, cfg.t, y)
            refs = {
                "pipeline": [f_stat(E, cfg.t, y) for k, E in enumerate(ilp) if k != j][:n_ref],
                "naive": [f_stat(E, cfg.t, y) for E in simple[:n_ref]],
            }
            orbit = []
            for _ in range(n_ref):
                perm = np.arange(cfg.N)
                for s in range(len(cfg.strata_sizes)):
                    idx = np.flatnonzero(cfg.strata == s)
                    perm[idx] = rng.permutation(idx)
                orbit.append(f_stat(D[perm], cfg.t, y))
            refs["orbit"] = orbit
            rec = {"config": c, "effect": effect}
            for name, ref in refs.items():
                rec[f"p_{name}"] = (1 + np.sum(np.array(ref) >= T - 1e-12)) / (1 + len(ref))
            rows.append(rec)
    df = pd.DataFrame(rows)
    out = []
    for effect, g in df.groupby("effect"):
        for name in ("pipeline", "orbit", "naive"):
            rej = (g[f"p_{name}"] <= 0.05).mean()
            out.append({"config": c, "scenario": "effect" if effect else "no_effect", "reference": name,
                        "rejection_rate": rej, "mcse": np.sqrt(rej * (1 - rej) / len(g)), "n": len(g)})
    return out


# ----------------------------------------------------------------------------- (b), (c)
def exchangeability(c, method="ilp"):
    cfg = CONFIGS[c]
    pool = load_pool(c, method)
    R, N, t = pool.shape
    pvals, maxdev = [], 0.0
    for i in range(N):
        for k in range(t):
            cnt = np.bincount(pool[:, i, k], minlength=t)
            pvals.append(stats.chisquare(cnt).pvalue)
            maxdev = max(maxdev, np.abs(cnt / R - 1 / t).max())
    pvals = np.array(pvals)
    combined = stats.combine_pvalues(pvals, method="fisher").pvalue
    return {"config": c, "method": method, "designs": R, "cells_tested": len(pvals),
            "share_p_below_0.05": (pvals < 0.05).mean(), "fisher_combined_p": combined,
            "max_abs_dev_from_1/t": maxdev}


def canonical(D, cfg):
    best = None
    for perm in itertools.permutations(range(cfg.t)):
        E = np.array(perm)[D]
        key = tuple(tuple(sorted(map(tuple, E[cfg.strata == s]))) for s in range(len(cfg.strata_sizes)))
        best = key if best is None or key < best else best
    return best


def diversity(c, method):
    cfg = CONFIGS[c]
    pool = load_pool(c, method)[:60]
    alloc = len({D.tobytes() for D in pool})
    skel = len({canonical(D, cfg) for D in pool})
    return {"config": c, "method": method, "designs": len(pool), "distinct_allocations": alloc,
            "distinct_skeletons": skel}


# ----------------------------------------------------------------------------- (d)
TOOL_W = {"carry": 100.0, "spread": 10.0}


def _band_dev(counts, target):
    lo, hi = np.floor(target + 1e-9), np.ceil(target - 1e-9)
    return (np.clip(counts - hi, 0, None) + np.clip(lo - counts, 0, None)).sum(-1)


def enumerate_optimal(t, N, chunk=400_000):
    """Every multiset of N treatment orders (vectorized); returns the tool's optimal set under its
    lexicographic logic (period balance required; carry-over locked if perfect is possible;
    then spread), the number of period-balanced designs, and the list of orders."""
    seqs = list(itertools.permutations(range(t)))
    S, p = len(seqs), t
    off = [(a, b) for a in range(t) for b in range(t) if a != b]
    feat_period = np.zeros((S, p * t), int)
    feat_carry = np.zeros((S, len(off)), int)
    feat_spread = np.zeros((S, (p - 1) * len(off)), int)
    for i, s in enumerate(seqs):
        for k, a in enumerate(s):
            feat_period[i, k * t + a] = 1
        for k in range(p - 1):
            q = off.index((s[k], s[k + 1]))
            feat_carry[i, q] += 1
            feat_spread[i, k * len(off) + q] = 1
    keys, carry, spread = [], [], []
    it = itertools.combinations_with_replacement(range(S), N)
    while True:
        block = np.array(list(itertools.islice(it, chunk)), dtype=np.int32)
        if not len(block):
            break
        pc = feat_period[block].sum(1)
        ok = _band_dev(pc, N / t) == 0
        block = block[ok]
        carry.append(_band_dev(feat_carry[block].sum(1), N * (p - 1) / len(off)))
        spread.append(_band_dev(feat_spread[block].sum(1), N / len(off)))
        cnt = np.zeros((len(block), S), np.int8)
        np.add.at(cnt, (np.repeat(np.arange(len(block)), N), block.ravel()), 1)
        keys += [r.tobytes() for r in cnt]
    df = pd.DataFrame({"key": keys, "carry": np.concatenate(carry), "spread": np.concatenate(spread)})
    recs = df
    if (df.carry == 0).any():
        df = df[df.carry == 0]
        df = df[df.spread == df.spread.min()]
    else:
        obj = TOOL_W["carry"] * df.carry + TOOL_W["spread"] * df.spread
        df = df[obj == obj.min()]
    return set(df.key), len(recs), seqs


def tool_task(args):
    t, N, seed = args
    from randomizer import solve
    res = solve(ilp_spec(Config("enum", t, (N,)), seed, 10))
    return res.assign


def uniformity(t, N, seeds, workers=None):
    from common import WORKERS
    workers = workers or WORKERS
    opt, n_feasible, seqs = enumerate_optimal(t, N)
    index = {s: i for i, s in enumerate(seqs)}
    with mp.get_context("spawn").Pool(workers, maxtasksperchild=1) as pool:
        outs = pool.map(tool_task, [(t, N, s) for s in range(1, seeds + 1)])
    keys = [np.bincount([index[tuple(r)] for r in D], minlength=len(seqs)).astype(np.int8).tobytes()
            for D in outs]
    freq = pd.Series(keys).value_counts()
    all_opt = all(k in opt for k in keys)
    observed = np.array([freq.get(k, 0) for k in opt])
    chi = stats.chisquare(observed) if len(opt) > 1 else None
    return {"t": t, "N": N, "period_balanced_designs": n_feasible, "optimal_designs": len(opt),
            "seeds": seeds, "all_outputs_optimal": all_opt, "distinct_outputs": len(freq),
            "share_of_optimal_set_reached": (observed > 0).mean(),
            "chi2_uniformity_p": None if chi is None else chi.pvalue,
            "max_over_expected": observed.max() / (seeds / len(opt))}


def main():
    rng = np.random.default_rng(zlib.crc32(b"validity"))
    perm = []
    for c in ("A", "B", "D"):
        perm += permutation_tests(c, rng)
        print(pd.DataFrame(perm).tail(6).to_string(index=False), flush=True)
    pd.DataFrame(perm).to_csv(RESULTS / "validity_permutation_tests.csv", index=False)

    ex = pd.DataFrame([exchangeability(c, m) for c in CONFIGS for m in ("ilp", "simple", "williams")])
    ex.to_csv(RESULTS / "validity_exchangeability.csv", index=False)
    print(ex.round(4).to_string(index=False), flush=True)

    dv = pd.DataFrame([diversity(c, m) for c in CONFIGS
                       for m in ("simple", "latin", "williams", "rerand", "ilp_nospread", "ilp")])
    dv.to_csv(RESULTS / "validity_diversity.csv", index=False)
    print(dv.to_string(index=False), flush=True)

    un = pd.DataFrame([uniformity(t, N, 300) for t, N in ((3, 6), (3, 9), (4, 4), (4, 8))])
    un.to_csv(RESULTS / "validity_uniformity.csv", index=False)
    print(un.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
