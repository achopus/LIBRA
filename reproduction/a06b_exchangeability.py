"""Exchangeability test that respects the dependence between cells.

Claim to test: in the procedure's output, every subject is equally likely to receive every
treatment in every period. The final steps of the procedure (random relabelling of treatments,
random re-ordering of subjects within strata) make this exact by construction.

Statistic: sum over (subject, period) cells of the chi-square statistic for uniform treatment
counts across the pool. Cells are strongly dependent (rows are permutations; one relabelling is
shared by all cells of a design), so the reference distribution is built by Monte Carlo: apply
fresh random relabellings and within-stratum re-orderings to the same designs (999 replicates).
A small p-value would mean the procedure's output is less uniform than its own symmetrization.

Output results/validity_exchangeability.csv
"""
import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, load_pool


def stat(pool, t):
    R, N, p = pool.shape
    exp = R / t
    total = 0.0
    for k in range(p):
        counts = np.stack([(pool[:, :, k] == a).sum(0) for a in range(t)], 1)   # (N, t)
        total += ((counts - exp) ** 2 / exp).sum()
    return total


def symmetrize(pool, cfg, rng):
    out = np.empty_like(pool)
    for r, D in enumerate(pool):
        perm = np.arange(cfg.N)
        for s in range(len(cfg.strata_sizes)):
            idx = np.flatnonzero(cfg.strata == s)
            perm[idx] = rng.permutation(idx)
        out[r] = rng.permutation(cfg.t)[D[perm]]
    return out


def main(n_mc=999):
    rng = np.random.default_rng(2024)
    rows = []
    for c, cfg in CONFIGS.items():
        for m in ("ilp", "ilp_nospread", "williams", "simple"):
            pool = load_pool(c, m)[:60]
            obs = stat(pool, cfg.t)
            null = np.array([stat(symmetrize(pool, cfg, rng), cfg.t) for _ in range(n_mc)])
            p = (1 + (null >= obs).sum()) / (1 + n_mc)
            rows.append({"config": c, "method": m, "designs": len(pool), "statistic": round(obs, 1),
                         "null_mean": round(null.mean(), 1), "mc_p_value": p,
                         "max_abs_dev_from_1/t": max(np.abs((pool[:, :, k] == a).mean(0) - 1 / cfg.t).max()
                                                     for k in range(cfg.t) for a in range(cfg.t))})
            print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(RESULTS / "validity_exchangeability.csv", index=False)


if __name__ == "__main__":
    main()
