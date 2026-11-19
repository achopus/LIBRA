"""A warm-started, tuned heuristic on the tool's criteria, in the tool's priority order.

Simulated annealing that minimizes the tool's criteria lexicographically, in the same order as the
ILP (session; carry-over within groups; carry-over overall; spread within groups; spread overall).
The weights are powers of 1,000 apart (LEX below), larger than any possible total of
the criteria after them, so a move that worsens a higher criterion is never worth any gain in a
lower one, and the temperature schedule decides how often such a move is accepted while exploring.
Other than that, as in r02, but
  start      a stratified Williams design (common.gen_williams: whole Williams squares or pairs
             first, independently relabelled, so the start is period-balanced within strata),
             i.e. the same kind of start as the ILP's warm start;
  moves      with probability 1/2, swap two periods within one subject (as in r02);
             otherwise a period-preserving 2 x 2 exchange: subject i and another subject j of the
             same stratum with D[j,k] = D[i,l] and D[j,l] = D[i,k] both swap periods k and l, which
             leaves every period count unchanged (falls back to a single swap if no such j exists);
  cooling    geometric, T(s) = T0 (T1/T0)^s over the fraction s of the time budget, T1 = 0.01;
             T0 tuned per configuration over {1, 10, 100, 300, 1000, 3000} on seeds 901-906 (lowest mean
             final penalty), then 60 designs with seeds 1-60;
  budget     60 s per design, as for the ILP pools; the best design visited is returned, then
             relabelled and shuffled within strata like every other method.

Outputs pools/{A..E}_sa_ws.npz, results/r12_tuning.csv, results/r12_log.txt (printed)
"""
import math
import multiprocessing as mp
import time

import numpy as np
import pandas as pd

from common import BENCH_SECONDS, CONFIGS, POOLS, RESULTS, WORKERS, gen_williams
from r02_comparators import Annealer

SECONDS = BENCH_SECONDS     # same budget as the ILP
T1 = 0.01
T0_GRID = [1, 10, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e9]       # spans the lexicographic weights
TUNE_SEEDS = range(901, 907)
N_DESIGNS = 60


LEX = {"period": 1e12, ("carry", "group"): 1e9, ("carry", "overall"): 1e6,
       ("spread", "group"): 1e3, ("spread", "overall"): 1.0}


class WarmAnnealer(Annealer):
    W = LEX

    def run(self, seconds, T0):
        t, N, rng, cfg = self.t, self.cfg.N, self.rng, self.cfg
        D = gen_williams(cfg, rng)
        stratum = cfg.strata
        self.P = [np.zeros((t, t)) for _ in self.units]
        self.Sp = [np.zeros((t - 1, t, t)) for _ in self.units]
        for i in range(N):
            self._add(i, D[i], 1)
        costs = [self.unit_cost(u) for u in range(len(self.units))]
        cur = sum(costs)
        best, bestD = cur, D.copy()
        t_start = time.time()
        while True:
            el = (time.time() - t_start) / seconds
            if el >= 1 or best == 0:
                break
            T = T0 * (T1 / T0) ** el
            for _ in range(200):
                i = int(rng.integers(N))
                k, l = rng.choice(t, 2, replace=False)
                movers = [i]
                if rng.random() < 0.5:
                    cand = np.flatnonzero((stratum == stratum[i]) & (D[:, k] == D[i, l]) & (D[:, l] == D[i, k]))
                    if len(cand):
                        movers.append(int(rng.choice(cand)))
                old = {m: D[m].copy() for m in movers}
                new = {}
                for m in movers:
                    r = old[m].copy()
                    r[k], r[l] = r[l], r[k]
                    new[m] = r
                us = sorted({u for m in movers for u in self.unit_of[m]})
                before = sum(costs[u] for u in us)
                for m in movers:
                    self._add(m, old[m], -1)
                    self._add(m, new[m], 1)
                after_u = {u: self.unit_cost(u) for u in us}
                delta = sum(after_u.values()) - before
                if delta <= 0 or rng.random() < math.exp(-delta / T):
                    for m in movers:
                        D[m] = new[m]
                    for u in us:
                        costs[u] = after_u[u]
                    cur += delta
                    if cur < best - 1e-9:
                        best, bestD = cur, D.copy()
                else:
                    for m in movers:
                        self._add(m, new[m], -1)
                        self._add(m, old[m], 1)
        out = rng.permutation(t)[bestD]
        for s in range(len(cfg.strata_sizes)):
            idx = np.flatnonzero(cfg.strata == s)
            out[idx] = out[rng.permutation(idx)]
        return out, best


def task(args):
    c, seed, T0 = args
    D, best = WarmAnnealer(CONFIGS[c], np.random.default_rng(20_000 + seed)).run(SECONDS, T0)
    return c, seed, T0, D, best


def main():
    tune = [(c, s, T0) for c in CONFIGS for T0 in T0_GRID for s in TUNE_SEEDS]
    rows = []
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        for c, s, T0, _, best in pool.imap_unordered(task, tune, chunksize=1):
            rows.append({"config": c, "seed": s, "T0": T0, "penalty": best})
    tun = pd.DataFrame(rows)
    tun.to_csv(RESULTS / "r12_tuning.csv", index=False)
    tab = tun.groupby(["config", "T0"]).penalty.mean().unstack()
    print("mean final penalty by T0 (tuning seeds):\n", tab.round(1).to_string(), flush=True)
    chosen = tab.idxmin(axis=1).to_dict()
    print("chosen T0:", chosen, flush=True)

    tasks = [(c, s, chosen[c]) for c in CONFIGS for s in range(1, N_DESIGNS + 1)]
    out = {c: [] for c in CONFIGS}
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        for c, s, T0, D, best in pool.imap_unordered(task, tasks, chunksize=1):
            out[c].append((s, D, best))
    for c, items in out.items():
        items.sort(key=lambda z: z[0])
        np.savez_compressed(POOLS / f"{c}_sa_ws.npz", designs=np.stack([z[1] for z in items]),
                            seeds=np.array([z[0] for z in items]),
                            penalty=np.array([z[2] for z in items]), T0=chosen[c])
        print(c, "T0", chosen[c], "mean final penalty", np.mean([z[2] for z in items]).round(1), flush=True)


if __name__ == "__main__":
    main()
