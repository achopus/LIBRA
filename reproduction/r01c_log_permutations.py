"""Log the relabelling permutation the app draws for each seed (D, no spread,
seeds 1-60), by wrapping numpy's default_rng inside the solver process. Checks whether the
relabelling is uniform and independent across seeds.

Output: printed; results/r01c_permutations.txt
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import multiprocessing as mp

import numpy as np


def task(seed):
    import numpy as _np
    import common  # noqa: F401
    from common import CONFIGS, ilp_spec
    from randomizer import solver as S

    calls = []
    real = _np.random.default_rng

    class Proxy:
        def __init__(self, *a, **k):
            self._g = real(*a, **k)

        def __getattr__(self, name):
            return getattr(self._g, name)

        def permutation(self, x, *a, **k):
            out = self._g.permutation(x, *a, **k)
            if isinstance(x, (int, _np.integer)):
                calls.append((int(x), out.copy()))
            return out

    S.np.random.default_rng = Proxy
    cfg = CONFIGS["D"]
    res = S.solve(ilp_spec(cfg, seed, 20, spread=False))
    relabel = [p for n, p in calls if n == cfg.t][-1]
    return seed, relabel, res.assign


def main():
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        out = sorted(pool.map(task, range(1, 61), chunksize=1), key=lambda z: z[0])
    perms = np.stack([o[1] for o in out])
    t = perms.shape[1]
    print("position x label counts of the relabelling permutation over 60 seeds (expected 10 each):")
    print(np.stack([np.bincount(perms[:, j], minlength=t) for j in range(t)]))
    from scipy import stats
    chi = sum(((np.bincount(perms[:, j], minlength=t) - 10) ** 2 / 10).sum() for j in range(t))
    print("chi-square over positions:", round(chi, 1), "df ~", t * (t - 1), "p ~",
          round(stats.chi2.sf(chi, t * (t - 1)), 4))
    agree = np.mean([(perms[i] == perms[i + 1]).mean() for i in range(59)])
    print("agreement of consecutive seeds' permutations:", round(agree, 3), "(independent:", round(1 / t, 3), ")")


if __name__ == "__main__":
    main()
