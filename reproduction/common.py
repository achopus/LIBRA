"""Shared code for the validation analyses: configurations, comparator allocation methods,
and metrics implemented independently of the randomizer package (used to cross-check it).

A design is an integer array of shape (N, p): treatment index per subject and randomized
period. `strata` is an int array of length N (stratum per subject, in enrollment order).
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
# The solver package to import: ../app/randomizer when it exists, else ../randomizer; set ANALYSIS_SOLVER
# to point the scripts to another copy of the solver package.
_APP = ROOT.parent / "app"
_SOLVER = _APP if (_APP / "randomizer").is_dir() else ROOT.parent
sys.path.insert(0, os.environ.get("ANALYSIS_SOLVER", str(_SOLVER)))
RESULTS = ROOT / "results"
# Benchmark settings: every ILP and heuristic design gets the app's default
# budget (60 s; for the ILP in reproducible mode, a fixed amount of solver work), and solves run in
# parallel processes with one solver thread each.
BENCH_SECONDS = float(os.environ.get("BENCH_SECONDS", 60))
WORKERS = int(os.environ.get("BENCH_WORKERS", 6))
os.environ.setdefault("LIBRA_THREADS", "1")
FIGURES = ROOT / "figures"
POOLS = Path(os.environ.get("ANALYSIS_POOLS", ROOT / "pools"))   # override for smoke tests
for d in (RESULTS, FIGURES, POOLS):
    d.mkdir(exist_ok=True)


# ----------------------------------------------------------------------------- configurations
@dataclass(frozen=True)
class Config:
    name: str
    t: int                       # treatments (= randomized periods; complete crossover)
    strata_sizes: tuple          # subjects per stratum
    fixed_last: bool = False     # an extra fixed period (e.g. MAX) after the randomized ones
    label: str = ""

    @property
    def N(self):
        return int(sum(self.strata_sizes))

    @property
    def strata(self):
        return np.repeat(np.arange(len(self.strata_sizes)), self.strata_sizes)


CONFIGS = {
    # A and B carry an extra fixed final period (fixed_last=True);
    # fixed periods are excluded from the model, so they are plain five-period crossovers.
    "A": Config("A", 5, (15,), True, "t=5, N=15, one stratum (odd t, N = 3t)"),
    "B": Config("B", 5, (15, 15), True, "t=5, N=30, two strata of 15"),
    "C": Config("C", 4, (8, 8), False, "t=4, N=16, two strata (even t)"),
    "D": Config("D", 6, (10, 10), False, "t=6, N=20, two strata (N not a multiple of t)"),
    "E": Config("E", 3, (9,), False, "t=3, N=9 (perfect carry-over balance impossible)"),
}

if os.environ.get("ANALYSIS_CONFIGS"):                       # e.g. "E" for quick tests
    CONFIGS = {k: v for k, v in CONFIGS.items() if k in os.environ["ANALYSIS_CONFIGS"]}

METHODS = ["simple", "latin", "williams", "williams_best", "rerand", "ilp_nospread", "ilp"]
METHOD_LABELS = {
    "simple": "Simple (random orders)",
    "latin": "Random Latin squares",
    "williams": "Williams squares",
    "williams_best": "Williams squares, best of 500",
    "rerand": "Rerandomization (best 1%)",
    "ilp_nospread": "ILP without spread",
    "ilp": "ILP (full)",
}
# Okabe-Ito colour-blind-safe palette (distinct hues; the two ILP variants are not both green)
METHOD_COLORS = dict(zip(METHODS, ["#56B4E9", "#E69F00", "#009E73", "#7FC9B0", "#D55E00", "#CC79A7", "#0072B2"]))
METHOD_SHORT = {"simple": "Simple", "latin": "Latin sq.", "williams": "Williams", "williams_best": "Williams, best",
                "rerand": "Rerand.",
                "ilp_nospread": "ILP, no spread", "ilp": "ILP"}


# ----------------------------------------------------------------------------- comparators
def williams_square(t):
    first, lo, hi = [0], 1, t - 1
    while len(first) < t:
        first.append(lo); lo += 1
        if len(first) < t:
            first.append(hi); hi -= 1
    sq = (np.array(first)[None, :] + np.arange(t)[:, None]) % t
    return sq if t % 2 == 0 else np.vstack([sq, sq[:, ::-1]])


def random_latin_square(t, rng):
    """Random member of the isotopy class of the cyclic square (rows, columns, symbols permuted)."""
    cyc = (np.arange(t)[:, None] + np.arange(t)[None, :]) % t
    return rng.permutation(t)[cyc[rng.permutation(t)][:, rng.permutation(t)]]


def _fill_strata(cfg, rng, block_fn):
    """Fill each stratum with stacked blocks (rows shuffled); a final partial block uses a random
    subset of rows. Subjects within the stratum are assigned rows at random."""
    out = np.zeros((cfg.N, cfg.t), dtype=int)
    t = cfg.t
    for s, size in enumerate(cfg.strata_sizes):
        rows = []
        while len(rows) < size:
            block = block_fn()
            # a block may hold several Latin squares (odd-t Williams pair): use whole squares
            # first, rows shuffled within each square, so a partial block stays period-balanced
            squares = [block[i:i + t] for i in range(0, len(block), t)]
            for j in rng.permutation(len(squares)):
                sq = squares[j][rng.permutation(t)]
                rows.extend(sq[: size - len(rows)])
                if len(rows) >= size:
                    break
        idx = np.flatnonzero(cfg.strata == s)
        out[idx] = np.array(rows)[rng.permutation(size)]
    return out


def gen_simple(cfg, rng):
    return np.stack([rng.permutation(cfg.t) for _ in range(cfg.N)])


def gen_latin(cfg, rng):
    return _fill_strata(cfg, rng, lambda: random_latin_square(cfg.t, rng))


def gen_williams(cfg, rng):
    base = williams_square(cfg.t)
    return _fill_strata(cfg, rng, lambda: rng.permutation(cfg.t)[base])


def balance_score(designs, cfg):
    """Vectorized imbalance score for many designs (R, N, t): period + carry-over deviations,
    overall and within strata (used by rerandomization)."""
    R = designs.shape[0]
    score = np.zeros(R)
    units = [np.arange(cfg.N)] + ([np.flatnonzero(cfg.strata == s) for s in range(len(cfg.strata_sizes))]
                                  if len(cfg.strata_sizes) > 1 else [])
    t = cfg.t
    for rows in units:
        D = designs[:, rows]
        n = len(rows)
        lo, hi = math.floor(n / t), math.ceil(n / t)
        for k in range(t):
            C = np.stack([(D[:, :, k] == a).sum(1) for a in range(t)], 1)
            score += np.clip(C - hi, 0, None).sum(1) + np.clip(lo - C, 0, None).sum(1)
        trans = D[:, :, :-1] * t + D[:, :, 1:]
        tot = n * (t - 1) / (t * (t - 1))
        lo, hi = math.floor(tot), math.ceil(tot)
        for a in range(t):
            for b in range(t):
                if a != b:
                    c = (trans == a * t + b).sum((1, 2))
                    score += np.clip(c - hi, 0, None) + np.clip(lo - c, 0, None)
    return score


def gen_rerand(cfg, rng, K=2000, keep=0.01):
    designs = np.stack([gen_simple(cfg, rng) for _ in range(K)])
    sc = balance_score(designs, cfg)
    cutoff = np.quantile(sc, keep)
    good = np.flatnonzero(sc <= cutoff)
    return designs[rng.choice(good)]


def spread_score(designs, cfg):
    """Vectorized spread deviation (R, N, t): per transition and unit, distance from the band."""
    R, t = designs.shape[0], cfg.t
    score = np.zeros(R)
    units = [np.arange(cfg.N)] + ([np.flatnonzero(cfg.strata == s) for s in range(len(cfg.strata_sizes))]
                                  if len(cfg.strata_sizes) > 1 else [])
    for rows in units:
        D = designs[:, rows]
        tau = len(rows) / (t * (t - 1))
        lo, hi = math.floor(tau + 1e-9), math.ceil(tau - 1e-9)
        for k in range(D.shape[2] - 1):
            code = D[:, :, k] * t + D[:, :, k + 1]
            for a in range(t):
                for b in range(t):
                    if a != b:
                        c = (code == a * t + b).sum(1)
                        score += np.clip(c - hi, 0, None) + np.clip(lo - c, 0, None)
    return score


def gen_williams_best(cfg, rng, K=500):
    """Stratified Williams squares as a careful practitioner would use them: of K randomizations
    (relabellings and choices of the rows that fill partial blocks), keep the best balanced one
    (session and carry-over imbalance first, spread as a tie-breaker)."""
    designs = np.stack([gen_williams(cfg, rng) for _ in range(K)])
    score = balance_score(designs, cfg) * 1000 + spread_score(designs, cfg)
    best = np.flatnonzero(score == score.min())
    return designs[rng.choice(best)]


GENERATORS = {"simple": gen_simple, "latin": gen_latin, "williams": gen_williams,
              "williams_best": gen_williams_best, "rerand": gen_rerand}


def ilp_spec(cfg, seed, time_limit, spread=True):
    from randomizer import DesignSpec
    subj = pd.DataFrame({"subject": [f"s{i + 1}" for i in range(cfg.N)],
                         "stratum": [f"g{s}" for s in cfg.strata]})
    return DesignSpec(subjects=subj, strata=["stratum"] if len(cfg.strata_sizes) > 1 else [],
                      treatments=[f"T{i}" for i in range(cfg.t)],
                      n_periods=cfg.t + (1 if cfg.fixed_last else 0),
                      fixed={cfg.t + 1: "MAX"} if cfg.fixed_last else {},
                      spread_balance="preferred" if spread else "off",
                      seed=int(seed), time_limit=float(time_limit), deterministic=True)


# ----------------------------------------------------------------------------- pools
def pool_path(cfg_name, method):
    return POOLS / f"{cfg_name}_{method}.npz"


def load_pool(cfg_name, method):
    z = np.load(pool_path(cfg_name, method), allow_pickle=True)
    return z["designs"]


# ----------------------------------------------------------------------------- metrics
def units_of(cfg):
    """(name, row indices): all subjects, then each stratum (if more than one)."""
    out = [("all", np.arange(cfg.N))]
    if len(cfg.strata_sizes) > 1:
        out += [(f"stratum {s + 1}", np.flatnonzero(cfg.strata == s)) for s in range(len(cfg.strata_sizes))]
    return out


def period_counts(D, t):
    return np.stack([np.bincount(D[:, k], minlength=t) for k in range(D.shape[1])], 1)   # (t, p)


def transitions(D, t, changes=None):
    M = np.zeros((t, t), dtype=int)
    for k in (range(D.shape[1] - 1) if changes is None else changes):
        np.add.at(M, (D[:, k], D[:, k + 1]), 1)
    return M


def band_deviation(counts, target):
    lo, hi = math.floor(target + 1e-9), math.ceil(target - 1e-9)
    return np.clip(counts - hi, 0, None) + np.clip(lo - counts, 0, None)


def mutual_information(M):
    P = M / M.sum()
    E = P.sum(1, keepdims=True) @ P.sum(0, keepdims=True)
    nz = P > 0
    return float((P[nz] * np.log2(P[nz] / E[nz])).sum())


def design_metrics(D, cfg):
    """Balance metrics of one design (independent implementation)."""
    t, p = cfg.t, D.shape[1]
    off = ~np.eye(t, dtype=bool)
    out = {}
    for name, rows in units_of(cfg):
        X = D[rows]
        n = len(rows)
        pc = period_counts(X, t)
        out[f"period_dev[{name}]"] = int(band_deviation(pc, n / t).sum())
        M = transitions(X, t)
        out[f"carry_dev[{name}]"] = int(band_deviation(M[off], n * (p - 1) / (t * (t - 1))).sum())
        out[f"carry_range[{name}]"] = int(M[off].max() - M[off].min())
        spread = 0
        for k in range(p - 1):
            Mk = transitions(X, t, [k])
            spread += int(band_deviation(Mk[off], n / (t * (t - 1))).sum())
        out[f"spread_dev[{name}]"] = spread
    out["distinct_sequences"] = len({tuple(r) for r in D})
    per_change_mi = [mutual_information(transitions(D, t, [k])) for k in range(p - 1)]
    out["mi_per_change"] = float(np.mean(per_change_mi))
    out["mi_pooled"] = mutual_information(transitions(D, t))
    return out


# ----------------------------------------------------------------------------- predictability
def guess_accuracy(D, t):
    """Expected accuracy of three observers guessing each subject's next treatment.

    G1 knows the design's pooled transition table, the current treatment, and which treatments the
       subject already had (each treatment is given once).
    G2 knows the transition table of that specific period change (+ exclusions).
    G3 knows the whole design (all sequences, not which subject has which) and the subject's
       history so far; guesses the most common next treatment among consistent sequences.
    Ties are broken at random (expected accuracy = 1/|tied set| if the truth is among them).
    Returns dict observer -> array over prefix length k=1..p-1, plus the chance baseline.
    """
    N, p = D.shape
    pooled = transitions(D, t)
    per = [transitions(D, t, [k]) for k in range(p - 1)]
    rows = [tuple(r) for r in D]
    res = {g: np.zeros(p - 1) for g in ("G1", "G2", "G3", "chance")}
    for k in range(p - 1):                        # predicting period k+1 from periods 0..k
        acc = {g: 0.0 for g in res}
        for i in range(N):
            hist, cur, nxt = D[i, : k + 1], D[i, k], D[i, k + 1]
            remaining = np.setdiff1d(np.arange(t), hist)
            acc["chance"] += 1 / len(remaining)
            for g, table in (("G1", pooled), ("G2", per[k])):
                scores = table[cur, remaining]
                best = remaining[scores == scores.max()]
                acc[g] += (nxt in best) / len(best)
            nxts = [r[k + 1] for r in rows if r[: k + 1] == tuple(hist)]
            vals, cnt = np.unique(nxts, return_counts=True)
            best = vals[cnt == cnt.max()]
            acc["G3"] += (nxt in best) / len(best)
        for g in res:
            res[g][k] = acc[g] / N
    return res


# ----------------------------------------------------------------------------- linear models
def model_matrix(D, t, carryover=False, strata=None, keep=None):
    """Design matrix for y = subject + period + treatment (+ first-order carry-over).
    Subject fixed effects absorb strata. Returns (X, treatment columns slice)."""
    N, p = D.shape
    subj = np.repeat(np.arange(N), p)
    per = np.tile(np.arange(p), N)
    trt = D.ravel()
    prev = np.full(N * p, -1)
    prev[per > 0] = D[:, :-1].ravel()
    cols = [np.eye(N)[subj], np.eye(p)[per][:, 1:], np.eye(t)[trt][:, 1:]]
    tr = slice(N + p - 1, N + p - 1 + t - 1)
    if carryover:
        C = np.zeros((N * p, t))
        C[prev >= 0, prev[prev >= 0]] = 1
        cols.append(C[:, 1:])
    X = np.hstack(cols)
    if keep is not None:
        X = X[keep]
    return X, tr


def contrast_variances(D, t, carryover=False, keep=None):
    """Variance (sigma^2 = 1) of every pairwise direct-treatment contrast."""
    X, tr = model_matrix(D, t, carryover, keep=keep)
    XtX_inv = np.linalg.pinv(X.T @ X)
    V = np.zeros((t, t))
    B = np.zeros((X.shape[1], t))
    B[tr, 1:] = np.eye(t - 1)        # treatment j effect relative to 0 (column 0 -> zero vector)
    cov = B.T @ XtX_inv @ B
    for i, j in combinations(range(t), 2):
        V[i, j] = V[j, i] = cov[i, i] + cov[j, j] - 2 * cov[i, j]
    return V


def a_efficiency(D, t, carryover=False, keep=None):
    """Mean pairwise contrast variance relative to the ideal 2/N (complete, balanced, no carry-over)."""
    V = contrast_variances(D, t, carryover, keep)
    mean_var = V[np.triu_indices(t, 1)].mean()
    return (2 / D.shape[0]) / mean_var, mean_var
