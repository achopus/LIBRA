"""Monte Carlo simulation study (reported following ADEMP; Morris, White & Crowther 2019).

Aims      Compare allocation methods on estimation and testing of treatment effects in small
          within-subject studies with strata, period trends and carry-over.
Data      y_ik = s_i + g_stratum + pi_k + tau_d(i,k) + rho_d(i,k-1) + e_ik
          s_i ~ N(0,1), e ~ N(0,1), g = 0.5 per stratum index, pi_k = 0.25 k (linear trend)
          tau_j = delta * j/(t-1) (dose-response, delta = 1 SD), rho_j = 0.5 tau_j when present.
Estimand  theta = tau_{t-1} - tau_0 (highest dose vs vehicle) and the global treatment effect.
Methods   OLS with subject and period fixed effects + treatment (M1), + carry-over (M2).
          95% t-interval for theta; global F test for treatment.
Perf.     bias, empirical SE, mean model SE, RMSE, coverage, rejection rate (type I error / power),
          with Monte Carlo SEs.
Scenarios no_effect, effect, carry_unmodelled (data with carry-over, M1),
          carry_modelled (same data, M2), dropout (effect data, 20% of subjects miss last period, M1).
Each repetition uses the next design from the method's pool (pool = its randomization distribution).

Outputs results/simulation.csv, figures/fig_simulation.png
"""
import zlib

import numpy as np
import pandas as pd
from scipy import stats

from common import CONFIGS, FIGURES, METHOD_COLORS, METHOD_LABELS, METHODS, RESULTS, load_pool, model_matrix
import plotstyle as ps

N_SIM = 2000
DELTA, CARRY, TREND, STRATUM = 1.0, 0.5, 0.25, 0.5
SCENARIOS = ["no_effect", "effect", "carry_unmodelled", "carry_modelled", "dropout"]


class Fit:
    """Pre-computed least-squares quantities for one design / model / missingness pattern."""

    def __init__(self, D, t, carry, keep=None):
        X, tr = model_matrix(D, t, carry, keep=keep)
        Xr = np.delete(X, np.arange(tr.start, tr.stop), axis=1)        # without treatment
        self.pinv = np.linalg.pinv(X)
        rank, rank_r = np.linalg.matrix_rank(X), np.linalg.matrix_rank(Xr)
        n = X.shape[0]
        self.df = n - rank
        self.q = rank - rank_r
        self.H = X @ self.pinv
        self.Hr = Xr @ np.linalg.pinv(Xr)
        c = np.zeros(X.shape[1]); c[tr.stop - 1] = 1                     # tau_{t-1} - tau_0
        self.w = c @ self.pinv
        self.vfac = float(c @ np.linalg.pinv(X.T @ X) @ c)

    def analyse(self, Y):
        """Y: (n, reps). Returns theta_hat, se, F p-value."""
        theta = self.w @ Y
        res = Y - self.H @ Y
        rss = (res ** 2).sum(0)
        s2 = rss / self.df
        se = np.sqrt(s2 * self.vfac)
        rss_r = ((Y - self.Hr @ Y) ** 2).sum(0)
        F = ((rss_r - rss) / self.q) / s2
        tq = np.full(theta.shape, stats.t.ppf(0.975, self.df))
        return theta, se, stats.f.sf(F, self.q, self.df), tq


def simulate_y(D, cfg, rng, reps, effect, carry):
    N, t = D.shape
    tau = DELTA * np.arange(t) / (t - 1) if effect else np.zeros(t)
    rho = CARRY * tau if carry else np.zeros(t)
    mean = (STRATUM * cfg.strata[:, None] + TREND * np.arange(t)[None, :] + tau[D])
    mean[:, 1:] += rho[D[:, :-1]]
    s = rng.normal(0, 1, (N, 1, reps))
    e = rng.normal(0, 1, (N, t, reps))
    return (mean[:, :, None] + s + e).reshape(N * t, reps)


