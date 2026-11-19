"""Stronger comparators.

classical  Best classical design. For t = 5 with 15 subjects per stratum (configurations A, B), a
           carry-over-balanced uniform design with 3t sequences exists (Newcombe 1996; Prescott
           1999). We use one such design, fixed once (found by an exact feasibility model; it has
           the same balance properties as the published constructions), randomized the classical
           way: independent random relabelling per stratum and random row assignment. For the other
           configurations the best classical design is the stratified Williams comparator
           already in the pools (C: Williams squares fit exactly; D: no classical design fits a
           stratum of 10; E: no carry-over-balanced design exists for t = 3, N = 9).
           Sensitivity: 50 distinct balanced uniform 15 x 5 designs are also saved, so results can
           be shown for the whole family rather than one arbitrary member.
sa         Heuristic search on the same criteria: simulated annealing over subjects' orders,
           minimizing the tool's weighted penalties (period 1000; carry-over 100 overall / 30 per
           stratum; spread 10 / 3), from a random start, with the ILP's budget (60 s) per design. Separates the gain due to
           the criteria from the gain due to exact optimization.

Outputs pools/{A,B}_classical.npz, pools/{A..E}_sa.npz, pools/A_balanced_family.npz
"""
import math
import multiprocessing as mp
import time

import numpy as np

from common import BENCH_SECONDS, CONFIGS, POOLS, WORKERS, ilp_spec

N_CLASSICAL = 200
N_SA = 60
SA_SECONDS = BENCH_SECONDS          # same budget as the ILP
W = {"period": 1000.0, ("carry", "overall"): 100.0, ("carry", "group"): 30.0,
     ("spread", "overall"): 10.0, ("spread", "group"): 3.0}


# ----------------------------------------------------------------------------- classical family
def balanced_family(n_designs=50, seed=0):
    """Distinct carry-over-balanced uniform designs for t = 5, N = 15 (one stratum)."""
    from randomizer import solver as S
    from ext_solver import _build
    cfg = CONFIGS["A"]
    spec = ilp_spec(cfg, 1, 60, spread=False)
    ctx = S._prepare(spec, np.random.default_rng(seed))
    levels = {"period": "required", "carryover": "required", "cooccurrence": "off", "spread": "off"}
    model, form, _ = _build(ctx, ctx.members, ctx.units, levels)
    rng = np.random.default_rng(seed)
    found = {}
    for i in range(400):
        cost = np.zeros(model.n)
        cost[form.decision] = rng.normal(size=len(form.decision))
        x, _, _ = model.solve(cost, 10, 0.0, 100 + i)
        if x is None:
            continue
        rows = form.extract(x, 0)
        key = tuple(sorted(map(tuple, rows)))
        found.setdefault(key, rows)
        if len(found) >= n_designs:
            break
    return [np.array(v) for v in found.values()]


def randomize_fixed(design, cfg, rng):
    """Classical randomization of a fixed design: per stratum, a random relabelling and a random
    assignment of rows to subjects."""
    out = np.zeros((cfg.N, cfg.t), dtype=int)
    for s in range(len(cfg.strata_sizes)):
        idx = np.flatnonzero(cfg.strata == s)
        rows = rng.permutation(cfg.t)[design]
        out[idx] = rows[rng.permutation(len(rows))]
    return out


