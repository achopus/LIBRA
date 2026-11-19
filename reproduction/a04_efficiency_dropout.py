"""Statistical efficiency of each method's designs, and robustness to missing data.

Efficiency = (2/N) / mean variance of pairwise direct-treatment contrasts (sigma^2 = 1) under
  M1: subject + period + treatment
  M2: subject + period + treatment + first-order carry-over
1.0 equals a complete, period-balanced design analysed without carry-over.

Missing-data scenarios (averaged over random patterns per design):
  last20   20% of subjects miss the last randomized period
  random10 10% of observations missing completely at random
  drop1    one subject per stratum leaves after the first half of the periods

Outputs results/efficiency_per_design.csv, results/efficiency_summary.csv, figures/fig_efficiency.png
"""
import numpy as np
import pandas as pd

from common import CONFIGS, FIGURES, METHOD_COLORS, METHOD_LABELS, METHODS, RESULTS, a_efficiency, load_pool
import plotstyle as ps

N_DESIGNS = 60          # per method (the ILP pools hold 60)
N_PATTERNS = 30         # random missingness patterns per design


def missing_masks(cfg, rng, scenario):
    N, p = cfg.N, cfg.t
    keep = np.ones((N, p), bool)
    if scenario == "last20":
        keep[rng.choice(N, max(1, round(0.2 * N)), replace=False), -1] = False
    elif scenario == "random10":
        keep.ravel()[rng.choice(N * p, round(0.1 * N * p), replace=False)] = False
    elif scenario == "drop1":
        for s in range(len(cfg.strata_sizes)):
            i = rng.choice(np.flatnonzero(cfg.strata == s))
            keep[i, (p + 1) // 2:] = False
    return keep.ravel()


def main():
    rows = []
    for c, cfg in CONFIGS.items():
        rng = np.random.default_rng(7)
        for m in METHODS:
            pool = load_pool(c, m)[:N_DESIGNS]
            for i, D in enumerate(pool):
                rec = {"config": c, "method": m, "design": i}
                rec["eff_M1"], _ = a_efficiency(D, cfg.t, carryover=False)
                rec["eff_M2"], _ = a_efficiency(D, cfg.t, carryover=True)
                for sc in ("last20", "random10", "drop1"):
                    vals = [a_efficiency(D, cfg.t, False, keep=missing_masks(cfg, rng, sc))[0]
                            for _ in range(N_PATTERNS if sc != "drop1" else 10)]
                    rec[f"eff_M1_{sc}"] = float(np.mean(vals))
                rows.append(rec)
            print(c, m, flush=True)
    per = pd.DataFrame(rows)
    per.to_csv(RESULTS / "efficiency_per_design.csv", index=False)
    cols = [c for c in per.columns if c.startswith("eff_")]
    summ = per.groupby(["config", "method"], sort=False)[cols].agg(["mean", "std", "min"]).round(4)
    summ.to_csv(RESULTS / "efficiency_summary.csv")
    print(per.groupby(["config", "method"], sort=False)[cols].mean().round(3).to_string())
    figure(per)


def figure(per):
    """Drawn at printed size, in the style of the balance figure (r17): methods on the y axis, one panel per
    configuration, model without carry-over (top) and with it (bottom)."""
    from r17_figures import COLORS, FONT, SHORT, WIDTH, hstrip, title
    ps.apply()
    cfgs = list(CONFIGS)
    order = [m for m in METHODS if m in set(per.method)]
    rng = np.random.default_rng(0)
    fig, axes = ps.plt.subplots(2, len(cfgs), figsize=(WIDTH, 4.6), sharey=True, squeeze=False)
    for j, c in enumerate(cfgs):
        g = per[per.config == c]
        for i, col in enumerate(("eff_M1", "eff_M2")):
            ax = axes[i, j]
            hstrip(ax, {m: g[g.method == m][col].to_numpy(float) for m in order}, order, rng)
            ax.tick_params(labelsize=FONT - 0.5)
        axes[0, j].set_title(title(c), fontsize=FONT)
    for i in range(2):
        axes[i, 0].set_yticks(range(len(order)), [SHORT[m] for m in order], fontsize=FONT)
    fig.text(0.6, 0.505, "A-efficiency, model without carry-over (1 = ideal)", ha="center", fontsize=FONT)
    fig.text(0.6, 0.01, "A-efficiency, model with a carry-over term", ha="center", fontsize=FONT)
    fig.tight_layout(rect=(0, 0.03, 1, 1), h_pad=2.2)
    fig.savefig(FIGURES / "fig_efficiency.png", dpi=300)


if __name__ == "__main__":
    import sys
    if "--figure-only" in sys.argv:          # redraw from the saved per-design results
        figure(pd.read_csv(RESULTS / "efficiency_per_design.csv"))
    else:
        main()
