"""Does within-stratum balance matter statistically?

Two-stratum configurations B (t = 5, 2 x 15) and D (t = 6, 2 x 10); every method's pool; 2,000
repetitions per scenario, each using the next design of the pool. Base data model as in a05:
  y_ik = s_i + g_stratum + pi_k + tau_d(i,k) [+ rho_d(i,k-1)] + e_ik,  s_i, e_ik ~ N(0,1),
  tau_j = delta j/(t-1) with delta = 1 SD, theta = tau_{t-1} - tau_0.

Scenarios
  sex_period    period trend +0.25 k in stratum 1 and -0.25 k in stratum 2, no carry-over.
                Analysed by M1 (subject + period + treatment) and M1 + stratum x period.
  sex_carry     carry-over rho_j = 0.5 tau_j in stratum 2 only. Stratified analysis (common in
                preclinical work): theta estimated separately within each stratum, by M1 (carry-over
                not modelled) and M2 (modelled). Reported for stratum 2.
  ar1           within-subject AR(1) errors (rho = 0.5, unit variance), no carry-over, M1 by OLS
                (independence assumed); null and effect.
A self-and-mixed carry-over model (Kunert and Stufken 2002) coincides with the first-order model
here, because no treatment is given in two consecutive periods.

Output: results/r06_sim_strata.csv (printed)
"""
import numpy as np
import pandas as pd
from scipy import stats

from common import CONFIGS, RESULTS, load_pool, model_matrix

N_SIM = 2000
DELTA, CARRY, STRATUM = 1.0, 0.5, 0.5
METHODS = ["simple", "latin", "williams", "williams_best", "rerand", "classical", "sa", "ilp"]


class Fit:
    """OLS quantities for a design matrix X with treatment columns `tr` (treatment 0 = reference)."""

    def __init__(self, X, tr):
        Xr = np.delete(X, np.arange(tr.start, tr.stop), axis=1)
        self.pinv = np.linalg.pinv(X)
        rank, rank_r = np.linalg.matrix_rank(X), np.linalg.matrix_rank(Xr)
        self.df, self.q = X.shape[0] - rank, rank - rank_r
        self.H, self.Hr = X @ self.pinv, Xr @ np.linalg.pinv(Xr)
        c = np.zeros(X.shape[1]); c[tr.stop - 1] = 1
        self.w, self.vfac = c @ self.pinv, float(c @ np.linalg.pinv(X.T @ X) @ c)

    def analyse(self, Y):
        theta = self.w @ Y
        rss = ((Y - self.H @ Y) ** 2).sum(0)
        s2 = rss / self.df
        se = np.sqrt(s2 * self.vfac)
        F = ((((Y - self.Hr @ Y) ** 2).sum(0) - rss) / self.q) / s2
        return theta, se, stats.f.sf(F, self.q, self.df), stats.t.ppf(0.975, self.df)


def with_stratum_period(D, t, strata):
    X, tr = model_matrix(D, t)
    N, p = D.shape
    per = np.tile(np.arange(p), N)
    st = np.repeat(strata, p)
    extra = np.zeros((N * p, p - 1))
    m = st == 1
    extra[m, per[m] - 1] = (per[m] > 0)                       # stratum-2 x period (period 0 = reference)
    extra[:, :][~(per > 0)] = 0
    return np.hstack([X, extra]), tr


def simulate(D, cfg, scenario, R, rng):
    t, (N, p) = cfg.t, D.shape
    strata = cfg.strata
    tau = DELTA * np.arange(t) / (t - 1)
    s = rng.normal(size=(N, R))
    mean = (s + STRATUM * strata[:, None])[:, None, :] + tau[D][:, :, None]
    k = np.arange(p)[None, :, None]
    if scenario == "sex_period":
        slope = np.where(strata == 0, 0.25, -0.25)[:, None, None]
        mean = mean + slope * k
    else:
        mean = mean + 0.25 * k
    if scenario == "sex_carry":
        carry = np.zeros((N, p))
        carry[:, 1:] = CARRY * tau[D[:, :-1]]
        carry[strata == 0] = 0
        mean = mean + carry[:, :, None]
    if scenario.startswith("ar1"):
        e = np.zeros((N, p, R))
        e[:, 0] = rng.normal(size=(N, R))
        for j in range(1, p):
            e[:, j] = 0.5 * e[:, j - 1] + np.sqrt(1 - 0.25) * rng.normal(size=(N, R))
    else:
        e = rng.normal(size=(N, p, R))
    if scenario == "ar1_null":
        mean = mean - tau[D][:, :, None]
    return (mean + e).reshape(N * p, R)


def summarize(theta, se, pv, tq, truth):
    return {"bias": float(np.mean(theta) - truth), "emp_se": float(np.std(theta, ddof=1)),
            "coverage": float(np.mean(np.abs(theta - truth) <= tq * se)), "reject": float(np.mean(pv < 0.05))}


def run(c, method, rng):
    cfg = CONFIGS[c]
    try:
        pool = load_pool(c, method)
    except FileNotFoundError:
        return []
    R = int(np.ceil(N_SIM / len(pool)))
    acc = {}
    for D in pool:
        fits = {"M1": Fit(*model_matrix(D, cfg.t)), "M1+SxP": Fit(*with_stratum_period(D, cfg.t, cfg.strata))}
        rows2 = np.flatnonzero(cfg.strata == 1)
        D2 = D[rows2]
        fits["S2_M1"] = Fit(*model_matrix(D2, cfg.t))
        fits["S2_M2"] = Fit(*model_matrix(D2, cfg.t, True))
        for sc, analyses in (("sex_period", ("M1", "M1+SxP")), ("sex_carry", ("S2_M1", "S2_M2")),
                             ("ar1", ("M1",)), ("ar1_null", ("M1",))):
            Y = simulate(D, cfg, sc, R, rng)
            for a in analyses:
                if a.startswith("S2"):
                    idx = (rows2[:, None] * D.shape[1] + np.arange(D.shape[1])[None, :]).ravel()
                    out = fits[a].analyse(Y[idx])
                else:
                    out = fits[a].analyse(Y)
                acc.setdefault((sc, a), []).append(out)
    rows = []
    for (sc, a), outs in acc.items():
        theta = np.concatenate([o[0] for o in outs])[:N_SIM]
        se = np.concatenate([o[1] for o in outs])[:N_SIM]
        pv = np.concatenate([o[2] for o in outs])[:N_SIM]
        tq = np.concatenate([np.full(len(o[0]), o[3]) for o in outs])[:N_SIM]
        truth = 0.0 if sc == "ar1_null" else DELTA
        rows.append({"config": c, "method": method, "scenario": sc, "analysis": a,
                     **summarize(theta, se, pv, tq, truth)})
    return rows


def main():
    rng = np.random.default_rng(8)
    rows = []
    for c in ("B", "D"):
        for m in METHODS:
            rows += run(c, m, rng)
            print(c, m, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "r06_sim_strata.csv", index=False)
    print(df.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
