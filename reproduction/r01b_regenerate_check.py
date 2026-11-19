"""Regenerate the two ILP pools whose exchangeability test gave p ~ 0.002
(B with default settings, D without spread; seeds 1-60, 20 s, one solve per fresh process, the
app's own solve()) and test them again. A seed-specific artefact would reproduce; a chance
result or an artefact of the original generation run would not.

Output: printed; results/r01b_regenerate_check.txt
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import multiprocessing as mp

import numpy as np

from a06b_exchangeability import stat, symmetrize
from common import CONFIGS, ilp_spec


def task(args):
    c, spread, seed = args
    from randomizer import solve
    return c, spread, seed, solve(ilp_spec(CONFIGS[c], seed, 20, spread)).assign


def main():
    tasks = [(c, spread, s) for c, spread in (("B", True), ("D", False)) for s in range(1, 61)]
    got = {}
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        for c, spread, seed, D in pool.imap_unordered(task, tasks, chunksize=1):
            got.setdefault((c, spread), {})[seed] = D
    rng = np.random.default_rng(99)
    for (c, spread), d in got.items():
        cfg = CONFIGS[c]
        P = np.stack([d[s] for s in sorted(d)])
        obs = stat(P, cfg.t)
        null = np.array([stat(symmetrize(P, cfg, rng), cfg.t) for _ in range(4999)])
        p = (1 + (null >= obs).sum()) / 5000
        print(f"{c} {'ilp' if spread else 'ilp_nospread'} regenerated seeds 1-60: p = {p:.4f}", flush=True)


if __name__ == "__main__":
    main()
