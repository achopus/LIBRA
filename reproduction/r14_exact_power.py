"""Exact power and bias instead of Monte Carlo estimates, and simulation rows for the comparators
of r02 and r12.

For a fixed design, the global F test of the normal linear model has an exact noncentral F
distribution when the analysis model contains the true mean: power = P(F(q, df, lambda) > F_crit),
lambda = ||(H - H_r) mu||^2 / sigma^2, where H and H_r are the hat matrices with and without the
treatment columns. Subject (and stratum) effects lie in both column spaces and drop out. The bias of
theta_hat = w'y under a misspecified model is w' mu - theta, and its SD is sqrt(w'w) sigma. Averaging
these over a method's pool gives the method's expected power, bias and SE with no Monte Carlo error
(only the finite pool of designs).

Exact quantities
  main      'effect' scenario of a05 (dose-response, delta = 1 SD, trend 0.25 k, M1, global F)
  strata    B and D, as in r06: carry-over in stratum 2 only, stratum-2 analysis by M2 (power) and
            M1 (bias); opposite-sign period trends, M1 without stratum x period term (SE)
Simulated (no exact form, or for the type I error rows of these comparators)
  a05 run() for classical (A, B), sa and sa_ws (A-E); r06 run() for sa_ws (B, D)

Output: results/r14_exact.csv, results/r14_sim_new.csv, results/r14_sim_strata_new.csv
"""
import zlib

import numpy as np
import pandas as pd
from scipy import stats

import a05_simulation as A5
import r06_sim_strata as R6
from common import CONFIGS, RESULTS, load_pool, model_matrix

METHODS = ["simple", "latin", "williams", "williams_best", "rerand", "classical", "sa", "sa_ws", "ilp_nospread", "ilp"]
DELTA, TREND, CARRY = 1.0, 0.25, 0.5


def hats(X, tr):
    Xr = np.delete(X, np.arange(tr.start, tr.stop), axis=1)
    H, Hr = X @ np.linalg.pinv(X), Xr @ np.linalg.pinv(Xr)
    rank, rank_r = np.linalg.matrix_rank(X), np.linalg.matrix_rank(Xr)
    c = np.zeros(X.shape[1]); c[tr.stop - 1] = 1
    w = c @ np.linalg.pinv(X)
    return H, Hr, X.shape[0] - rank, rank - rank_r, w


def power(X, tr, mu):
    H, Hr, df, q, _ = hats(X, tr)
    lam = float(mu @ (H - Hr) @ mu)
    return float(stats.ncf.sf(stats.f.isf(0.05, q, df), q, df, lam))


def exact_main(c, D):
    cfg = CONFIGS[c]
    t, (N, p) = cfg.t, D.shape
    tau = DELTA * np.arange(t) / (t - 1)
    mu = (tau[D] + TREND * np.arange(p)[None, :]).ravel()
    return power(*model_matrix(D, t), mu)


def exact_strata(c, D):
    cfg = CONFIGS[c]
    t, (N, p) = cfg.t, D.shape
    tau = DELTA * np.arange(t) / (t - 1)
    D2 = D[cfg.strata == 1]
    mu2 = tau[D2] + TREND * np.arange(p)[None, :]
    mu2[:, 1:] += CARRY * tau[D2[:, :-1]]
    mu2 = mu2.ravel()
    pw = power(*model_matrix(D2, t, True), mu2)
    *_, w1 = hats(*model_matrix(D2, t, False))
    bias = float(w1 @ mu2 - DELTA)
    *_, w = hats(*model_matrix(D, t, False))
    return pw, bias, float(np.sqrt(w @ w))


def main():
    rows = []
    for c in CONFIGS:
        for m in METHODS:
            try:
                pool = load_pool(c, m)
            except FileNotFoundError:
                continue
            pw = [exact_main(c, D) for D in pool]
            row = {"config": c, "method": m, "n_designs": len(pool), "power_F": np.mean(pw),
                   "power_F_sd": np.std(pw, ddof=1)}
            if c in ("B", "D"):
                ex = np.array([exact_strata(c, D) for D in pool])
                row.update({"S2_power_M2": ex[:, 0].mean(), "S2_power_M2_sd": ex[:, 0].std(ddof=1),
                            "S2_bias_M1": ex[:, 1].mean(), "SE_sexperiod_M1": ex[:, 2].mean()})
            rows.append(row)
            print(c, m, flush=True)
    ex = pd.DataFrame(rows)
    ex.to_csv(RESULTS / "r14_exact.csv", index=False)
    print(ex.round(4).to_string(index=False), flush=True)

    sim = []
    for c, cfg in CONFIGS.items():
        for m in ("classical", "sa", "sa_ws"):
            try:
                load_pool(c, m)
            except FileNotFoundError:
                continue
            sim += A5.run(cfg, m, np.random.default_rng(zlib.crc32(f"{c}-{m}".encode())))
    sim = pd.DataFrame(sim)
    sim.to_csv(RESULTS / "r14_sim_new.csv", index=False)
    print(sim.pivot_table(index=["config", "method"], columns="scenario", values="reject_F").round(3).to_string())

    rng = np.random.default_rng(8)
    st = []
    for c in ("B", "D"):
        st += R6.run(c, "sa_ws", rng)
    st = pd.DataFrame(st)
    st.to_csv(RESULTS / "r14_sim_strata_new.csv", index=False)
    print(st.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