# ----------------------------------------------------------------------------- simulated annealing
class Annealer:
    def __init__(self, cfg, rng):
        self.cfg, self.rng, self.t = cfg, rng, cfg.t
        self.units = [("overall", np.arange(cfg.N))]
        if len(cfg.strata_sizes) > 1:
            self.units += [("group", np.flatnonzero(cfg.strata == s)) for s in range(len(cfg.strata_sizes))]
        self.unit_of = [[u for u, (_, rows) in enumerate(self.units) if i in rows] for i in range(cfg.N)]
        t, m = cfg.t, cfg.t * (cfg.t - 1)
        self.off = ~np.eye(t, dtype=bool)
        self.band = []
        for _, rows in self.units:
            n = len(rows)
            b = {}
            for name, target in (("period", n / t), ("carry", n * (t - 1) / m), ("spread", n / m)):
                b[name] = (math.floor(target + 1e-9), math.ceil(target - 1e-9))
            self.band.append(b)

    @staticmethod
    def _dev(x, lo, hi):
        return float(np.clip(x - hi, 0, None).sum() + np.clip(lo - x, 0, None).sum())

    def unit_cost(self, u):
        kind = self.units[u][0]
        b = self.band[u]
        P, Sp = self.P[u], self.Sp[u]
        C = Sp.sum(0)
        w = getattr(self, "W", W)
        return (w["period"] * self._dev(P, *b["period"])
                + w[("carry", kind)] * self._dev(C[self.off], *b["carry"])
                + w[("spread", kind)] * self._dev(Sp[:, self.off], *b["spread"]))

    def _add(self, i, row, sign):
        k = np.arange(self.t)
        for u in self.unit_of[i]:
            self.P[u][k, row] += sign
            self.Sp[u][np.arange(self.t - 1), row[:-1], row[1:]] += sign

    def run(self, seconds):
        t, N, rng = self.t, self.cfg.N, self.rng
        D = np.stack([rng.permutation(t) for _ in range(N)])
        self.P = [np.zeros((t, t)) for _ in self.units]
        self.Sp = [np.zeros((t - 1, t, t)) for _ in self.units]
        for i in range(N):
            self._add(i, D[i], 1)
        costs = [self.unit_cost(u) for u in range(len(self.units))]
        cur = sum(costs)
        best, bestD = cur, D.copy()
        T0, T1 = 200.0, 0.05
        t_start = time.time()
        while True:
            el = (time.time() - t_start) / seconds
            if el >= 1 or best == 0:
                break
            T = T0 * (T1 / T0) ** el
            for _ in range(200):
                i = int(rng.integers(N))
                a, b = rng.choice(t, 2, replace=False)
                old = D[i].copy()
                new = old.copy()
                new[a], new[b] = new[b], new[a]
                us = self.unit_of[i]
                before = sum(costs[u] for u in us)
                self._add(i, old, -1)
                self._add(i, new, 1)
                after_u = {u: self.unit_cost(u) for u in us}
                delta = sum(after_u.values()) - before
                if delta <= 0 or rng.random() < math.exp(-delta / T):
                    D[i] = new
                    for u in us:
                        costs[u] = after_u[u]
                    cur += delta
                    if cur < best - 1e-9:
                        best, bestD = cur, D.copy()
                else:
                    self._add(i, new, -1)
                    self._add(i, old, 1)
        # final randomization as for any design: relabel and shuffle within strata
        out = rng.permutation(t)[bestD]
        for s in range(len(self.cfg.strata_sizes)):
            idx = np.flatnonzero(self.cfg.strata == s)
            out[idx] = out[rng.permutation(idx)]
        return out, best


def sa_task(args):
    c, seed = args
    cfg = CONFIGS[c]
    D, best = Annealer(cfg, np.random.default_rng(10_000 + seed)).run(SA_SECONDS)
    return c, seed, D, best


def main():
    family = balanced_family()
    print("balanced uniform 15 x 5 designs found:", len(family), flush=True)
    np.savez_compressed(POOLS / "A_balanced_family.npz", designs=np.stack(family))
    fixed = family[0]
    for c in ("A", "B"):
        rng = np.random.default_rng(42)
        pool = np.stack([randomize_fixed(fixed, CONFIGS[c], rng) for _ in range(N_CLASSICAL)])
        np.savez_compressed(POOLS / f"{c}_classical.npz", designs=pool, seeds=np.arange(N_CLASSICAL))
    tasks = [(c, s) for c in CONFIGS for s in range(1, N_SA + 1)]
    out = {c: [] for c in CONFIGS}
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        for c, seed, D, best in pool.imap_unordered(sa_task, tasks, chunksize=1):
            out[c].append((seed, D, best))
    for c, items in out.items():
        items.sort(key=lambda z: z[0])
        np.savez_compressed(POOLS / f"{c}_sa.npz", designs=np.stack([z[1] for z in items]),
                            seeds=np.array([z[0] for z in items]), penalty=np.array([z[2] for z in items]))
        print(c, "SA mean final penalty", np.mean([z[2] for z in items]).round(1), flush=True)


if __name__ == "__main__":
    main()
