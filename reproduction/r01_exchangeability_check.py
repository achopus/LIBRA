"""Check the exchangeability test that gave p ~ 0.002 for two ILP pools.

Exchangeability holds exactly by construction (Proposition 1: uniform relabelling and
within-stratum shuffling applied after the search), so the test's p-values should be uniform.
  (1) Recompute the two small p-values with 9,999 Monte Carlo replicates and a new random stream.
  (2) Calibration: build 200 pools that are exchangeable by construction (re-symmetrized copies of
      the original pool), test each with 199 replicates, and check that the p-values are uniform.
  (3) Independence of seeds: correlation between consecutive seeds' relabelling permutations,
      reproduced from numpy's default_rng streams as the app uses them.

Output: results/r01_exchangeability_check.txt (printed)
"""
import numpy as np
from scipy import stats

from a06b_exchangeability import stat, symmetrize
from common import CONFIGS, load_pool


def mc_p(pool, cfg, rng, n):
    obs = stat(pool, cfg.t)
    null = np.array([stat(symmetrize(pool, cfg, rng), cfg.t) for _ in range(n)])
    return (1 + (null >= obs).sum()) / (1 + n)


def main():
    rng = np.random.default_rng(777)
    print("(1) original pools, 9,999 replicates, new stream")
    for c, m in (("B", "ilp"), ("D", "ilp_nospread"), ("A", "ilp")):
        cfg = CONFIGS[c]
        print(f"  {c} {m}: p = {mc_p(load_pool(c, m)[:60], cfg, rng, 9999):.4f}", flush=True)

    print("(2) calibration on pools exchangeable by construction (200 pools x 199 replicates)")
    for c, m in (("B", "ilp"), ("D", "ilp_nospread")):
        cfg = CONFIGS[c]
        base = load_pool(c, m)[:60]
        ps = [mc_p(symmetrize(base, cfg, rng), cfg, rng, 199) for _ in range(200)]
        ks = stats.kstest(ps, "uniform")
        print(f"  {c} {m}: share p < 0.05 = {np.mean(np.array(ps) < 0.05):.3f}, "
              f"share p < 0.01 = {np.mean(np.array(ps) < 0.01):.3f}, KS p = {ks.pvalue:.3f}", flush=True)

    print("(3) consecutive seeds: agreement of the first permutation drawn from default_rng(seed)")
    agree = [np.mean(np.random.default_rng(s).permutation(5) == np.random.default_rng(s + 1).permutation(5))
             for s in range(1, 61)]
    print(f"  mean position agreement {np.mean(agree):.3f} (independent: 0.200)")


if __name__ == "__main__":
    main()