def run(cfg, method, rng):
    pool = load_pool(cfg.name, method)
    t = cfg.t
    true = DELTA
    out = []
    per_design = int(np.ceil(N_SIM / len(pool)))
    for sc in SCENARIOS:
        thetas, ses, ps_, tqs, reps_done = [], [], [], [], 0
        for d, D in enumerate(pool):
            reps = min(per_design, N_SIM - reps_done)
            if reps <= 0:
                break
            effect = sc != "no_effect"
            carry = sc.startswith("carry")
            Y = simulate_y(D, cfg, rng, reps, effect, carry)
            if sc == "dropout":
                for r in range(reps):
                    keep = np.ones((cfg.N, t), bool)
                    keep[rng.choice(cfg.N, max(1, round(0.2 * cfg.N)), replace=False), -1] = False
                    f = Fit(D, t, False, keep.ravel())
                    th, se, p, tq = f.analyse(Y[keep.ravel(), r:r + 1])
                    thetas.append(th); ses.append(se); ps_.append(p); tqs.append(tq)
            else:
                f = Fit(D, t, sc == "carry_modelled")
                th, se, p, tq = f.analyse(Y)
                thetas.append(th); ses.append(se); ps_.append(p); tqs.append(tq)
            reps_done += reps
        th, se, p, tq = (np.concatenate(v) for v in (thetas, ses, ps_, tqs))
        target = 0.0 if sc == "no_effect" else true
        cover = np.abs(th - target) <= tq * se
        rej_theta = np.abs(th) / se > tq
        n = len(th)
        out.append({"config": cfg.name, "method": method, "scenario": sc, "n_sim": n,
                    "bias": th.mean() - target, "bias_mcse": th.std(ddof=1) / np.sqrt(n),
                    "emp_se": th.std(ddof=1), "model_se": se.mean(),
                    "rmse": np.sqrt(((th - target) ** 2).mean()),
                    "coverage": cover.mean(), "coverage_mcse": np.sqrt(cover.mean() * (1 - cover.mean()) / n),
                    "reject_theta": rej_theta.mean(), "reject_F": (p < 0.05).mean(),
                    "reject_mcse": np.sqrt(0.05 * 0.95 / n)})
    return out


def main():
    rows = []
    for c, cfg in CONFIGS.items():
        for m in METHODS:
            rows += run(cfg, m, np.random.default_rng(zlib.crc32(f"{c}-{m}".encode())))
            print(c, m, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "simulation.csv", index=False)
    show = df.pivot_table(index=["config", "method"], columns="scenario",
                          values=["bias", "emp_se", "coverage", "reject_F"], sort=False)
    print(show.round(3).to_string())
    figure(df)


def figure(df):
    ps.apply()
    cfgs = list(CONFIGS)
    panels = [("no_effect", "reject_F", "Type I error (global F)", 0.05),
              ("effect", "emp_se", r"Empirical SE of $\hat{\theta}$ (no carry-over)", None),
              ("carry_unmodelled", "bias", r"Bias of $\hat{\theta}$, carry-over not modelled", 0),
              ("carry_unmodelled", "emp_se", "Empirical SE, carry-over not modelled", None),
              ("dropout", "emp_se", "Empirical SE with dropout", None)]
    fig, axes = ps.plt.subplots(len(panels), 1, figsize=(9, 2.1 * len(panels)), sharex=True, squeeze=False)
    axes = axes[:, 0]
    x = np.arange(len(cfgs))
    width = 0.13
    for ax, (sc, col, title, ref) in zip(axes, panels):
        for k, m in enumerate(METHODS):
            g = df[(df.scenario == sc) & (df.method == m)].set_index("config").loc[cfgs]
            ax.bar(x + (k - 2.5) * width, g[col], width * 0.9, color=METHOD_COLORS[m], label=METHOD_LABELS[m])
        if ref is not None:
            ax.axhline(ref, color=ps.INK2, lw=0.8)
        ax.set_title(title)
    axes[-1].set_xticks(x, [f"{c}: t={CONFIGS[c].t}, N={CONFIGS[c].N}" for c in cfgs])
    axes[0].legend(ncol=3, fontsize=7, loc="upper left", bbox_to_anchor=(0, 1.55))
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_simulation.png", dpi=200)


if __name__ == "__main__":
    main()
